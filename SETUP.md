# Instance Setup

This repo is a GitHub Template. Fork it, then configure your instance by
following the steps below. Your instance values (credentials, usernames,
device names) stay local — they are gitignored.

## Prerequisites

- Chameleon Cloud account with an active allocation
- HuggingFace account
- balena.io account (free)
- Node.js 18+ and Python 3.10+ on your workstation

## Step 1: Install CLIs

```bash
npm install -g balena-cli
pip install python-chi-edge --break-system-packages
ansible-galaxy collection install community.general  # if running playbooks
```

## Step 2: Configure Ansible vars

```bash
cp ansible/group_vars/all/vars.example.yml ansible/group_vars/all/vars.yml
```

Edit `ansible/group_vars/all/vars.yml` and set:

| Variable | Value |
|----------|-------|
| `hf_user` | Your HuggingFace username |

## Step 3: Configure secrets (Ansible Vault)

Create a vault password file (never commit this):

```bash
echo 'your-strong-password' > ansible/.vault_pass
chmod 600 ansible/.vault_pass
```

Copy and fill in the vault template:

```bash
cp ansible/group_vars/all/vault.example.yml ansible/group_vars/all/vault.yml
```

Edit `ansible/group_vars/all/vault.yml` and set:

| Variable | Where to get it |
|----------|----------------|
| `vault_hf_token` | https://huggingface.co/settings/tokens |
| `vault_chi_credential_id` | CHI@Edge portal → Identity → Application Credentials |
| `vault_chi_credential_secret` | Same — saved when you created the credential |

Encrypt the vault (required before use):

```bash
ansible-vault encrypt ansible/group_vars/all/vault.yml
```

Verify:

```bash
head -1 ansible/group_vars/all/vault.yml
# → $ANSIBLE_VAULT;1.1;AES256
```

Once encrypted, `vault.yml` is safe to commit to your private fork.

## Step 4: Configure the notebook

Open `CoachableRobots_v3.ipynb` and update the cells marked `# CONFIGURE:`:

| Cell | Variable | Set to |
|------|----------|--------|
| Cell 1 (Setup) | `project_name` | Your Chameleon allocation, e.g. `CHI-261589` |
| Cell 1 (Setup) | `KEY_NAME` | Your Nova key pair name |
| Cell 17 (Training) | `HF_USER` | Your HuggingFace username |

## Step 5: Enroll your Pi on CHI@Edge

Follow [docs/pi5-chi-edge-setup.md](docs/pi5-chi-edge-setup.md) to:

1. Register your device with `chi-edge device register`
2. Download BalenaOS with `balena os download`
3. Bake the image with `chi-edge device bake`
4. Flash with `balena local flash`

## Step 6: Set Up Chameleon JupyterHub

JupyterHub at **https://jupyter.chameleoncloud.org** is where you run the
orchestration notebook. It takes 3-5 minutes to spin up on first load.

Once it's running, open a terminal and:

```bash
# Clone the repo into your persistent /work directory
cd /work
git clone https://github.com/YOUR_GITHUB_USERNAME/coachable-robots.git
cd coachable-robots
```

