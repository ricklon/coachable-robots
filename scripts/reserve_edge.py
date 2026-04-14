#!/usr/bin/env python3
"""
reserve_edge.py - Non-interactive CHI@Edge SO-ARM101 lease/container workflow.

This is separate from scripts/reserve.py:
  - reserve.py targets CHI@TACC bare-metal MI100 training nodes.
  - reserve_edge.py targets CHI@Edge user-owned devices and Zun containers.

Usage:
    python scripts/reserve_edge.py [--status] [--release] [--lease-only] [--no-fip]
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=False)

import chi
from chi import clients, lease as lease_api, network as chi_network
from chi.container import Container
from chi.lease import Lease

REPO_ROOT = Path(__file__).parent.parent

EDGE_RC_FILE = Path(os.getenv("EDGE_RC_FILE", REPO_ROOT / "ansible" / "app-cred-chi-edge-openrc.sh"))
LEASE_NAME = os.getenv("EDGE_LEASE_NAME", "lerobot-soarm101-lease")
UNIQUE_LEASE_NAMES = os.getenv("EDGE_UNIQUE_LEASE_NAMES", "yes").lower() in ("1", "true", "yes")
CONTAINER_NAME = os.getenv("EDGE_CONTAINER_NAME", "lerobot-soarm101-container")
DEVICE_NAME = os.getenv("EDGE_DEVICE_NAME", "soarm101-1")
LEASE_DAYS = int(os.getenv("EDGE_LEASE_DAYS", "7"))
IMAGE_REF = os.getenv("EDGE_IMAGE_REF", "rianders/lerobot-soarm101:chi-edge")
DEVICE_PROFILES = [
    item.strip()
    for item in os.getenv(
        "EDGE_DEVICE_PROFILES",
        "ttyacm0,ttyacm1,video0,video1,video2,video3",
    ).split(",")
    if item.strip()
]


def load_edge_openrc() -> None:
    if not EDGE_RC_FILE.exists():
        sys.exit(f"ERROR: CHI@Edge RC file not found: {EDGE_RC_FILE}")

    result = subprocess.run(
        ["bash", "-lc", f"set -a && source {EDGE_RC_FILE} && env"],
        capture_output=True,
        text=True,
        check=True,
    )
    for line in result.stdout.splitlines():
        if line.startswith("OS_") and "=" in line:
            key, value = line.split("=", 1)
            os.environ[key] = value


def setup_chi_edge() -> None:
    load_edge_openrc()
    if os.getenv("OS_REGION_NAME") != "CHI@Edge":
        sys.exit(f"ERROR: {EDGE_RC_FILE} is for {os.getenv('OS_REGION_NAME')}, not CHI@Edge")

    # Application credentials are already scoped. Project scope env vars cause
    # Keystone to reject auth with "Application credentials cannot request a scope."
    for key in ("OS_PROJECT_ID", "OS_PROJECT_NAME", "OS_PROJECT_DOMAIN_ID", "OS_PROJECT_DOMAIN_NAME"):
        os.environ.pop(key, None)

    chi.reset()
    chi.use_site("CHI@Edge")
    chi.set("auth_type", "v3applicationcredential")
    chi.set("application_credential_id", os.environ.get("OS_APPLICATION_CREDENTIAL_ID"))
    chi.set("application_credential_secret", os.environ.get("OS_APPLICATION_CREDENTIAL_SECRET"))


def get_existing_lease():
    # If EDGE_LEASE_ID is set, find the lease directly by ID (useful for name transitions).
    lease_id = os.getenv("EDGE_LEASE_ID", "")
    if lease_id:
        for item in lease_api.list_leases():
            if item.id == lease_id and item.status in ("ACTIVE", "PENDING"):
                return item
        return None
    for item in lease_api.list_leases():
        if is_edge_lease_name(item.name) and item.status in ("ACTIVE", "PENDING"):
            return item
    return None


def is_edge_lease_name(name: str) -> bool:
    return name == LEASE_NAME or name.startswith(f"{LEASE_NAME}-")


def get_leases_by_name() -> list:
    return [item for item in lease_api.list_leases() if is_edge_lease_name(item.name)]


def cleanup_terminal_leases() -> None:
    terminal_statuses = {"TERMINATED", "DELETED", "ERROR"}
    for item in get_leases_by_name():
        if item.status in terminal_statuses:
            print(f"  Removing stale [{item.status}] lease with same name: {item.id}")
            try:
                lease_api.delete_lease(item.id)
            except Exception as exc:
                print(f"  WARNING: could not delete stale lease {item.id}: {exc}")


def next_lease_name() -> str:
    if not UNIQUE_LEASE_NAMES:
        return LEASE_NAME
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{LEASE_NAME}-{stamp}"


def get_existing_container():
    try:
        zun = clients.zun()
        matches = [c for c in zun.containers.list() if c.name == CONTAINER_NAME]
        if matches:
            return Container.from_zun_container(matches[0])
    except Exception:
        return None
    return None


def get_container_floating_ip(container: Container) -> str | None:
    try:
        zun = clients.zun()
        current = zun.containers.get(container.name)
        port_id = None
        for addrs in current.addresses.values():
            port_id = next((addr["port"] for addr in addrs if addr.get("port")), None)
            if port_id:
                break
        if not port_id:
            return None
        fips = chi_network.neutron().list_floatingips(port_id=port_id)["floatingips"]
        return fips[0]["floating_ip_address"] if fips else None
    except Exception:
        return None


def load_hf_token() -> str:
    token = os.getenv("HF_TOKEN", "")
    if token and token not in ("hf_REPLACE_ME", "REPLACE_ME"):
        return token

    vault_file = REPO_ROOT / "ansible" / "group_vars" / "all" / "vault.yml"
    vault_pass = REPO_ROOT / "ansible" / ".vault_pass"
    if not vault_file.exists() or not vault_pass.exists():
        return ""

    env = os.environ.copy()
    env.setdefault("ANSIBLE_LOCAL_TEMP", "/tmp/ansible-local")
    env.setdefault("ANSIBLE_REMOTE_TEMP", "/tmp/ansible-remote")
    result = subprocess.run(
        ["ansible-vault", "view", str(vault_file), "--vault-password-file", str(vault_pass)],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    for line in result.stdout.splitlines():
        if line.startswith("vault_hf_token:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return ""


def state_json() -> dict:
    my_lease = get_existing_lease()
    my_container = get_existing_container()
    fip = get_container_floating_ip(my_container) if my_container else None
    return {
        "site": "CHI@Edge",
        "lease": (
            {
                "name": my_lease.name,
                "status": my_lease.status,
                "id": my_lease.id,
                "ends": str(my_lease.end_date),
            }
            if my_lease
            else None
        ),
        "device": DEVICE_NAME,
        "container": (
            {
                "name": my_container.name,
                "status": my_container.status,
                "id": my_container.id,
                "floating_ip": fip,
            }
            if my_container
            else None
        ),
    }


def status() -> None:
    setup_chi_edge()
    state = state_json()
    print(json.dumps(state, indent=2))
    sys.exit(0 if state["lease"] else 2)


PORTAL_LEASE_URL = "https://chi.edge.chameleoncloud.org/project/leases/"


def _portal_create_hint(lease_name: str) -> str:
    return (
        "CHI@Edge device leases must be created via the portal or Chameleon JupyterHub.\n"
        "  Application credentials only carry member+reader roles; Blazar lease creation\n"
        "  requires the admin role granted in the Chameleon web UI session.\n\n"
        f"  1. Open: {PORTAL_LEASE_URL}\n"
        f"  2. Click '+ Create Lease'\n"
        f"  3. Resource type: Device, device name: {DEVICE_NAME}\n"
        f"  4. Duration: {LEASE_DAYS} day(s), name: {lease_name}\n"
        "  5. Once the lease is ACTIVE, re-run this script to continue.\n"
    )


def reserve(lease_only: bool = False, no_fip: bool = False, restart_container: bool = False) -> None:
    setup_chi_edge()

    print(f"Checking CHI@Edge lease base '{LEASE_NAME}' for device '{DEVICE_NAME}'...")
    my_lease = get_existing_lease()
    if my_lease:
        print(f"  Reusing [{my_lease.status}] {my_lease.name} ends: {my_lease.end_date}")
    else:
        cleanup_terminal_leases()
        lease_name = next_lease_name()
        print(f"  Creating {LEASE_DAYS}d CHI@Edge lease '{lease_name}' for {DEVICE_NAME}...")
        my_lease = Lease(name=lease_name, duration=timedelta(days=LEASE_DAYS))
        my_lease.add_device_reservation(device_name=DEVICE_NAME, amount=1)
        try:
            my_lease.submit(wait_for_active=True, wait_timeout=600, idempotent=True)
        except Exception as exc:
            sys.exit(
                f"ERROR: Blazar lease creation failed: {exc}\n\n"
                + _portal_create_hint(lease_name)
            )
        print(f"  Lease ACTIVE: {my_lease.id}")

    if lease_only:
        print("\nLease ready.")
        return

    print(f"Checking CHI@Edge container '{CONTAINER_NAME}'...")
    my_container = get_existing_container()
    if my_container and my_container.status.lower() == "running" and not restart_container:
        print(f"  Reusing running container: {my_container.id}")
    else:
        if restart_container and my_container and my_container.status.lower() == "running":
            print(f"  --restart-container: stopping and deleting running container {my_container.id}...")
            my_container.delete()
            for _ in range(24):
                time.sleep(5)
                if get_existing_container() is None:
                    break
            else:
                sys.exit("ERROR: Timed out waiting for container deletion")
            my_container = None
        if my_container:
            print(f"  Existing container is [{my_container.status}], deleting and recreating...")
            my_container.delete()
            for _ in range(24):
                time.sleep(5)
                if get_existing_container() is None:
                    break
            else:
                sys.exit("ERROR: Timed out waiting for stale container deletion")

        hf_token = load_hf_token()
        ssh_pub_path = Path.home() / ".ssh" / "id_ed25519.pub"
        ssh_pubkey = ssh_pub_path.read_text().strip() if ssh_pub_path.exists() else ""
        hf_user = os.getenv("HF_USER", "ricklon")
        ts_authkey = os.getenv("TS_AUTHKEY", "")
        ts_hostname = os.getenv("TS_HOSTNAME", "arm-01")
        reservation_id = my_lease.device_reservations[0]["id"]
        print(f"  Creating container from reservation {reservation_id}...")
        env = {
            "HF_TOKEN": hf_token,
            "HF_USER": hf_user,
            "LEADER_PORT": "/dev/ttyACM0",
            "FOLLOWER_PORT": "/dev/ttyACM1",
            "CAMERA_INDEX": "0",
            "SSH_PUBKEY": ssh_pubkey,
        }
        if ts_authkey:
            env["TS_AUTHKEY"] = ts_authkey
            env["TS_HOSTNAME"] = ts_hostname
            print(f"  Tailscale enabled — hostname: {ts_hostname}")
        # Talkbot configuration — passed through if set in .env
        for var in ("TALKBOT_LLM_PROVIDER", "TALKBOT_LOCAL_SERVER_URL",
                    "TALKBOT_AGENT_PROMPT", "OPENROUTER_API_KEY",
                    "TALKBOT_PORT", "TALKBOT_HOST"):
            val = os.getenv(var, "")
            if val:
                env[var] = val
        my_container = Container(
            name=CONTAINER_NAME,
            image_ref=IMAGE_REF,
            reservation_id=reservation_id,
            command=["sleep", "infinity"],
            environment=env,
            device_profiles=DEVICE_PROFILES,
        )
        submitted = my_container.submit(wait_for_active=True, wait_timeout=600, show=None, idempotent=True)
        if submitted is not None:
            my_container = submitted
        print(f"  Container running: {my_container.id}")

    if not no_fip:
        fip = get_container_floating_ip(my_container)
        if fip:
            print(f"  Floating IP: {fip}")
        else:
            fip = my_container.associate_floating_ip()
            print(f"  Floating IP assigned: {fip}")
        print(f"\nSSH: ssh root@{fip}")


def release() -> None:
    if os.getenv("COACHABLE_CONFIRM_RELEASE") != "yes":
        sys.exit(
            "ERROR: Set COACHABLE_CONFIRM_RELEASE=yes to release CHI@Edge resources.\n"
            "  COACHABLE_CONFIRM_RELEASE=yes just release-edge"
        )

    setup_chi_edge()
    my_container = get_existing_container()
    my_lease = get_existing_lease()

    if my_container:
        print(f"Deleting CHI@Edge container '{CONTAINER_NAME}'...")
        my_container.delete()
    else:
        print(f"No CHI@Edge container '{CONTAINER_NAME}' found")

    if my_lease:
        print(f"Deleting CHI@Edge lease '{LEASE_NAME}'...")
        lease_api.delete_lease(my_lease.id)
    else:
        print(f"No CHI@Edge lease '{LEASE_NAME}' found")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--status", action="store_true", help="Show current CHI@Edge lease/container state")
    group.add_argument("--release", action="store_true", help="Release CHI@Edge container and lease")
    parser.add_argument("--lease-only", action="store_true", help="Create/reuse only the device lease")
    parser.add_argument("--no-fip", action="store_true", help="Do not associate a floating IP")
    parser.add_argument("--restart-container", action="store_true",
                        help="Delete running container and recreate (keeps lease)")
    args = parser.parse_args()

    if args.status:
        status()
    elif args.release:
        release()
    else:
        reserve(lease_only=args.lease_only, no_fip=args.no_fip, restart_container=args.restart_container)


if __name__ == "__main__":
    main()
