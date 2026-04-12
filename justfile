# justfile — Coachable Robots operator interface
#
# Single entrypoint for human operators and AI agents.
# Every recipe is non-interactive and safe to call from automation.
#
# Prerequisites: just, uv, ansible, papermill, jupyter
#   uv tool install just  (or: cargo install just)
#   uv sync               (installs all Python deps including papermill)
#
# Quickstart:
#   echo 'vault-password' > ansible/.vault_pass && chmod 600 ansible/.vault_pass
#   just setup            # vault → .env → check-auth → provision
#   just ready            # full system health check
#   just verify-all       # run all student notebooks as acceptance tests

set dotenv-load := true

_default:
    @just --list

# ── Bootstrap ─────────────────────────────────────────────────────────────────

# Full setup from scratch: vault → .env → auth check → provision node
setup: vault-to-env check-auth provision
    @echo "Setup complete. Run 'just ready' to verify."

# Decrypt ansible vault and write .env (requires ansible/.vault_pass)
vault-to-env:
    uv run python scripts/vault_to_env.py

# Dry-run vault-to-env: show what would be written without writing
vault-to-env-dry:
    uv run python scripts/vault_to_env.py --dry-run

# Show vault contents (for manual inspection or copy-paste)
dump-vault:
    ansible-vault view ansible/group_vars/all/vault.yml \
        --vault-password-file ansible/.vault_pass

# ── Credentials ───────────────────────────────────────────────────────────────

# Validate .env exists and has no placeholder values
check-env:
    @test -f .env || (echo "ERROR: .env not found — run 'just vault-to-env' first" && exit 1)
    @python -c "\
import os; from dotenv import load_dotenv; load_dotenv(); \
bad = [k for k,v in os.environ.items() if 'REPLACE_ME' in str(v) or 'your_hf_username' in str(v)]; \
print('Placeholders found: ' + ', '.join(bad)) if bad else print('ENV: no placeholders')"

# Test live credentials against Chameleon API and HuggingFace (exits 1 on failure)
check-auth: check-env
    uv run python scripts/check_auth.py

# Same as check-auth but output as JSON (for agent parsing)
check-auth-json: check-env
    uv run python scripts/check_auth.py --json

# ── Infrastructure ────────────────────────────────────────────────────────────

# Reserve Chameleon MI100 node, wait for SSH, write inventory.ini (non-interactive)
reserve: check-auth
    uv run python scripts/reserve.py

# Show current lease + server state as JSON (exits 2 if not SSH-ready)
node-status:
    uv run python scripts/reserve.py --status

# Release lease and server (requires COACHABLE_CONFIRM_RELEASE=yes)
release:
    uv run python scripts/reserve.py --release

# Run Ansible provisioning (ROCm + LeRobot) against current inventory
provision: check-env
    ansible-playbook \
        -i ansible/inventory.ini \
        ansible/playbooks/setup_training_node.yml

# Provision the KVM control node
provision-control: check-env
    ansible-playbook \
        -i "${CONTROL_FLOATING_IP}," \
        -u cc \
        --private-key ~/.ssh/id_rsa \
        ansible/playbooks/setup_control_node.yml

# ── System Health ─────────────────────────────────────────────────────────────

# Test training node: SSH + GPU + ROCm + PyTorch
test-node: check-env
    @echo "=== Node SSH ==="
    ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 cc@${CONTROL_FLOATING_IP} "echo ok"
    @echo "=== OS ==="
    ssh -o StrictHostKeyChecking=no cc@${CONTROL_FLOATING_IP} "lsb_release -ds"
    @echo "=== AMD GPU ==="
    ssh -o StrictHostKeyChecking=no cc@${CONTROL_FLOATING_IP} \
        "lspci | grep -i 'amd\|arcturus' || echo 'no AMD GPU in lspci'"
    @echo "=== ROCm ==="
    ssh -o StrictHostKeyChecking=no cc@${CONTROL_FLOATING_IP} \
        "rocm-smi --version 2>/dev/null || echo 'ROCm not installed'"
    @echo "=== PyTorch ==="
    ssh -o StrictHostKeyChecking=no cc@${CONTROL_FLOATING_IP} \
        "source ~/miniconda3/bin/activate lerobot 2>/dev/null && \
         python -c 'import torch; print(torch.__version__, torch.cuda.is_available())' \
         || echo 'lerobot env not ready'"

