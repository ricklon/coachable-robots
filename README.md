# Coachable Robots — Ansible Training Node Setup

Configures a Chameleon Cloud MI100 bare-metal node with ROCm + LeRobot
for policy training.

## Structure

```
ansible/
├── ansible.cfg                        # SSH and timeout settings
├── inventory.yml.j2                   # Template — fill in floating_ip
├── playbooks/
│   └── setup_training_node.yml        # Main playbook
└── README.md
```

## Usage

### From Chameleon Jupyter (after provisioning the node)

```bash
# Quick: pass the IP directly, skip inventory file
ansible-playbook \
  -i "129.114.x.x," \
  -u cc \
  --private-key /work/.ssh/id_rsa \
  playbooks/setup_training_node.yml
```

### From the notebook

```python
import subprocess
result = subprocess.run(
    ["ansible-playbook",
     "-i", f"{floating_ip},",
     "-u", "cc",
     "--private-key", "/work/.ssh/id_rsa",
     "playbooks/setup_training_node.yml"],
    capture_output=True, text=True,
    cwd="/work/coachable-robots/ansible"
)
print(result.stdout)
if result.returncode != 0:
    print(result.stderr)
```

### With a proper inventory file

```bash
# Edit inventory.yml with your floating IP, then:
ansible-playbook playbooks/setup_training_node.yml
```

## What it installs

1. **System deps** — build tools, headers, tmux, htop
2. **ROCm 6.3** — AMD GPU driver + compute stack (skips if already installed)
3. **Miniconda** — Python environment manager (skips if already installed)
4. **PyTorch 2.7.1+rocm6.3** — in a `lerobot` conda environment
5. **LeRobot v0.4.1** — HuggingFace robotics framework
6. **HuggingFace CLI** — for dataset/checkpoint push/pull

## Idempotent

Every task checks before acting. Safe to re-run — it will skip
anything already in place and only install what's missing.

## MI100 (gfx908) Notes

- No Flash Attention 2 (requires gfx90a+)
- No hipBLASLt
- 32 GB HBM2 — ACT/Diffusion Policy run fine, Pi0 needs gradient
  checkpointing + bf16 + small batch size
- `rocm-smi` not `nvidia-smi`
