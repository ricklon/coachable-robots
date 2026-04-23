# Instance Setup

This repo can be forked or cloned for a course, lab, or single robot station.
Instance-specific values stay local in `.env`, `config/fleet.yaml`, Ansible
vault files, OpenRC files, and generated inventory. Those files are gitignored.

For the current runbook after setup, use
[docs/lerobot-training-session.md](docs/lerobot-training-session.md).

## Prerequisites

- Chameleon Cloud account with access to the target project.
- Hugging Face account with a write-scoped token.
- Tailscale tailnet and a reusable+ephemeral auth key for fleet nodes.
- Python 3.12 and `uv` on the control node.
- `just`, `ansible`, `ssh`, `scp`, and `git`.
- Balena CLI only if enrolling or repairing a physical CHI@Edge Pi host.

## 1. Clone and Bootstrap

```bash
git clone https://github.com/ricklon/coachable-robots.git
cd coachable-robots
```

Create local config from templates:

```bash
cp .env.example .env
cp config/fleet.example.yaml config/fleet.yaml
cp ansible/group_vars/all/vars.example.yml ansible/group_vars/all/vars.yml
cp ansible/group_vars/all/vault.example.yml ansible/group_vars/all/vault.yml
```

## 2. Configure Secrets

Create the vault password file:

```bash
echo 'your-vault-password' > ansible/.vault_pass
chmod 600 ansible/.vault_pass
```

Fill `ansible/group_vars/all/vault.yml` with:

| Variable | Purpose |
|----------|---------|
| `vault_hf_token` | Hugging Face dataset/model upload token |
| `vault_ts_authkey` | Tailscale auth key for control, arm, and training nodes |
| `vault_chi_tacc_credential_id` | CHI@TACC application credential for MI100 |
| `vault_chi_tacc_credential_secret` | CHI@TACC application credential secret |
| `vault_openrouter_api_key` | Optional talkbot cloud LLM key |

Legacy `vault_chi_credential_id` and `vault_chi_credential_secret` are still
accepted as fallbacks, but new setups should use the site-specific names above.

Encrypt the vault:

```bash
ansible-vault encrypt ansible/group_vars/all/vault.yml
```

Then generate `.env` and SSH material:

```bash
just vault-to-env
just check-env
just check-auth-json
```

## 3. Configure Chameleon Sites

Use separate credentials for separate sites:

| Site | Use |
|------|-----|
| CHI@TACC | MI100 bare-metal training leases |
| CHI@Edge | SO-ARM101 Pi and Jetson device leases/containers |
| KVM@TACC | Optional control node |

OpenRC files belong under `ansible/` and are gitignored:

```text
ansible/app-cred-chi-edge-openrc.sh
ansible/app-cred-coachable-chi-edge-openrc-unrestricted.sh
ansible/app-cred-kvm-tacc-openrc.sh
```

For CHI@Edge lease creation, unrestricted application credentials may be needed
because Blazar can create Keystone trusts during device lease workflows.

## 4. Configure the Fleet

Edit `config/fleet.yaml` for the physical lab:

- arm IDs such as `arm-01`;
- CHI@Edge device names such as `soarm101-1`;
- leader and follower serial ports;
- camera indexes;
- CHI@Edge image and device profiles.

The working SO-ARM101 CHI@Edge device profiles are:

```yaml
device_profiles:
  - ttyacm0
  - ttyacm1
  - video0
  - video1
  - video2
  - video3
```

Leave `.env` overrides such as `EDGE_DEVICE_NAME`, `EDGE_IMAGE_REF`, and
`EDGE_DEVICE_PROFILES` blank unless you are deliberately testing a temporary
override. Normal defaults come from `config/fleet.yaml`.

## 5. Enroll or Repair a Pi on CHI@Edge

For first-time Pi enrollment, follow
[docs/pi5-chi-edge-setup.md](docs/pi5-chi-edge-setup.md).

After enrollment, the operator path is:

```bash
just edge-device-show
just reserve-edge-lease
just reserve-edge
just edge-status
just arm-test
```

Access the arm over Tailscale:

```bash
ssh root@arm-01
```

Avoid running Balena preview and CHI@Edge robot workloads at the same time.
They share the same cameras and serial ports.

## 6. Preserve Calibration

The same physical leader and follower arms are reused across sessions. Back up
calibration immediately after a known-good calibration or before training:

```bash
just arm-calibration-backup label=alpha-current
just arm-calibration-backups
```

Backups stay local under `calibration-backups/` and are gitignored. Restore only
when the same physical arms and motor IDs are attached:

```bash
just arm-calibration-restore archive=calibration-backups/<backup>.tgz
```

## 7. Prepare MI100 Training

Reserve and provision an MI100 training node:

```bash
just reserve
just provision
just test-node
```

Confirm the node is really an MI100 before training:

```bash
ssh cc@train-mi100 'lspci -nn | egrep -i "AMD|Instinct|MI100|1002"; rocm-smi'
```

If this does not show AMD/MI100 hardware, create a fresh `gpu_mi100` lease
instead of training on a generic bare-metal host.

## 8. Run a Training Session

Use the current runbook:

```bash
less docs/lerobot-training-session.md
```

Recommended first task:

```text
touch_object_v1
```

Recommended first policy:

```text
ACT
```

MI100 is gfx908 hardware. ACT is the safest first policy because it avoids
Flash Attention 2 requirements.

## Gitignored Instance Files

Do not commit local credentials, generated state, or hardware backups:

```text
.env
.codex
.node_ip
ansible/.vault_pass
ansible/inventory.ini
ansible/*-openrc.sh
ansible/*-openrc-*.sh
ansible/group_vars/all/vars.yml
ansible/group_vars/all/vault.yml
config/fleet.yaml
calibration-backups/
bench/results/*
```

Generated notebook outputs in `bench/results/` are artifacts, not source. Keep
only `bench/results/.gitkeep` tracked.
