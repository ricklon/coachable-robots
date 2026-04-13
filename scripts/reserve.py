#!/usr/bin/env python3
"""
reserve.py — Non-interactive Chameleon lease + server provisioning

Idempotent: reuses an existing lease/server if found with the configured name.
Writes ansible/inventory.ini on success.
Exits 0 on success, 1 on failure.

Designed to be called by `just reserve` — no input() prompts, safe for agents.

Usage:
    python scripts/reserve.py [--status] [--release]

    --status   Print current lease/server state and exit
    --release  Tear down the server and lease (requires confirmation via
               COACHABLE_CONFIRM_RELEASE=yes env var)
"""

import argparse
import json
import os
import socket
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=False)

import chi
from chi import lease, server, hardware
from chi.lease import Lease

LEASE_NAME  = os.getenv("LEASE_NAME",  "coachable-robots-mi100")
SERVER_NAME = os.getenv("SERVER_NAME", "coachable-training-node")
KEY_NAME    = os.getenv("KEY_PAIR_NAME")
LEASE_HOURS = int(os.getenv("LEASE_DURATION_HOURS", 6))
NODE_TYPE   = "gpu_mi100"
IMAGE_NAME  = "CC-Ubuntu22.04"
REPO_ROOT   = Path(__file__).parent.parent


def configure_chameleon_env(strip_app_credential_scope: bool = False) -> None:
    """Mirror repo credential names to the OpenStack names python-chi expects."""
    if os.getenv("CHI_CREDENTIAL_ID") and not os.getenv("OS_APPLICATION_CREDENTIAL_ID"):
        os.environ["OS_APPLICATION_CREDENTIAL_ID"] = os.getenv("CHI_CREDENTIAL_ID", "")
    if os.getenv("CHI_CREDENTIAL_SECRET") and not os.getenv("OS_APPLICATION_CREDENTIAL_SECRET"):
        os.environ["OS_APPLICATION_CREDENTIAL_SECRET"] = os.getenv("CHI_CREDENTIAL_SECRET", "")
    os.environ.setdefault("OS_AUTH_TYPE", "v3applicationcredential")
    os.environ.setdefault("OS_PROJECT_DOMAIN_NAME", "chameleon")
    if strip_app_credential_scope and os.getenv("OS_AUTH_TYPE") == "v3applicationcredential":
        for key in ("OS_PROJECT_ID", "OS_PROJECT_NAME", "OS_PROJECT_DOMAIN_ID", "OS_PROJECT_DOMAIN_NAME"):
            os.environ.pop(key, None)


def setup_chi():
    region    = os.getenv("OS_REGION_NAME", "CHI@TACC")
    project   = os.getenv("OS_PROJECT_NAME")
    domain    = os.getenv("OS_PROJECT_DOMAIN_NAME", "chameleon")
    configure_chameleon_env(strip_app_credential_scope=True)
    _site_map = {"CHI@TACC": "CHI@TACC", "CHI@UC": "CHI@UC", "CHI@Edge": "CHI@Edge"}
    chi.use_site(_site_map.get(region, "CHI@TACC"))
    if os.getenv("OS_AUTH_TYPE") == "v3applicationcredential":
        chi.set("auth_type", "v3applicationcredential")
        chi.set("application_credential_id", os.getenv("OS_APPLICATION_CREDENTIAL_ID"))
        chi.set("application_credential_secret", os.getenv("OS_APPLICATION_CREDENTIAL_SECRET"))
    else:
        chi.set("project_name", project)
        chi.set("project_domain_name", domain)


def get_existing_lease():
    all_leases = lease.list_leases()
    for l in all_leases:
        if l.name == LEASE_NAME and l.status in ("ACTIVE", "PENDING"):
            return l
    return None


def get_existing_server():
    try:
        sid = server.get_server_id(SERVER_NAME)
        srv = server.get_server(sid)
        return srv
    except Exception:
        return None


def get_floating_ip(srv) -> str | None:
    try:
        ips = server.list_floating_ips(srv.id) if hasattr(server, "list_floating_ips") else []
        if ips:
            return ips[0]
    except Exception:
        pass
    return None


def wait_for_ssh(ip: str, timeout: int = 900, interval: int = 15) -> bool:
    print(f"  Waiting for SSH on {ip} (up to {timeout//60}m)...", flush=True)
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        try:
            with socket.create_connection((ip, 22), timeout=10):
                elapsed = round(time.monotonic() - start)
                print(f"  SSH ready after {elapsed}s")
                return True
        except OSError:
            elapsed = round(time.monotonic() - start)
            print(f"  {elapsed}s... retrying", flush=True)
            time.sleep(interval)
    return False


def write_inventory(floating_ip: str) -> None:
    private_key = os.path.expanduser("~/.ssh/id_rsa")
    inventory_path = REPO_ROOT / "ansible" / "inventory.ini"
    inventory_path.write_text(
        f"[training]\n"
        f"mi100 ansible_host={floating_ip} ansible_user=cc "
        f"ansible_ssh_private_key_file={private_key}\n\n"
        f"[training:vars]\n"
        f"ansible_ssh_common_args=-o StrictHostKeyChecking=no\n"
    )
    print(f"  Inventory written: {inventory_path}")


