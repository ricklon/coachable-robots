# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

Coachable Robots is an edge-to-cloud pipeline for training robot manipulation policies using imitation learning. Students and makers "coach" a SO-ARM101 robotic arm by demonstrating tasks with an Xbox controller, the demonstrations are recorded as LeRobot datasets, uploaded to HuggingFace Hub, trained on Chameleon Cloud MI100 GPUs, and the resulting policy is pulled back for autonomous execution.

The project serves dual purposes: a functional robotics training pipeline and a pedagogical framework for teaching embodied AI through hands-on demonstration rather than programming.

## Architecture

```
┌───────────────────────────┐                          ┌────────────────────────────┐
│    Raspberry Pi 5 (Edge)  │                          │  Chameleon MI100 (Cloud)   │
│                           │                          │                            │
│  xbox_soarm_teleop        │   HuggingFace Hub       │  LeRobot training          │
│  + SO-ARM101 follower     │  ────── dataset ──────> │  ACT / Diffusion / Pi0     │
│  + 2x USB cameras         │                          │                            │
│  + LeRobot recorder       │  <── checkpoint pull ── │  ROCm 6.3 + PyTorch 2.7    │
│                           │                          │  (gfx908 bare metal)       │
│  Docker container         │                          │  Ansible-provisioned       │
└───────────────────────────┘                          └────────────────────────────┘
        │                                                        │
        │  Chameleon Jupyter Notebook (Orchestration)             │
        │  python-chi 1.0+ API                                   │
        │  Lease/server management, Ansible execution             │
        └────────────────────────────────────────────────────────┘
```

## Role Model

Three distinct roles, each with a dedicated interface:

| Role | Interface | Who / What |
|---|---|---|
| **Operator** | `just` CLI | Human or AI agent |
| **System** | Ansible + chi API | Called by operator via `just` |
| **Teacher / Student** | `notebooks/` | Humans only |

**Agents operate exclusively via `just`.** Every `just` recipe is non-interactive — no `input()` prompts, predictable exit codes, JSON output available. Agents should never touch notebooks directly; they can execute them as acceptance tests via `just verify-*`.

**Notebooks are the teacher/student experience.** They are authored by humans, executed by students, and verified by operators via `just verify-*`. Claude Code may execute notebooks to verify workflows but must never author or modify their content.

## Agent Operations

Agents (Claude Code or other) operate the system through `just`. The canonical agent workflow:

```bash
# Bootstrap (one-time per machine)
echo 'vault-password' > ansible/.vault_pass && chmod 600 ansible/.vault_pass
just vault-to-env          # decrypt vault → write .env + SSH keys

# Verify environment
just check-auth            # live credential check (exits 1 on failure)
just check-auth-json       # same, machine-readable output

# Infrastructure
just reserve               # non-interactive lease + server + inventory
just provision             # Ansible: ROCm + LeRobot on training node
just node-status           # JSON state: lease, server, floating_ip, ssh_ready

# Health checks
just test-node             # GPU + ROCm + PyTorch on MI100
just test-pi               # serial ports + cameras + containers on Pi
just test-all              # auth + node + pi combined
just ready                 # test-all + verify-all (full readiness)

# Benchmarks
just bench-inference-node  # run benchmark_inference.py on MI100, save JSON
just bench-inference-pi    # run on Pi
just bench-inference-local # run locally
just bench-inference-remote host=cc@<ip> tag=h100   # arbitrary remote target
just bench-all             # all targets + summary table
just bench-summary         # compare latest results across tags

# Release (requires COACHABLE_CONFIRM_RELEASE=yes)
COACHABLE_CONFIRM_RELEASE=yes just release
```

### Agent Auth Prerequisites

Before an agent can operate, the machine needs:
1. `ansible/.vault_pass` — the vault decryption password (injected by human or CI secret)
2. `~/.ssh/id_rsa` — SSH key for Chameleon nodes (written by `just vault-to-env`)

Everything else derives from these two inputs. `just vault-to-env` is the bootstrap step.

### Exit Codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Error (auth failure, missing config, command failed) |
| `2` | Partial state (e.g. `node-status`: lease exists but SSH not ready) |

### Benchmark Multi-Target Pattern

`bench/benchmark_inference.py` runs on the local machine and auto-detects the device.
Call it via SSH for remote targets. Results are tagged by device name:

