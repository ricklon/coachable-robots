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

## In progress — KVM@TACC control node
Provisioning notebook and Ansible playbook built (ControlNode_Setup.ipynb + ansible/playbooks/setup_control_node.yml). Next steps to run it:
1. Download KVM@TACC RC file from kvm.tacc.chameleoncloud.org → save as ansible/app-cred-kvm-tacc-openrc.sh
2. Register SSH key pair at KVM@TACC (separate from CHI@TACC)
3. Add vault_pi_ssh_private_key to ansible vault
4. Run ControlNode_Setup.ipynb

## Next tasks
- Collect real demonstration episodes (pick_block task, 20+ episodes)
- Spin up MI100 on Chameleon for training
- Rebuild Docker image (speech-dispatcher fix)