Recreate the gitignored instance files (vault.yml comes with the clone
since it's encrypted and committed):

```bash
# Vault password — same password you used locally
echo 'your-vault-password' > ansible/.vault_pass
chmod 600 ansible/.vault_pass

# vars.yml
cp ansible/group_vars/all/vars.example.yml ansible/group_vars/all/vars.yml
vim ansible/group_vars/all/vars.yml   # set hf_user
```

Set your CHI@Edge credentials in the environment. Either source the RC file
if you've uploaded it, or export directly:

```bash
export OS_AUTH_TYPE=v3applicationcredential
export OS_AUTH_URL=https://chi.edge.chameleoncloud.org:5000/v3
export OS_IDENTITY_API_VERSION=3
export OS_REGION_NAME="CHI@Edge"
export OS_APPLICATION_CREDENTIAL_ID=YOUR_CREDENTIAL_ID
export OS_APPLICATION_CREDENTIAL_SECRET=YOUR_CREDENTIAL_SECRET
```

The SSH key for accessing bare-metal training nodes lives at `/work/.ssh/id_rsa`
on JupyterHub — generate it if it doesn't exist:

```bash
ls /work/.ssh/id_rsa || ssh-keygen -t ed25519 -f /work/.ssh/id_rsa -N ""
```

Register it with Nova before launching your first training server:

```python
from chi import clients
nova = clients.nova()
with open("/work/.ssh/id_rsa.pub") as f:
    nova.keypairs.create(name="YOUR_KEY_NAME", public_key=f.read())
```

Then open `CoachableRobots_v3.ipynb` and update the `# CONFIGURE:` cells.

## Step 7: Run the pipeline

The pipeline uses two notebooks with distinct roles:

| Notebook | Purpose | Run when |
|----------|---------|----------|
| `CoachableRobots_v3.ipynb` | Provision MI100 cloud node + train | Once per training session |
| `Request_LeRobot_SOARM101.ipynb` | Lease Pi, launch container, collect demos | Each work session |

---

### CoachableRobots_v3.ipynb — Cloud Training Setup

Open on **Chameleon JupyterHub** and run cells top to bottom.

**Part 1 — Lease and Server** (~5 min, or instant if reusing)
- Checks for an existing `coachable-robots-mi100` lease and reuses it
- Lists available MI100 nodes before creating anything
- Prompts for confirmation before creating a new lease
- Expected output: `REUSING lease ...` or `Lease ACTIVE: <id>`

**Part 2 — Ansible Provisioning** (~20 min first run, ~2 min on re-runs)
- Generates `ansible/inventory.ini` from the floating IP
- Runs `setup_training_node.yml` — installs ROCm 6.3, Miniconda, PyTorch, LeRobot
- Idempotent: skips steps already completed
- Expected output: `Playbook completed successfully`

**Part 4 — Training** (after demos are collected and pushed to HF Hub)
- Set `HF_USER` and `DATASET` at the top of the cell
- Launches `lerobot-train` on the MI100 via SSH
- Expected output: training loss logs (runs in foreground; use tmux for long runs)

**Part 6 — Cleanup** (when done)
- Type `yes` at the prompt to delete server and release the lease
- Expected output: `Cleanup complete.`

---

### Request_LeRobot_SOARM101.ipynb — Edge Device

Open on **Chameleon JupyterHub** and run cells top to bottom each session.

**Setup cell**
- Sets site to `CHI@Edge` and project to `CHI-261589`
- No output expected; errors here mean auth is not configured

**Lease cell**
- Reuses `lerobot-soarm101-lease` if active, creates a 7-day lease if not
- Expected output: `Reusing lease ... ACTIVE` or `Lease ACTIVE`

**Container cell**
- Deletes any stale/errored container automatically, then creates fresh
- Pulls `rianders/lerobot-soarm101:latest` from Docker Hub (~1-2 min)
- Uses `pi_camera` device profile for webcam access
- Expected output: `Container 'lerobot-soarm101-container' is Running`

**Floating IP cell**
- Assigns a public IP if not already attached
- Expected output: `Public IP: <ip>` and SSH command

**Verify cells**
- `ls /dev/video*` — should show `/dev/video0` (C920e webcam)
- `v4l2-ctl --info` — shows camera capabilities
- **Camera capture cell** — takes a test frame and displays it inline in the notebook
  - Expected output: a 1280×720 image from the C920e
  - If this fails: check the Pi is powered, camera is plugged in, `pi_camera` profile is set

**Data collection** *(pending dual-serial helpdesk response)*
- Requires custom device profile exposing both `ttyACM0` and `ttyACM1`
- Until then: run `bash scripts/collect_demos.sh` locally on the Pi with `--privileged`

**Cleanup cell** (optional — lease persists 7 days)
- Prompts for confirmation before deleting the container
- Lease is not deleted automatically; uncomment `my_lease.delete()` to release early

---

See [README.md](README.md) for the full architecture and data flow.

## What is gitignored (instance files)

```
ansible/.vault_pass
ansible/group_vars/all/vars.yml
ansible/group_vars/all/vault.yml   # until encrypted; safe to commit once encrypted
ansible/inventory.ini              # auto-generated by the notebook
```

Never commit plaintext `vault.yml` or any file containing real tokens/credentials.