```
bench/results/bench_inference_mi100_20260412_143022.json
bench/results/bench_inference_h100_20260412_150011.json
bench/results/bench_inference_pi5_20260412_151233.json
```

`just bench-summary` prints a comparison table across all tags.

## Notebooks

`notebooks/` contains the student control plane — focused, step-by-step workflows:

| Notebook | Purpose | Prereqs |
|---|---|---|
| `01_reserve_node.ipynb` | Reserve Chameleon MI100, write inventory | `.env` with Chameleon credentials |
| `02_lerobot.ipynb` | Collect episodes → train ACT policy → fetch checkpoint | `01` complete |
| `03_talkbot.ipynb` | Install talkbot on Pi, configure voice coaching prompt | Pi reachable via SSH |
| `04_lerobot_talkbot.ipynb` | Combined voice-coached demonstration session | `02` + `03` complete |

**Agents must NOT author or modify notebooks.**

Agents MAY execute notebooks to verify student workflows:
```bash
just verify-all          # run all four notebooks via papermill
just verify-lerobot      # run 02_lerobot only
```

Each `just verify-*` recipe runs the notebook via **Papermill** and saves the executed output notebook to `bench/results/` — the output notebook is the benchmark artifact (timestamped, cell outputs preserved). Verification failures indicate infrastructure or configuration issues to fix at the operator layer.

### Notebook Conventions

- First cell: `load_dotenv(dotenv_path=Path('..') / '.env')` — all config from `.env`
- Second cell: bench timing scaffold (`_bench`, `_t0 = time.monotonic()`)
- Last cell: write `bench/results/<name>_<timestamp>.json`
- Use `tqdm.notebook` for any multi-step progress within a cell
- Cells that require live hardware (Pi, arm) use `# TODO:` stubs with the equivalent shell command printed for manual execution

## Operator Interface

`justfile` is the single operator entrypoint. All operator actions go through `just`:

```bash
just                     # list all recipes
just check-env           # verify .env is populated
just verify-all          # smoke-test all student notebooks
just provision           # run Ansible against current inventory
just ssh-node            # SSH to training node
just ssh-pi              # SSH to Pi edge node
just status              # check Chameleon lease + server
just bench-latest        # show most recent benchmark result
```

### Shared State (.env)

All notebooks and justfile recipes share project state via `.env`:

```bash
cp .env.example .env
# Fill in values — use `just dump-vault` to read from ansible vault
just dump-vault          # prints vault.yml contents for copy-paste
```

The `.env` file is gitignored. `.env.example` is the committed template.

## Tech Stack

- **Robot**: SO-ARM101, 6-DOF, Feetech STS3215 servos
- **Teleoperation**: xbox_soarm_teleop (sibling repo) with Xbox controller IK
- **Training Framework**: LeRobot v0.5.0 (HuggingFace)
- **Cloud**: Chameleon Cloud, CHI@TACC, MI100 bare-metal nodes
- **Cloud API**: python-chi 1.0+ (NOT the deprecated pre-1.0 functions)
- **GPU**: AMD Instinct MI100 (gfx908, CDNA1, 32 GB HBM2)
- **GPU Stack**: ROCm 6.3, PyTorch 2.7.1+rocm6.3
- **Provisioning**: Ansible (playbooks for node configuration)
- **Data Transfer**: HuggingFace Hub (datasets and checkpoints)
- **Edge Container**: Docker on Raspberry Pi 5 (CPU-only PyTorch)
- **Voice Interface**: ricklon/talkbot (STT + LLM + TTS, local-first, runs on Pi)
- **Notebook**: Jupyter on Chameleon JupyterHub
- **Notebook Verification**: Papermill (parameterized execution, output as benchmark artifact)
- **Config/Shared State**: python-dotenv (`.env` loaded by notebooks and justfile)
- **Python**: 3.12 (LeRobot v0.5.0 requirement)

## Project Structure