def status():
    setup_chi()
    my_lease = get_existing_lease()
    my_server = get_existing_server()

    state = {
        "lease":  None,
        "server": None,
        "floating_ip": None,
        "ssh_ready": False,
    }

    if my_lease:
        state["lease"] = {"name": my_lease.name, "status": my_lease.status,
                          "id": my_lease.id, "ends": str(my_lease.end_date)}
    if my_server:
        srv_status = my_server.status if hasattr(my_server, "status") else my_server.get("status")
        fip = get_floating_ip(my_server)
        state["server"] = {"name": SERVER_NAME, "status": srv_status}
        state["floating_ip"] = fip
        if fip:
            try:
                with socket.create_connection((fip, 22), timeout=5):
                    state["ssh_ready"] = True
            except OSError:
                pass

    print(json.dumps(state, indent=2))

    ready = (
        my_lease is not None
        and my_server is not None
        and state["ssh_ready"]
    )
    sys.exit(0 if ready else 2)  # 2 = exists but not ready, 1 = error


def reserve():
    setup_chi()

    if not KEY_NAME or KEY_NAME in ("your_keypair_name", "REPLACE_ME"):
        sys.exit("ERROR: KEY_PAIR_NAME not set in .env")

    # ── Lease ──
    print(f"Checking lease '{LEASE_NAME}'...")
    my_lease = get_existing_lease()

    if my_lease:
        print(f"  Reusing [{my_lease.status}] {my_lease.name}  ends: {my_lease.end_date}")
    else:
        available = hardware.get_nodes(node_type=NODE_TYPE, filter_reserved=True)
        if not available:
            sys.exit(f"ERROR: No {NODE_TYPE} nodes available — check the host calendar")

        print(f"  Creating {LEASE_HOURS}h lease for 1x {NODE_TYPE}...")
        my_lease = Lease(name=LEASE_NAME, duration=timedelta(hours=LEASE_HOURS))
        my_lease.add_node_reservation(node_type=NODE_TYPE, amount=1)
        my_lease.add_fip_reservation(amount=1)
        my_lease.submit(wait_for_active=True, wait_timeout=600, idempotent=True)
        print(f"  Lease ACTIVE: {my_lease.id}")

    # ── Server ──
    print(f"Checking server '{SERVER_NAME}'...")
    my_server = get_existing_server()

    if my_server:
        srv_status = my_server.status if hasattr(my_server, "status") else my_server.get("status")
        if srv_status == "ACTIVE":
            print(f"  Reusing ACTIVE server")
        elif srv_status == "BUILD":
            print(f"  Server building — waiting...")
            server.wait_for_active(my_server.id)
        else:
            print(f"  Server status {srv_status} — deleting and recreating")
            server.delete_server(my_server.id)
            time.sleep(10)
            my_server = None

    if my_server is None:
        reservation_id = my_lease.node_reservations[0]["id"]
        print(f"  Creating server from reservation {reservation_id}...")
        my_server = server.create_server(
            SERVER_NAME,
            reservation_id=reservation_id,
            image_name=IMAGE_NAME,
            key_name=KEY_NAME,
        )
        server.wait_for_active(my_server.id)
        print("  Server ACTIVE")

    # ── Floating IP ──
    floating_ip = get_floating_ip(my_server)
    if not floating_ip:
        floating_ip = server.associate_floating_ip(my_server.id)
        print(f"  Floating IP assigned: {floating_ip}")
    else:
        print(f"  Floating IP: {floating_ip}")

    # ── SSH ──
    if not wait_for_ssh(floating_ip):
        sys.exit(f"ERROR: SSH not available on {floating_ip} after timeout")

    # ── Inventory ──
    write_inventory(floating_ip)

    print(f"\nNode ready: ssh cc@{floating_ip}")
    print("Run `just provision` to install ROCm + LeRobot")

    # Write floating IP back to a temp file so justfile can capture it
    (REPO_ROOT / ".node_ip").write_text(floating_ip)


def release():
    if os.getenv("COACHABLE_CONFIRM_RELEASE") != "yes":
        sys.exit(
            "ERROR: Set COACHABLE_CONFIRM_RELEASE=yes to confirm resource release.\n"
            "  COACHABLE_CONFIRM_RELEASE=yes just release"
        )

    setup_chi()
    my_server = get_existing_server()
    my_lease  = get_existing_lease()

    if my_server:
        print(f"Deleting server '{SERVER_NAME}'...")
        server.delete_server(my_server.id)
        print("  Done")
    else:
        print(f"No server '{SERVER_NAME}' found")

    if my_lease:
        print(f"Deleting lease '{LEASE_NAME}'...")
        lease.delete_lease(my_lease.id)
        print("  Done — bare metal released")
    else:
        print(f"No lease '{LEASE_NAME}' found")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--status",  action="store_true", help="Show current state")
    group.add_argument("--release", action="store_true", help="Release resources")
    args = parser.parse_args()

    if args.status:
        status()
    elif args.release:
        release()
    else:
        reserve()


if __name__ == "__main__":
    main()