# Test Pi edge node: SSH + serial ports + cameras + containers
test-pi: check-env
    @echo "=== Pi SSH ==="
    ssh -p ${PI_PORT} -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
        root@${PI_HOST} "echo ok && uname -m"
    @echo "=== Serial Ports ==="
    ssh -p ${PI_PORT} -o StrictHostKeyChecking=no root@${PI_HOST} \
        "ls /dev/ttyACM* 2>/dev/null || echo 'NO SERIAL PORTS'"
    @echo "=== Cameras ==="
    ssh -p ${PI_PORT} -o StrictHostKeyChecking=no root@${PI_HOST} \
        "ls /dev/video0 /dev/video2 2>/dev/null && echo 'cameras OK' || echo 'cameras NOT FOUND'"
    @echo "=== Containers ==="
    ssh -p ${PI_PORT} -o StrictHostKeyChecking=no root@${PI_HOST} \
        "balena ps 2>/dev/null || docker ps 2>/dev/null || echo 'no container runtime'"

# Full system health check: auth + node + pi
test-all: check-auth test-node test-pi
    @echo "=== All checks passed ==="

# Full readiness check: health + verify student notebooks
ready: test-all verify-all
    @echo "=== System ready for student sessions ==="

# ── Arm Operations ────────────────────────────────────────────────────────────

# Verify Pi serial ports and cameras are present (non-interactive)
test-arm: check-env
    @echo "=== Serial Ports ==="
    ssh -p ${PI_PORT} -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
        root@${PI_HOST} "ls /dev/ttyACM* 2>/dev/null || echo 'NO SERIAL PORTS'"
    @echo "=== Cameras ==="
    ssh -p ${PI_PORT} -o StrictHostKeyChecking=no root@${PI_HOST} \
        "ls /dev/video0 /dev/video2 2>/dev/null && echo 'cameras OK' || echo 'cameras NOT FOUND'"
    @echo "=== Calibration ==="
    ssh -p ${PI_PORT} -o StrictHostKeyChecking=no root@${PI_HOST} \
        "ls /mnt/data/calibration/*.json 2>/dev/null | wc -l | xargs -I{} echo '{} calibration file(s)'"

# Replay a reference animation on the follower arm: just replay-ref repo=USER/soarm101-touch-block-reference episode=0
replay-ref repo episode="0": check-env
    ssh -p ${PI_PORT} -t -o StrictHostKeyChecking=no root@${PI_HOST} \
        "balena run -it --privileged \
         --device=/dev/ttyACM1 \
         -v /mnt/data/calibration:/app/calibration \
         -v /mnt/data/datasets:/app/data \
         ${HF_USER}/lerobot-soarm101:latest \
         lerobot-replay \
           --robot.type=so101_follower --robot.port=/dev/ttyACM1 \
           --robot.id=alpha_follower \
           --robot.calibration_dir=/app/calibration \
           --dataset.repo_id={{repo}} \
           --dataset.episode={{episode}} \
           --play_sounds=false"

# Verify arm setup notebook (00_arm_setup)
verify-arm: check-env
    papermill \
        notebooks/00_arm_setup.ipynb \
        bench/results/00_arm_setup_{{_ts}}.ipynb \
        --log-output

# Verify touch coaching notebook (05_touch_objects)
verify-touch: check-env
    papermill \
        notebooks/05_touch_objects.ipynb \
        bench/results/05_touch_objects_{{_ts}}.ipynb \
        --log-output

# Verify pick-and-place coaching notebook (06_pick_place)
verify-pick: check-env
    papermill \
        notebooks/06_pick_place.ipynb \
        bench/results/06_pick_place_{{_ts}}.ipynb \
        --log-output

# ── Benchmarks ────────────────────────────────────────────────────────────────
#
# benchmark_inference.py runs on the target machine and outputs JSON.
# Results are tee'd to bench/results/ locally and printed to stdout.
# Use --tag to label the device in filenames and results.

_ts := `date +%Y%m%d_%H%M%S`

# Run inference benchmark on the MI100 training node
bench-inference-node: check-env
    @echo "Running inference benchmark on MI100 node (${CONTROL_FLOATING_IP})..."
    ssh -o StrictHostKeyChecking=no cc@${CONTROL_FLOATING_IP} \
        "source ~/miniconda3/bin/activate lerobot 2>/dev/null; \
         python ~/coachable-robots/bench/benchmark_inference.py --tag mi100 --no-save" \
        | tee bench/results/bench_inference_mi100_{{_ts}}.json