```
coachable-robots/
├── CLAUDE.md
├── AGENTS.md                         # Symlink → CLAUDE.md (for other agent frameworks)
├── README.md
├── justfile                          # Operator interface: verify-*, provision, ssh-node
├── .env.example                      # Shared project state template (copy to .env)
├── CoachableRobots_v3.ipynb          # Comprehensive operator reference notebook (all features)
├── notebooks/                        # Student learning path (operator verifies via papermill)
│   ├── 01_reserve_node.ipynb         # Reserve Chameleon MI100, write inventory
│   ├── 02_lerobot.ipynb              # LeRobot-only: collect → train → deploy
│   ├── 03_talkbot.ipynb              # Talkbot-only: voice coaching interface
│   └── 04_lerobot_talkbot.ipynb      # Combined: voice-coached demonstration session
├── ansible/
│   ├── ansible.cfg                   # SSH/timeout settings for bare metal
│   ├── inventory.yml.j2              # Inventory template
│   ├── inventory.ini                 # Auto-generated by 01_reserve_node / justfile
│   ├── README.md
│   └── playbooks/
│       └── setup_training_node.yml   # ROCm + LeRobot install playbook
├── docker/
│   ├── Dockerfile.pi                 # Pi 5 edge collector container
│   └── scripts/
│       ├── collect_demos.sh          # Teleoperate → record → push dataset
│       └── fetch_checkpoint.sh       # Pull trained policy from HF Hub
├── scripts/
│   ├── vault_to_env.py               # Decrypt vault → write .env + SSH keys
│   ├── reserve.py                    # Non-interactive Chameleon lease + server
│   └── check_auth.py                 # Live credential validation (Chameleon + HF)
├── bench/
│   ├── benchmark_inference.py        # Multi-target latency benchmark (runs locally or via SSH)
│   └── results/                      # JSON benchmark outputs (per device + per notebook run)
└── docs/
    ├── pi5-chi-edge-setup.md         # Pi 5 enrollment on CHI@Edge
    ├── platform-support.md           # Platform x input x simulation matrix
    └── chameleon-user-meeting/       # Presentation materials (April 2026)
```

## Related Repositories

| Repo | Role | Relationship |
|------|------|-------------|
| `ricklon/xbox_soarm_teleop` | Xbox controller teleoperation + IK | Installed in Pi Docker container; provides data collection |
| `ricklon/talkbot` | Local-first voice assistant (STT + LLM + TTS) | Runs on Pi alongside LeRobot; voice coaching interface |
| `huggingface/lerobot` | Training framework, dataset format, recording | Core dependency on both edge and cloud |
| `AMDResearch/Ryzers` | Docker framework for ROCm + LeRobot | Reference; we use Ansible instead |

## Chameleon Cloud Conventions

### python-chi 1.0+ API (CRITICAL)

The python-chi API changed significantly in 1.0. Always use the new patterns:

```python
# CORRECT — python-chi 1.0+ Lease class
from chi.lease import Lease

my_lease = Lease(name="coachable-robots-mi100", duration=timedelta(hours=6))
my_lease.add_node_reservation(node_type="gpu_mi100", amount=1)
my_lease.add_fip_reservation(amount=1)
my_lease.submit(wait_for_active=True, idempotent=True)

# Access reservations:
my_lease.node_reservations    # NOT my_lease['reservations']
my_lease.fip_reservations     # separate lists per type
my_lease.status               # NOT my_lease['status']
```

```python
# WRONG — deprecated pre-1.0 patterns (DO NOT USE)
chi.lease.create_lease(...)           # deprecated
chi.lease.get_node_reservation(...)   # deprecated
current_lease['reservations']         # Lease is not subscriptable
```

### Idempotent Resource Management

Never create duplicate leases or servers. Always check first:

```python
# Check existing before creating
existing = lease.get_lease(LEASE_NAME)
if existing and existing.status in ("ACTIVE", "PENDING"):
    my_lease = existing  # reuse
else:
    # create new, with idempotent=True as safety net
    my_lease = Lease(...)
    my_lease.submit(idempotent=True)
```

### Server Access

- Default user on Chameleon bare metal: `cc` (not `root`, not `ubuntu`)
- SSH key lives at `/work/.ssh/id_rsa` on the Chameleon Jupyter server
- Must register key pair with Nova before first server launch
- MI100 is AMD — use `rocm-smi` and `lspci`, NEVER `nvidia-smi`

## MI100 GPU Constraints (gfx908)

These constraints affect policy selection and training configuration:

- **Flash Attention 2**: NOT supported (requires gfx90a / MI210+)
- **hipBLASLt**: NOT available on gfx908
- **VRAM**: 32 GB HBM2 — sufficient for ACT/Diffusion, tight for Pi0 3B
- **ROCm support**: Supported through ROCm 7.1.x on Ubuntu 22.04/24.04
- **Recommended policy**: ACT (no Flash Attention dependency)
- **Pi0 workarounds**: `--policy.gradient_checkpointing=true --policy.dtype=bfloat16 --batch_size=8`
- **PyTorch target**: Build/install with gfx908 explicitly

## Ansible Playbook Conventions

- Playbooks live in `ansible/playbooks/`
- Config in `ansible/ansible.cfg` (host_key_checking disabled, pipelining on)
- Inventory is auto-generated by the notebook with the floating IP
- Every task must be idempotent — check before act (stat, command+ignore_errors)
- ROCm install checks `rocm-smi --version` before downloading anything
- Conda env checks `conda env list` output before creating
- All user-space tasks use `become: false` (run as `cc`, not root)

## LeRobot Integration Points

### Data Collection (Pi Edge)

```bash
lerobot-record \
    --robot.type=so101_follower \
    --robot.cameras="{ top: {type: opencv, index_or_path: 0, ...}, side: {...} }" \
    --teleop.type=so101_leader \
    --dataset.repo_id=USER/dataset_name \
    --dataset.num_episodes=50 \
    --dataset.push_to_hub=true
```

### Training (MI100 Cloud)

```bash
conda activate lerobot
python lerobot/scripts/train.py \
    --dataset.repo_id=USER/dataset_name \
    --policy.path=lerobot/act \
    --policy.device=cuda \
    --output_dir=outputs/train/act_run1
```

### Inference (Pi Edge)

```bash
lerobot-record \
    --policy.path=/app/checkpoints/latest \
    --dataset.single_task="Pick up the block" \
    ...
```

## Data Flow

1. **Collect**: Pi runs `lerobot-record` with Xbox teleop → episodes saved locally
2. **Push**: `--dataset.push_to_hub=true` uploads to HuggingFace Hub
3. **Train**: MI100 node pulls dataset by `repo_id`, trains policy, saves checkpoints
4. **Upload**: `hf upload` pushes checkpoint to HF Hub
5. **Fetch**: Pi runs `hf download` to pull trained policy
6. **Deploy**: Pi runs `lerobot-record --policy.path=...` for autonomous execution

HuggingFace Hub is the transfer layer — no custom transfer code, no Chameleon Object Store needed for runtime data (Object Store is for Trovi experiment packaging).

## Benchmarking (coachable-robots-bench)

The benchmarking framework measures inference latency and training throughput across hardware tiers:

| Tier | Hardware | Metrics |
|------|----------|---------|
| Edge | Raspberry Pi 5 (CPU) | Inference latency (p50, p99) |
| Desktop | Local GPU/CPU | Inference + training time |
| Cloud vGPU | Chameleon MI100 | Training throughput, inference latency |
| Cloud HPC | Chameleon H100 | Large VLA training (Pi0), inference |

Benchmark results are JSON files in `bench/results/` with device name, PyTorch version, input shapes, and timing distributions.

## Docker Conventions (Pi Edge)

- Base image: `python:3.12-slim-bookworm`
- PyTorch: CPU-only wheels (`--index-url .../whl/cpu`)
- Must run with `--privileged -v /dev:/dev` for camera and serial passthrough
- HF token passed as environment variable, never baked into image
- Container installs both `lerobot` and `xbox_soarm_teleop`

## Development Commands

```bash
# === Operator (justfile) ===
just                          # list all recipes
just check-env                # verify .env is populated
just dump-vault               # view ansible vault secrets for .env copy-paste
just verify-all               # smoke-test all student notebooks via papermill
just provision                # run Ansible against current inventory
just ssh-node                 # SSH to training node
just ssh-pi                   # SSH to Pi edge node
just tunnel                   # SSH tunnel → JupyterLab on http://localhost:8888
just status                   # check Chameleon lease + server
just bench-latest             # show most recent benchmark result

# === Notebook Verification (what just verify-* runs) ===
papermill notebooks/01_reserve_node.ipynb bench/results/01_reserve_node_$(date +%Y%m%d_%H%M%S).ipynb

# === On the MI100 Node ===
conda activate lerobot
rocm-smi                      # verify GPU
python -c "import torch; print(torch.cuda.get_device_name(0))"

# === On the Pi (inside Docker) ===
docker run -it --privileged -v /dev:/dev -e HF_TOKEN=hf_xxx coachable-robots-pi
bash scripts/collect_demos.sh my_dataset 50
bash scripts/fetch_checkpoint.sh USER/my_model

# === Talkbot on Pi ===
ssh -p 22222 root@<pi-ip>
tmux new-session -d -s talkbot 'cd ~/talkbot && TALKBOT_AGENT_PROMPT="..." uv run talkbot'
```

