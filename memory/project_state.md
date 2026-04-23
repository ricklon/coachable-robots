---
name: Project current state
description: Active work items, infrastructure status, and pending requests
type: project
---

Pi enrolled on CHI@Edge, arms calibrated and verified, full collect→replay→push pipeline working. Dataset `ricklon/soarm101-test_calibration3` successfully pushed to HuggingFace Hub.

**Why:** Building edge-to-cloud imitation learning pipeline for SO-ARM101 arms.

**How to apply:** Context for what's working vs what's still pending.

## Infrastructure status
- Pi 5 (BalenaOS, 192.168.4.191:22222): operational, arms calibrated
- Robot alpha: leader=ttyACM0 (serial 5970072696), follower=ttyACM1 (serial 5970072616)
- Camera: C920 at /dev/video0, mounted 30cm overhead
- HF account: ricklon (not rianders — rianders is Docker Hub only)
- Docker image: rianders/lerobot-soarm101:latest (needs rebuild for speech-dispatcher fix)

## CHI@Edge — dual serial resolved
- Helpdesk confirmed (2026-04-07): pass `["ttyacm0","ttyacm1"]` in `device_profiles` to expose both ports. No custom profile needed. Notebook and docs updated.

## CHI@Edge — SO-ARM lease path
- CHI@Edge SO-ARM leases are separate from CHI@TACC MI100 leases. Use `just reserve-edge-lease`, `just reserve-edge`, `just edge-status`, and `just edge-device-show`; do not use `just reserve` for SO-ARM.
- `just edge-device-show` works with `ansible/app-cred-chi-edge-openrc.sh` and confirms `soarm101-1` exists as a CHI@Edge device.
- The operator path now generates fresh lease names by default (`EDGE_UNIQUE_LEASE_NAMES=yes`), e.g. `lerobot-soarm101-lease-YYYYMMDD-HHMMSS`, because CHI@Edge should use new lease names rather than reusing old terminated names.
- Current blocker (2026-04-13): API lease creation for `soarm101-1` still returns CHI@Edge Blazar `ERROR: Internal Server Error`, even with a fresh lease name and explicit start/end timestamps.
- Next step: create the CHI@Edge lease manually in the web UI. If manual lease succeeds, set `EDGE_LEASE_NAME` to that lease name and use `just edge-status` / `just reserve-edge` to continue container setup.

## CHI@Edge — SO-ARM device profile blocker (2026-04-16)
- Lease `lerobot-soarm101-lease-20260413` is ACTIVE for `soarm101-1`, and a no-device-profile debug container can run with SSH/Tailscale.
- Full robot profiles (`ttyacm0`, `ttyacm1`, `video0`, `video1`, `video2`, `video3`) fail scheduling with `Insufficient smarter-devices/ttyACM0`, `ttyACM1`, and `video*`.
- Serial-only profiles (`EDGE_DEVICE_PROFILES=ttyacm0,ttyacm1`) also fail with insufficient `ttyACM0` / `ttyACM1`.
- Negative-control legacy profile (`EDGE_DEVICE_PROFILES=pi_serial`) also fails with `Insufficient smarter-devices/ttyACM0`, confirming this is not a custom profile spelling/list issue.
- Current evidence points to CHI@Edge host visibility or smarter-device-manager resource advertisement on the k3s node. Keep using `EDGE_DEVICE_PROFILES=none just restart-arm` only for image/Tailscale/debug checks until CHI@Edge fixes allocatable device resources.

## CHI@Edge — Jetson Orin status (2026-04-15)
- Jetson lease `talkbot-orin-lease` is ACTIVE through 2026-04-21; container `talkbot-orin-container` is Running with floating IP `129.114.34.212`.
- GPU access is solved: Jetson containers must use `runtime="nvidia"` (`JETSON_RUNTIME=nvidia`), not device profiles. Confirmed present in-container: `/dev/nvidia0`, `/dev/nvidiactl`, `/dev/nvidia-modeset`, and `/dev/dri/renderD128`.
- Outbound internet remains the blocker. From the running Jetson container, DNS uses `10.43.0.10`, external DNS resolution hangs, `ping 1.1.1.1` has 100% packet loss, and `curl https://controlplane.tailscale.com` times out during DNS resolution.
- Tailscale on the Jetson container is `NeedsLogin` / offline because it cannot reach Tailscale control; the floating IP appears to provide inbound association only and does not provide outbound NAT.
- For Jetson follow-up, treat GPU/runtime as confirmed working and focus support/debugging on CHI@Edge pod egress/NAT/DNS.

## In progress — KVM@TACC control node
Provisioning notebook and Ansible playbook built (ControlNode_Setup.ipynb + ansible/playbooks/setup_control_node.yml). Next steps to run it:
1. Download KVM@TACC RC file from kvm.tacc.chameleoncloud.org → save as ansible/app-cred-kvm-tacc-openrc.sh
2. Register SSH key pair at KVM@TACC (separate from CHI@TACC)
3. Add vault_pi_ssh_private_key to ansible vault
4. Run ControlNode_Setup.ipynb

## Future TODO — MI100 talkbot / inference benchmark
- Attempted on 2026-04-15 against `coachable-training-node` at `129.114.109.229`.
- The node was reachable and Ansible could install ROCm userland, but it was not an MI100 host: OpenStack showed flavor `baremetal`, the lease `chi-tacc-talkbot1` had `resource_properties=""`, and `lspci` on the node showed only the Matrox BMC display controller with no AMD GPU. `rocminfo` reported `ROCk module is NOT loaded, possibly no GPU devices`.
- Chameleon bare-metal servers commonly show flavor `baremetal`; the GPU selection must come from the Blazar lease reservation. For MI100, create a fresh lease whose node reservation filters `node_type=gpu_mi100`, then launch the server from that reservation.
- Avoid reusing `chi-tacc-talkbot1` for MI100 work because it is a generic physical host lease.
- Recommended future steps:
  1. Release or ignore the generic `chi-tacc-talkbot1` server/lease.
  2. Set a fresh `LEASE_NAME`, e.g. `coachable-mi100-bench`, and keep `SERVER_NAME` distinct.
  3. Run `just reserve`; `scripts/reserve.py` uses `NODE_TYPE = "gpu_mi100"` and `Lease.add_node_reservation(node_type="gpu_mi100", amount=1)`.
  4. Before provisioning, verify `ssh cc@$(cat .node_ip) 'lspci -nn | egrep -i "AMD|Instinct|MI100|1002"'`.
  5. Run `just provision`, then run `bench/benchmark_inference.py --tag mi100`.
- Repo fixes made during this attempt: `just provision` now passes the vault password and writable Ansible temp dirs; `setup_training_node.yml` uses the correct ROCm 6.3.4 installer package name and reboots after first ROCm install; `reserve.py` writes inventory with an existing SSH key instead of assuming `~/.ssh/id_rsa`.

## Next tasks
- Collect real demonstration episodes (pick_block task, 20+ episodes)
- Spin up MI100 on Chameleon for training
- Rebuild Docker image (speech-dispatcher fix)