# Run inference benchmark on the Pi edge node
bench-inference-pi: check-env
    @echo "Running inference benchmark on Pi (${PI_HOST})..."
    ssh -p ${PI_PORT} -o StrictHostKeyChecking=no root@${PI_HOST} \
        "python ~/benchmark_inference.py --tag pi5 --no-save" \
        | tee bench/results/bench_inference_pi5_{{_ts}}.json

# Run inference benchmark locally
bench-inference-local:
    @echo "Running inference benchmark locally..."
    uv run python bench/benchmark_inference.py --tag local

# Run benchmark on a named remote target: just bench-inference-remote host=user@ip tag=h100
bench-inference-remote host tag:
    @echo "Running inference benchmark on {{host}} (tag: {{tag}})..."
    ssh -o StrictHostKeyChecking=no {{host}} \
        "python ~/coachable-robots/bench/benchmark_inference.py --tag {{tag}} --no-save" \
        | tee bench/results/bench_inference_{{tag}}_{{_ts}}.json

# Run all benchmarks (node + pi + local) and save results
bench-all: bench-inference-node bench-inference-pi bench-inference-local
    @just bench-summary

# Print a comparison table of the most recent result per tag
bench-summary:
    @python -c "\
import json, glob, os; \
files = sorted(glob.glob('bench/results/bench_inference_*.json'), key=os.path.getmtime); \
seen = {}; \
[seen.update({json.load(open(f)).get('tag','?'): f}) for f in files]; \
print(f\"{'tag':<12} {'device':<30} {'p50_matmul_512':>16} {'p50_224':>12}\"); \
print('-' * 72); \
[print(f\"{d.get('tag','?'):<12} {d.get('device',{}).get('device_name','?')[:30]:<30} \
{next((b.get('p50_ms','?') for b in d.get('benchmarks',[]) if b.get('name')=='matmul_512'),'?'):>16} \
{next((b.get('p50_ms','?') for b in d.get('benchmarks',[]) if b.get('name')=='policy_input_224'),'?'):>12}\") \
for d in [json.load(open(f)) for f in seen.values()]]" 2>/dev/null || echo "No benchmark results yet"

# List all benchmark result files
bench-list:
    @ls -lt bench/results/*.json 2>/dev/null | head -20 || echo "No benchmark results yet"

# Show the latest benchmark result
bench-latest:
    @ls -t bench/results/*.json 2>/dev/null | head -1 | xargs cat || echo "No benchmark results yet"

# ── Verification (notebooks as acceptance tests) ───────────────────────────────
#
# Executes student notebooks via Papermill.
# The output notebook (with cell results) is the benchmark artifact.

# Verify: reserve Chameleon node workflow (01_reserve_node)
verify-reserve: check-env
    papermill \
        notebooks/01_reserve_node.ipynb \
        bench/results/01_reserve_node_{{_ts}}.ipynb \
        --log-output

# Verify: LeRobot-only training workflow (02_lerobot)
verify-lerobot: check-env
    papermill \
        notebooks/02_lerobot.ipynb \
        bench/results/02_lerobot_{{_ts}}.ipynb \
        --log-output

# Verify: Talkbot-only voice interface (03_talkbot)
verify-talkbot: check-env
    papermill \
        notebooks/03_talkbot.ipynb \
        bench/results/03_talkbot_{{_ts}}.ipynb \
        --log-output

# Verify: Combined LeRobot + Talkbot session (04_lerobot_talkbot)
verify-combined: check-env
    papermill \
        notebooks/04_lerobot_talkbot.ipynb \
        bench/results/04_lerobot_talkbot_{{_ts}}.ipynb \
        --log-output

# Run all verification notebooks in sequence
verify-all: verify-arm verify-reserve verify-lerobot verify-talkbot verify-combined verify-touch verify-pick

# ── Access ────────────────────────────────────────────────────────────────────

# SSH to the training node
ssh-node: check-env
    ssh cc@${CONTROL_FLOATING_IP}

# SSH to the Pi edge node
ssh-pi: check-env
    ssh -p ${PI_PORT} root@${PI_HOST}

# Open SSH tunnel to JupyterLab on the control node → http://localhost:8888
tunnel: check-env
    @echo "Tunneling JupyterLab → http://localhost:8888"
    ssh -L 8888:localhost:8888 cc@${CONTROL_FLOATING_IP}