## Constraints and Conventions

### Pedagogical Framing

This project frames imitation learning as "coaching" — students show the robot what to do through demonstration, not programming. The Xbox controller is the coaching interface. Language in docs, presentations, and UI should reinforce this metaphor:
- "Coach the robot" not "program the robot"
- "Demonstration episodes" not "training samples"
- "The robot learned from your coaching" not "the model converged"

### Code Conventions

- `justfile` for operator actions — single entrypoint, all infra operations go through `just`
- `notebooks/` for student workflows — stubs only, content authored by humans not agents
- `CoachableRobots_v3.ipynb` is the operator reference — comprehensive, not decomposed
- Ansible for infrastructure provisioning (not bash scripts over SSH)
- Python 3.12 (LeRobot v0.5.0 requirement)
- Markdown for all documentation (not docx unless explicitly requested)
- `pyproject.toml` for Python projects (uv as package manager where applicable)
- Ruff for linting/formatting

### Safety

- Idempotent everything — notebooks, Ansible, Docker builds
- Always check for existing Chameleon resources before creating
- Cleanup cells require explicit confirmation (`input('yes')`)
- Never hardcode HF tokens or SSH keys in committed files
- Lease duration defaults should be conservative (6h, not 24h)
- `.env` is gitignored — secrets live there, not in committed files
- `.env.example` is the committed template — all keys present, no real values

## Reference Resources

- **LeRobot docs**: https://huggingface.co/docs/lerobot
- **LeRobot SO-101 tutorial**: https://huggingface.co/docs/lerobot/so101
- **python-chi 1.0 docs**: https://python-chi.readthedocs.io/en/latest/
- **Chameleon getting started**: https://chameleoncloud.readthedocs.io/en/latest/getting-started/
- **ROCm MI100 compat**: https://rocm.docs.amd.com/en/latest/compatibility/compatibility-matrix.html
- **AMD LeRobot blog**: https://rocm.blogs.amd.com/artificial-intelligence/rocm-lerobot/README.html
- **AMD edge-to-cloud blog**: https://rocm.blogs.amd.com/artificial-intelligence/rocm-blogsblogsartificial-in/README.html
- **xbox_soarm_teleop**: https://github.com/ricklon/xbox_soarm_teleop
- **SO-ARM100 hardware**: https://github.com/TheRobotStudio/SO-ARM100

## Troubleshooting

### Chameleon lease errors

```python
# "Lease object is not subscriptable"
# You're using pre-1.0 dict syntax. Use attribute access:
my_lease.node_reservations    # not my_lease['reservations']
my_lease.status               # not my_lease['status']
```

### "Invalid key_name provided" on server creation

```python
# Key pair not registered with Nova at this site. Upload it:
from chi import clients
nova = clients.nova()
with open("/work/.ssh/id_rsa.pub") as f:
    nova.keypairs.create(name="rick_rutgers", public_key=f.read())
```

### ROCm not detecting MI100 after install

```bash
# May need a reboot after ROCm install
sudo reboot
# Then verify:
rocm-smi
rocminfo | grep gfx    # should show gfx908
```

### PyTorch says CUDA not available on MI100

```bash
# Ensure ROCm PyTorch wheels, not CUDA wheels:
pip install torch==2.7.1 --index-url https://download.pytorch.org/whl/rocm6.3
python -c "import torch; print(torch.cuda.is_available())"  # True on ROCm too
```

### Ansible "unreachable" on fresh bare-metal node

```bash
# Bare metal takes 5-15 min to image + boot. Wait for SSH:
ssh -o StrictHostKeyChecking=no cc@<ip> echo ok
# If still failing, check Chameleon dashboard for server status
```

### Pi Docker can't see cameras or serial ports

```bash
# Must run privileged with /dev mounted:
docker run -it --privileged -v /dev:/dev coachable-robots-pi
# Inside container, verify:
ls /dev/video*      # cameras
ls /dev/ttyACM*     # servo controller
```
