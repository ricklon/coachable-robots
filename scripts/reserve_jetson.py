#!/usr/bin/env python3
"""
reserve_jetson.py - Non-interactive CHI@Edge Jetson AGX Orin lease/container workflow.

Manages the talkbot inference node (Jetson AGX Orin 64GB) on CHI@Edge.
The Jetson lease must be created via the portal (Blazar device lease limitation).
Set JETSON_LEASE_ID in .env after portal creation, then run this script.

Usage:
    python scripts/reserve_jetson.py [--status] [--release] [--restart-container]
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=False)

import chi
from chi import clients, lease as lease_api, network as chi_network
from chi.container import Container
from chi.lease import Lease

REPO_ROOT = Path(__file__).parent.parent

EDGE_RC_FILE = Path(os.getenv("EDGE_RC_FILE", REPO_ROOT / "ansible" / "app-cred-chi-edge-openrc.sh"))
JETSON_LEASE_ID     = os.getenv("JETSON_LEASE_ID", "")
DEVICE_NAME         = os.getenv("JETSON_DEVICE_NAME", "jetson-agx-orin-devkit-64gb-1")
CONTAINER_NAME      = os.getenv("JETSON_CONTAINER_NAME", "talkbot-orin-container")
IMAGE_REF           = os.getenv("JETSON_IMAGE_REF", "rianders/lerobot-soarm101:arm-talk-jetson")
TS_HOSTNAME         = os.getenv("JETSON_TS_HOSTNAME", "talkbot-orin")
LEASE_DAYS          = int(os.getenv("JETSON_LEASE_DAYS", "7"))

PORTAL_LEASE_URL = "https://chi.edge.chameleoncloud.org/project/leases/"


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
    for key in ("OS_PROJECT_ID", "OS_PROJECT_NAME", "OS_PROJECT_DOMAIN_ID", "OS_PROJECT_DOMAIN_NAME"):
        os.environ.pop(key, None)
    chi.reset()
    chi.use_site("CHI@Edge")
    chi.set("auth_type", "v3applicationcredential")
    chi.set("application_credential_id", os.environ.get("OS_APPLICATION_CREDENTIAL_ID"))
    chi.set("application_credential_secret", os.environ.get("OS_APPLICATION_CREDENTIAL_SECRET"))


def get_existing_lease():
    if not JETSON_LEASE_ID:
        sys.exit(
            "ERROR: JETSON_LEASE_ID not set in .env.\n"
            f"  Create a device lease via the portal:\n"
            f"  1. Open: {PORTAL_LEASE_URL}\n"
            f"  2. Resource type: Device, device name: {DEVICE_NAME}\n"
            f"  3. Once ACTIVE, set JETSON_LEASE_ID=<lease-id> in .env"
        )
    for item in lease_api.list_leases():
        if item.id == JETSON_LEASE_ID and item.status in ("ACTIVE", "PENDING"):
            return item
    return None


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
        capture_output=True, text=True, env=env, check=True,
    )
    for line in result.stdout.splitlines():
        if line.startswith("vault_hf_token:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return ""


def state_json() -> dict:
    my_lease = get_existing_lease()
    my_container = get_existing_container()
    fip = get_container_floating_ip(my_container) if my_container else None
    ts_online = False
    try:
        out = subprocess.check_output(["tailscale", "status", "--json"], stderr=subprocess.DEVNULL)
        import json as _json
        peers = _json.loads(out).get("Peer", {}).values()
        ts_online = any(
            p.get("Online") and p.get("HostName", "") == TS_HOSTNAME
            for p in peers
        )
    except Exception:
        pass
    return {
        "site": "CHI@Edge",
        "node": "talkbot-orin (Jetson AGX Orin 64GB)",
        "lease": (
            {
                "name": my_lease.name,
                "status": my_lease.status,
                "id": my_lease.id,
                "ends": str(my_lease.end_date),
            }
            if my_lease else None
        ),
        "device": DEVICE_NAME,
        "container": (
            {
                "name": my_container.name,
                "status": my_container.status,
                "id": my_container.id,
                "floating_ip": fip,
            }
            if my_container else None
        ),
        "tailscale": {
            "hostname": TS_HOSTNAME,
            "online": ts_online,
            "ssh": f"ssh root@{TS_HOSTNAME}" if ts_online else None,
        },
    }


def status() -> None:
    setup_chi_edge()
    state = state_json()
    print(json.dumps(state, indent=2))
    sys.exit(0 if (state["lease"] and state["container"]) else 2)


def reserve(restart_container: bool = False, no_fip: bool = False) -> None:
    setup_chi_edge()

    print(f"Checking Jetson lease (ID: {JETSON_LEASE_ID or 'NOT SET'})...")
    my_lease = get_existing_lease()
    if my_lease:
        print(f"  Lease [{my_lease.status}] {my_lease.name} ends: {my_lease.end_date}")
    else:
        sys.exit(
            f"ERROR: Lease {JETSON_LEASE_ID} not found or not ACTIVE.\n"
            "  Check JETSON_LEASE_ID in .env and lease status in the portal."
        )

    print(f"Checking container '{CONTAINER_NAME}'...")
    my_container = get_existing_container()
    if my_container and my_container.status.lower() == "running" and not restart_container:
        print(f"  Reusing running container: {my_container.id}")
    else:
        if restart_container and my_container and my_container.status.lower() == "running":
            print(f"  --restart-container: stopping {my_container.id}...")
            my_container.delete()
            for _ in range(24):
                time.sleep(5)
                if get_existing_container() is None:
                    break
            else:
                sys.exit("ERROR: Timed out waiting for container deletion")
            my_container = None
        if my_container:
            print(f"  Existing container [{my_container.status}] — deleting...")
            my_container.delete()
            for _ in range(24):
                time.sleep(5)
                if get_existing_container() is None:
                    break
            else:
                sys.exit("ERROR: Timed out waiting for container deletion")

        hf_token = load_hf_token()
        ssh_pub_path = Path.home() / ".ssh" / "id_ed25519.pub"
        ssh_pubkey = ssh_pub_path.read_text().strip() if ssh_pub_path.exists() else ""
        ts_authkey = os.getenv("TS_AUTHKEY", "")

        reservation_id = my_lease.device_reservations[0]["id"]
        print(f"  Reservation ID: {reservation_id}")
        print(f"  Image: {IMAGE_REF}")

        env = {
            "SSH_PUBKEY": ssh_pubkey,
            "HF_TOKEN": hf_token,
            "HF_USER": os.getenv("HF_USER", "ricklon"),
        }
        if ts_authkey:
            env["TS_AUTHKEY"] = ts_authkey
            env["TS_HOSTNAME"] = TS_HOSTNAME
            print(f"  Tailscale enabled — hostname: {TS_HOSTNAME}")

        # Talkbot configuration
        for var in ("TALKBOT_LLM_PROVIDER", "TALKBOT_LOCAL_SERVER_URL",
                    "TALKBOT_AGENT_PROMPT", "OPENROUTER_API_KEY",
                    "TALKBOT_DEFAULT_MODEL", "TALKBOT_PORT", "TALKBOT_HOST"):
            val = os.getenv(var, "")
            if val:
                env[var] = val

        use_nvidia = os.getenv("JETSON_RUNTIME", "nvidia").lower() == "nvidia"
        print(f"  Runtime: {'nvidia (GPU access)' if use_nvidia else 'default'}")
        print(f"  Creating container '{CONTAINER_NAME}'...")
        my_container = Container(
            name=CONTAINER_NAME,
            image_ref=IMAGE_REF,
            reservation_id=reservation_id,
            environment=env,
            device_profiles=[],  # Jetson: no serial/camera profiles needed
            exposed_ports=["22/tcp", "7860/tcp", "8000/tcp"],
            runtime="nvidia" if use_nvidia else None,
        )
        submitted = my_container.submit(
            wait_for_active=True, wait_timeout=900, show=None, idempotent=True
        )
        if submitted is not None:
            my_container = submitted
        print(f"  Container running: {my_container.id}")

    if not no_fip:
        fip = get_container_floating_ip(my_container)
        if fip:
            print(f"  Floating IP: {fip}")
        else:
            try:
                fip = my_container.associate_floating_ip()
                print(f"  Floating IP assigned: {fip}")
            except Exception as exc:
                print(f"  WARNING: Could not assign floating IP: {exc}")

    print(f"\nTailscale SSH: ssh root@{TS_HOSTNAME}")
    print("(Allow ~30s for tailscaled to connect after container starts)")


def release() -> None:
    if os.getenv("COACHABLE_CONFIRM_RELEASE") != "yes":
        sys.exit(
            "ERROR: Set COACHABLE_CONFIRM_RELEASE=yes to release Jetson resources.\n"
            "  COACHABLE_CONFIRM_RELEASE=yes just release-jetson"
        )
    setup_chi_edge()
    my_container = get_existing_container()
    my_lease = get_existing_lease()
    if my_container:
        print(f"Deleting container '{CONTAINER_NAME}'...")
        my_container.delete()
    else:
        print(f"No container '{CONTAINER_NAME}' found")
    if my_lease:
        print(f"Deleting lease {my_lease.id}...")
        lease_api.delete_lease(my_lease.id)
    else:
        print(f"No lease {JETSON_LEASE_ID} found")


def assign_fip() -> None:
    """Assign a floating IP to the existing running container."""
    setup_chi_edge()
    my_container = get_existing_container()
    if not my_container:
        sys.exit(f"ERROR: Container '{CONTAINER_NAME}' not found")
    print(f"Container: {my_container.name} ({my_container.status})")
    existing = get_container_floating_ip(my_container)
    if existing:
        print(f"Already has floating IP: {existing}")
        return
    try:
        fip = my_container.associate_floating_ip()
        print(f"Floating IP assigned: {fip}")
    except Exception as exc:
        sys.exit(f"ERROR: Could not assign floating IP: {exc}")


def zun_exec(cmd: str) -> None:
    """Execute a command in the running container via Zun (no SSH/Tailscale needed)."""
    setup_chi_edge()
    my_container = get_existing_container()
    if not my_container:
        sys.exit(f"ERROR: Container '{CONTAINER_NAME}' not found")
    result = clients.zun().containers.execute(my_container.name, command=cmd, run=True)
    output = result.get("output", "") if isinstance(result, dict) else str(result)
    exit_code = result.get("exit_code") if isinstance(result, dict) else None
    print(output, end="")
    if exit_code is not None and exit_code != 0:
        sys.exit(exit_code)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--status", action="store_true", help="Show current lease/container state as JSON")
    group.add_argument("--release", action="store_true", help="Delete container and lease (requires COACHABLE_CONFIRM_RELEASE=yes)")
    group.add_argument("--assign-fip", action="store_true", help="Assign floating IP to running container")
    group.add_argument("--exec", metavar="CMD", help="Execute a command in the container via Zun (no SSH needed)")
    parser.add_argument("--restart-container", action="store_true",
                        help="Delete and recreate container (keeps lease)")
    parser.add_argument("--no-fip", action="store_true", help="Do not associate a floating IP")
    args = parser.parse_args()

    if args.status:
        status()
    elif args.release:
        release()
    elif args.assign_fip:
        assign_fip()
    elif args.exec:
        zun_exec(args.exec)
    else:
        reserve(restart_container=args.restart_container, no_fip=args.no_fip)


if __name__ == "__main__":
    main()
