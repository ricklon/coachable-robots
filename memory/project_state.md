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

## Pending — CHI@Edge
- Helpdesk ticket submitted (2026-04-06): requesting custom `pi_serial_dual` device profile exposing both /dev/ttyACM0 and /dev/ttyACM1. Currently pi_serial only exposes ttyACM0.

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
