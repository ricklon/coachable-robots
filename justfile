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
    @python scripts/check_env.py

# Test live credentials against Chameleon API and HuggingFace (exits 1 on failure)
check-auth: check-env
    uv run python scripts/check_auth.py

# Test only Chameleon credentials required for lease/server operations
check-chameleon:
    uv run python scripts/check_auth.py --only chameleon

# Same as check-auth but output as JSON (for agent parsing)
check-auth-json: check-env
    uv run python scripts/check_auth.py --json

# ── Infrastructure ────────────────────────────────────────────────────────────

# Reserve Chameleon MI100 node, wait for SSH, write inventory.ini (non-interactive)
reserve: check-chameleon
    uv run python scripts/reserve.py

# Reserve CHI@Edge SO-ARM101 device, launch LeRobot container, assign floating IP
reserve-edge:
    uv run python scripts/reserve_edge.py

# Reserve only the CHI@Edge SO-ARM101 device lease
reserve-edge-lease:
    uv run python scripts/reserve_edge.py --lease-only

# Delete and recreate the arm-01 container (keeps lease; picks up .env changes)
restart-arm:
    uv run python scripts/reserve_edge.py --restart-container --no-fip

# Show current CHI@Edge SO-ARM101 lease/container state as JSON
edge-status:
    uv run python scripts/reserve_edge.py --status

# Show CHI@Edge device enrollment and health details
edge-device-show:
    bash -lc 'source "${EDGE_RC_FILE:-ansible/app-cred-chi-edge-openrc.sh}" && unset OS_PROJECT_ID OS_PROJECT_NAME OS_PROJECT_DOMAIN_ID OS_PROJECT_DOMAIN_NAME && uv run chi-edge device show "${EDGE_DEVICE_NAME:-soarm101-1}"'

# Show current lease + server state as JSON (exits 2 if not SSH-ready)
node-status:
    uv run python scripts/reserve.py --status

# Release CHI@Edge SO-ARM101 container and lease (requires COACHABLE_CONFIRM_RELEASE=yes)
release-edge:
    uv run python scripts/reserve_edge.py --release

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

# Join this machine to the tailnet (runs locally)
provision-tailscale-local:
    ansible-playbook \
        -i "localhost," -c local \
        ansible/playbooks/setup_tailscale.yml \
        -e "ts_authkey=${TS_AUTHKEY}" \
        -e "ts_hostname=coachable-robots-control"

# Join the MI100 training node to the tailnet
provision-tailscale-node: check-env
    ansible-playbook \
        -i ansible/inventory.ini --limit mi100 \
        ansible/playbooks/setup_tailscale.yml \
        -e "ts_authkey=${TS_AUTHKEY}" \
        -e "ts_hostname=coachable-robots-mi100"

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

# ── Arm Operations (fleet: arm-01, arm-02, ...) ───────────────────────────────
#
# PI_HOST / PI_PORT in .env control which arm node is targeted.
# Default: PI_HOST=arm-01, PI_PORT=22  (Tailscale — no floating IP needed)
# Override per-call: just arm-ssh PI_HOST=arm-02

# SSH into the arm node (via Tailscale by default)
arm-ssh: check-env
    ssh root@${PI_HOST}

# Run a command on the arm node: just arm-exec cmd="ls /dev/ttyACM*"
arm-exec cmd: check-env
    ssh -p ${PI_PORT} -o StrictHostKeyChecking=no root@${PI_HOST} "{{cmd}}"

# Verify arm node: SSH + serial ports + cameras + tailscale
arm-test: check-env
    @echo "=== SSH ==="
    ssh -p ${PI_PORT} -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
        root@${PI_HOST} "echo ok && uname -m && hostname"
    @echo "=== Tailscale ==="
    ssh -p ${PI_PORT} -o StrictHostKeyChecking=no root@${PI_HOST} \
        "tailscale status 2>/dev/null || echo 'tailscale not running'"
    @echo "=== Serial Ports ==="
    ssh -p ${PI_PORT} -o StrictHostKeyChecking=no root@${PI_HOST} \
        "ls /dev/ttyACM* 2>/dev/null || echo 'NO SERIAL PORTS'"
    @echo "=== Cameras ==="
    ssh -p ${PI_PORT} -o StrictHostKeyChecking=no root@${PI_HOST} \
        "ls /dev/video0 /dev/video2 2>/dev/null && echo 'cameras OK' || echo 'cameras NOT FOUND'"
    @echo "=== Calibration ==="
    ssh -p ${PI_PORT} -o StrictHostKeyChecking=no root@${PI_HOST} \
        "ls /mnt/data/calibration/*.json 2>/dev/null | wc -l | xargs -I{} echo '{} calibration file(s)'"

# Collect demonstration episodes on the arm node: just arm-collect dataset=touch-block episodes=20
arm-collect dataset episodes="20": check-env
    ssh -p ${PI_PORT} -t -o StrictHostKeyChecking=no root@${PI_HOST} \
        "lerobot-record \
           --robot.type=so101_follower --robot.port=/dev/ttyACM1 \
           --teleop.type=so101_leader  --teleop.port=/dev/ttyACM0 \
           --dataset.repo_id=${HF_USER}/{{dataset}} \
           --dataset.num_episodes={{episodes}} \
           --dataset.push_to_hub=true"

# Calibrate the arm: just arm-calibrate
arm-calibrate: check-env
    ssh -p ${PI_PORT} -t -o StrictHostKeyChecking=no root@${PI_HOST} \
        "lerobot-calibrate \
           --robot.type=so101_follower --robot.port=/dev/ttyACM1 \
           --robot.id=alpha_follower \
           --robot.calibration_dir=/mnt/data/calibration"

# Replay a reference episode on the follower arm: just arm-replay repo=USER/soarm101-touch-block episode=0
arm-replay repo episode="0": check-env
    ssh -p ${PI_PORT} -t -o StrictHostKeyChecking=no root@${PI_HOST} \
        "lerobot-replay \
           --robot.type=so101_follower --robot.port=/dev/ttyACM1 \
           --robot.id=alpha_follower \
           --robot.calibration_dir=/mnt/data/calibration \
           --dataset.repo_id={{repo}} \
           --dataset.episode={{episode}} \
           --play_sounds=false"

# Open SSH tunnel to arm-01 Gradio UI -> http://localhost:7860
tunnel-arm: check-env
    @echo "Tunneling arm Gradio UI -> http://localhost:7860"
    ssh -L 7860:localhost:7860 -p ${PI_PORT} root@${PI_HOST}

# ── Talkbot ───────────────────────────────────────────────────────────────────
#
# Best CPU-only model (from benchmarks): qwen3.5-0.8b-q8_0 — 90% success, 100%
# tool selection, ~1.4s latency (m3max bench; Pi5 will be ~5–8x slower).
#
# Local server backend (default): llama-cpp-python[server] on port 8000
#   uv run python -m llama_cpp.server --model models/qwen3.5-0.8b-q8_0.gguf
#
# Ollama alternative: ollama serve (port 11434)
#   Set TALKBOT_LOCAL_SERVER_URL=http://127.0.0.1:11434/v1 in .env

# Start talkbot Gradio UI on this machine (requires local llama-server on :8000)
talkbot-serve:
    cd ~/talkbot && uv run talkbot serve \
        --host 0.0.0.0 \
        --port 7860

# Start talkbot Gradio UI on arm-01 via SSH and tunnel to localhost:7860
talkbot-arm: check-env
    @echo "Starting talkbot on arm-01, tunneling to http://localhost:7860"
    ssh -L 7860:localhost:7860 root@${PI_HOST} \
        "cd ~/talkbot && tmux new-session -d -s talkbot 'uv run talkbot serve --no-tts' 2>/dev/null; echo talkbot started"

# Send a single chat message to talkbot (no voice): just talkbot-chat msg="Hello"
talkbot-chat msg: check-env
    cd ~/talkbot && uv run talkbot --no-speak chat "{{msg}}"

# Start talkbot on arm-01 in a tmux session with voice coaching prompt
talkbot-arm-start: check-env
    ssh root@${PI_HOST} \
        "cd ~/talkbot && tmux kill-session -t talkbot 2>/dev/null; \
         tmux new-session -d -s talkbot \
           'TALKBOT_AGENT_PROMPT=\"${TALKBOT_AGENT_PROMPT}\" uv run talkbot serve'"
    @echo "TalkBot started on arm-01. Run: just tunnel-arm to access UI."

# Stop talkbot tmux session on arm-01
talkbot-arm-stop: check-env
    ssh root@${PI_HOST} "tmux kill-session -t talkbot 2>/dev/null; echo stopped"

# ── Legacy aliases (old pi-* / balena-based recipes) ──────────────────────────
# These target the same PI_HOST/PI_PORT but use the old balena runtime.
# Use arm-* recipes above for CHI@Edge / Tailscale deployments.

# Verify Pi serial ports and cameras are present (non-interactive)
test-arm: arm-test

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
    @python scripts/bench_summary.py

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

# ── Docker Image Builds (channels/) ──────────────────────────────────────────
#
# Images are tagged with a date to bust CHI@Edge's k8s image cache.
# image_pull_policy=always is forbidden (HTTP 403) — dated tags are required.
#
# After building, push and update EDGE_IMAGE_REF in .env, then just restart-arm.

_date := `date +%Y%m%d`

# Build arm base image (app + openssh + Tailscale)
build-arm:
    docker buildx build --platform linux/arm64 \
        -t rianders/lerobot-soarm101:arm \
        -t rianders/lerobot-soarm101:arm-{{_date}} \
        -f channels/arm/Dockerfile .

# Build and push arm base image
push-arm: build-arm
    docker push rianders/lerobot-soarm101:arm
    docker push rianders/lerobot-soarm101:arm-{{_date}}
    @echo "Pushed: rianders/lerobot-soarm101:arm-{{_date}}"

# Build arm-talk image (arm + llama-server + talkbot + Gradio)
build-arm-talk:
    docker buildx build --platform linux/arm64 \
        -t rianders/lerobot-soarm101:arm-talk \
        -t rianders/lerobot-soarm101:arm-talk-{{_date}} \
        -f channels/arm-talk/Dockerfile .

# Build and push arm-talk image with dated tag
push-arm-talk: build-arm-talk
    docker push rianders/lerobot-soarm101:arm-talk-{{_date}}
    @echo "Pushed: rianders/lerobot-soarm101:arm-talk-{{_date}}"
    @echo "Update .env: EDGE_IMAGE_REF=rianders/lerobot-soarm101:arm-talk-{{_date}}"
    @echo "Then run: just restart-arm"

# Build and push the full channel stack: arm base then arm-talk
push-all-channels: push-arm push-arm-talk

# ── Access ────────────────────────────────────────────────────────────────────

# SSH to the training node
ssh-node: check-env
    ssh cc@${CONTROL_FLOATING_IP}

# SSH to the arm edge node (alias for arm-ssh)
ssh-pi: check-env
    ssh -p ${PI_PORT} root@${PI_HOST}

# Open SSH tunnel to JupyterLab on the control node → http://localhost:8888
tunnel: check-env
    @echo "Tunneling JupyterLab → http://localhost:8888"
    ssh -L 8888:localhost:8888 cc@${CONTROL_FLOATING_IP}
