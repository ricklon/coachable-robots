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

# ── Dynamic Tailscale hostname resolution ─────────────────────────────────────
# Finds the currently-online arm-* node on the tailnet at recipe execution time.
# Falls back to PI_HOST from .env if tailscale is unavailable or no node is online.
# This means PI_HOST never needs manual updating after a container restart.
_arm_host := `python3 -c "
import subprocess, json, os, sys
try:
    out = subprocess.check_output(['tailscale','status','--json'], stderr=subprocess.DEVNULL)
    peers = json.loads(out).get('Peer', {}).values()
    # HostName is always the advertised name (e.g. 'arm-01'); suffix only in DNSName.
    # Strip the .tail*.ts.net. suffix to get the short hostname (e.g. 'arm-01-5').
    online = []
    for p in peers:
        if p.get('Online') and p.get('HostName','').startswith('arm-'):
            dns = p.get('DNSName','').split('.')[0]  # e.g. 'arm-01-5'
            if dns:
                online.append(dns)
    if online:
        print(sorted(online)[-1]); sys.exit(0)
except Exception:
    pass
print(os.environ.get('PI_HOST','arm-01'))
" 2>/dev/null || echo "${PI_HOST:-arm-01}"`

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

# ── Jetson AGX Orin (talkbot inference node) ──────────────────────────────────

# Create talkbot-orin-container on CHI@Edge Jetson (lease must exist; set JETSON_LEASE_ID in .env)
reserve-jetson:
    uv run python scripts/reserve_jetson.py

# Show current Jetson lease/container/tailscale state as JSON
jetson-status:
    uv run python scripts/reserve_jetson.py --status

# Delete and recreate the Jetson container (keeps lease; picks up .env changes)
restart-jetson:
    uv run python scripts/reserve_jetson.py --restart-container

# Assign a floating IP to the running Jetson container (enables outbound internet)
assign-jetson-fip:
    uv run python scripts/reserve_jetson.py --assign-fip

# Execute a command in the Jetson container via Zun API (no SSH/Tailscale needed)
# Usage: just jetson-zun-exec cmd="ls /dev/nvidia*"
jetson-zun-exec cmd="":
    uv run python scripts/reserve_jetson.py --exec "{{cmd}}"

# SSH into talkbot-orin via Tailscale
jetson-ssh:
    ssh root@${JETSON_TS_HOSTNAME:-talkbot-orin}

# Run a command on the Jetson via SSH
jetson-exec cmd="":
    ssh root@${JETSON_TS_HOSTNAME:-talkbot-orin} "{{cmd}}"

# Release Jetson container and lease (requires COACHABLE_CONFIRM_RELEASE=yes)
release-jetson:
    uv run python scripts/reserve_jetson.py --release

# Show CHI@Edge device enrollment and health details
edge-device-show:
    bash -lc 'source "${EDGE_RC_FILE:-ansible/app-cred-chi-edge-openrc.sh}" && unset OS_PROJECT_ID OS_PROJECT_NAME OS_PROJECT_DOMAIN_ID OS_PROJECT_DOMAIN_NAME && uv run chi-edge device show "${EDGE_DEVICE_NAME:-soarm101-1}"'

# List registered CHI@Edge devices visible to these credentials as redacted JSON
edge-device-list:
    uv run python scripts/reserve_edge.py --devices

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
    ANSIBLE_LOCAL_TEMP=/tmp/ansible-local \
    ANSIBLE_REMOTE_TEMP=/tmp/ansible-remote \
    ANSIBLE_SSH_CONTROL_PATH_DIR=/tmp/ansible-cp \
    ansible-playbook \
        -i ansible/inventory.ini \
        ansible/playbooks/setup_training_node.yml \
        --vault-password-file ansible/.vault_pass

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
    @echo "=== Pi SSH ({{_arm_host}}) ==="
    ssh -p ${PI_PORT} -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
        root@{{_arm_host}} "echo ok && uname -m"
    @echo "=== Serial Ports ==="
    ssh -p ${PI_PORT} -o StrictHostKeyChecking=no root@{{_arm_host}} \
        "ls /dev/ttyACM* 2>/dev/null || echo 'NO SERIAL PORTS'"
    @echo "=== Cameras ==="
    ssh -p ${PI_PORT} -o StrictHostKeyChecking=no root@{{_arm_host}} \
        "ls /dev/video0 /dev/video2 2>/dev/null && echo 'cameras OK' || echo 'cameras NOT FOUND'"
    @echo "=== Containers ==="
    ssh -p ${PI_PORT} -o StrictHostKeyChecking=no root@{{_arm_host}} \
        "balena ps 2>/dev/null || docker ps 2>/dev/null || echo 'no container runtime'"

# Full system health check: auth + node + pi
test-all: check-auth test-node test-pi
    @echo "=== All checks passed ==="

# Full readiness check: health + verify student notebooks
ready: test-all verify-all
    @echo "=== System ready for student sessions ==="

# ── Arm Operations (fleet: arm-01, arm-02, ...) ───────────────────────────────
#
# _arm_host resolves the online arm-* node from Tailscale at runtime.
# PI_HOST in .env is the fallback if tailscale is unavailable.
# No manual .env update needed after container restarts.

# Show which arm node will be targeted by arm-* recipes
arm-host:
    @echo "{{_arm_host}}"

# SSH into the arm node (via Tailscale by default)
arm-ssh: check-env
    ssh root@{{_arm_host}}

# Run a command on the arm node: just arm-exec cmd="ls /dev/ttyACM*"
arm-exec cmd: check-env
    ssh -p ${PI_PORT} -o StrictHostKeyChecking=no root@{{_arm_host}} "{{cmd}}"

# Verify arm node: SSH + serial ports + cameras + tailscale
arm-test: check-env
    @echo "=== SSH ({{_arm_host}}) ==="
    ssh -p ${PI_PORT} -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
        root@{{_arm_host}} "echo ok && uname -m && hostname"
    @echo "=== Tailscale ==="
    ssh -p ${PI_PORT} -o StrictHostKeyChecking=no root@{{_arm_host}} \
        "tailscale status 2>/dev/null || echo 'tailscale not running'"
    @echo "=== Serial Ports ==="
    ssh -p ${PI_PORT} -o StrictHostKeyChecking=no root@{{_arm_host}} \
        "ls /dev/ttyACM* 2>/dev/null || echo 'NO SERIAL PORTS'"
    @echo "=== Cameras ==="
    ssh -p ${PI_PORT} -o StrictHostKeyChecking=no root@{{_arm_host}} \
        "ls /dev/video* 2>/dev/null || echo 'cameras NOT FOUND'"
    @echo "=== Calibration ==="
    ssh -p ${PI_PORT} -o StrictHostKeyChecking=no root@{{_arm_host}} \
        "ls /mnt/data/calibration/*.json 2>/dev/null | wc -l | xargs -I{} echo '{} calibration file(s)'"

# Collect demonstration episodes on the arm node: just arm-collect dataset=touch-block episodes=20
arm-collect dataset episodes="20": check-env
    ssh -p ${PI_PORT} -t -o StrictHostKeyChecking=no root@{{_arm_host}} \
        "lerobot-record \
           --robot.type=so101_follower --robot.port=/dev/ttyACM1 \
           --teleop.type=so101_leader  --teleop.port=/dev/ttyACM0 \
           --dataset.repo_id=${HF_USER}/{{dataset}} \
           --dataset.num_episodes={{episodes}} \
           --dataset.push_to_hub=true"

# Calibrate the arm: just arm-calibrate
arm-calibrate: check-env
    ssh -p ${PI_PORT} -t -o StrictHostKeyChecking=no root@{{_arm_host}} \
        "lerobot-calibrate \
           --robot.type=so101_follower --robot.port=/dev/ttyACM1 \
           --robot.id=alpha_follower \
           --robot.calibration_dir=/mnt/data/calibration"

# Replay a reference episode on the follower arm: just arm-replay repo=USER/soarm101-touch-block episode=0
arm-replay repo episode="0": check-env
    ssh -p ${PI_PORT} -t -o StrictHostKeyChecking=no root@{{_arm_host}} \
        "lerobot-replay \
           --robot.type=so101_follower --robot.port=/dev/ttyACM1 \
           --robot.id=alpha_follower \
           --robot.calibration_dir=/mnt/data/calibration \
           --dataset.repo_id={{repo}} \
           --dataset.episode={{episode}} \
           --play_sounds=false"

# Run cable-safe SO-ARM101 teleop with follower wrist-roll clamped around the
# current matched start pose. Put both wrists in a cable-safe matching pose first.
arm-teleop-safe fps="30" wrist_degrees="15": check-env
    scp scripts/safe_so101_teleoperate.py root@{{_arm_host}}:/tmp/safe_so101_teleoperate.py
    ssh -p ${PI_PORT} -t -o StrictHostKeyChecking=no root@{{_arm_host}} \
        "python /tmp/safe_so101_teleoperate.py \
           --fps {{fps}} \
           --wrist-safe-degrees {{wrist_degrees}} \
           --leader-port /dev/ttyACM0 \
           --follower-port /dev/ttyACM1 \
           --leader-id alpha_leader \
           --follower-id alpha_follower \
           --calibration-dir /app/calibration"

# Same as arm-teleop-safe, but freezes follower wrist-roll exactly at startup.
arm-teleop-freeze-wrist fps="30": check-env
    scp scripts/safe_so101_teleoperate.py root@{{_arm_host}}:/tmp/safe_so101_teleoperate.py
    ssh -p ${PI_PORT} -t -o StrictHostKeyChecking=no root@{{_arm_host}} \
        "python /tmp/safe_so101_teleoperate.py \
           --fps {{fps}} \
           --freeze-wrist-roll \
           --leader-port /dev/ttyACM0 \
           --follower-port /dev/ttyACM1 \
           --leader-id alpha_leader \
           --follower-id alpha_follower \
           --calibration-dir /app/calibration"

# Start Gradio camera preview on arm in a tmux session (then: just tunnel-arm → http://localhost:7860)
# camera=0 → /dev/video0 (top)  camera=1 → /dev/video1  default: 0
arm-preview camera="0": check-env
    ssh -p ${PI_PORT} -o StrictHostKeyChecking=no root@{{_arm_host}} \
        "tmux kill-session -t preview 2>/dev/null; \
         tmux new-session -d -s preview \
           'python /app/scripts/camera_preview.py --camera {{camera}} 2>&1 | tee /tmp/preview.log'"
    @echo "Camera preview started (video{{camera}}) on {{_arm_host}}."
    @echo "Run: just tunnel-arm   → http://localhost:7860"

# Stop Gradio camera preview tmux session on arm
arm-preview-stop: check-env
    ssh -p ${PI_PORT} -o StrictHostKeyChecking=no root@{{_arm_host}} \
        "tmux kill-session -t preview 2>/dev/null; echo preview stopped"

# Open SSH tunnel to arm Gradio UI -> http://localhost:7860
tunnel-arm: check-env
    @echo "Tunneling arm Gradio UI -> http://localhost:7860 (host: {{_arm_host}})"
    ssh -L 7860:localhost:7860 -p ${PI_PORT} root@{{_arm_host}}

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

# Start talkbot Gradio UI on arm via SSH and tunnel to localhost:7860
talkbot-arm: check-env
    @echo "Starting talkbot on {{_arm_host}}, tunneling to http://localhost:7860"
    ssh -L 7860:localhost:7860 root@{{_arm_host}} \
        "cd ~/talkbot && tmux new-session -d -s talkbot 'uv run talkbot serve --no-tts' 2>/dev/null; echo talkbot started"

# Send a single chat message to talkbot (no voice): just talkbot-chat msg="Hello"
talkbot-chat msg: check-env
    cd ~/talkbot && uv run talkbot --no-speak chat "{{msg}}"

# Start talkbot on arm in a tmux session with voice coaching prompt
talkbot-arm-start: check-env
    ssh root@{{_arm_host}} \
        "cd ~/talkbot && tmux kill-session -t talkbot 2>/dev/null; \
         tmux new-session -d -s talkbot \
           'TALKBOT_AGENT_PROMPT=\"${TALKBOT_AGENT_PROMPT}\" uv run talkbot serve'"
    @echo "TalkBot started on {{_arm_host}}. Run: just tunnel-arm to access UI."

# Stop talkbot tmux session on arm
talkbot-arm-stop: check-env
    ssh root@{{_arm_host}} "tmux kill-session -t talkbot 2>/dev/null; echo stopped"

# ── Legacy aliases (old pi-* / balena-based recipes) ──────────────────────────
# These target the same PI_HOST/PI_PORT but use the old balena runtime.
# Use arm-* recipes above for CHI@Edge / Tailscale deployments.

# Verify Pi serial ports and cameras are present (non-interactive)
test-arm: arm-test

# Replay a reference animation on the follower arm: just replay-ref repo=USER/soarm101-touch-block-reference episode=0
replay-ref repo episode="0": check-env
    ssh -p ${PI_PORT} -t -o StrictHostKeyChecking=no root@{{_arm_host}} \
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
    @echo "Running inference benchmark on Pi ({{_arm_host}})..."
    ssh -p ${PI_PORT} -o StrictHostKeyChecking=no root@{{_arm_host}} \
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
    docker buildx build --platform linux/arm64 --push \
        -t rianders/lerobot-soarm101:arm \
        -t rianders/lerobot-soarm101:arm-{{_date}} \
        -f channels/arm/Dockerfile .

# Build and push arm base image (alias — build-arm already pushes)
push-arm: build-arm
    @echo "Pushed: rianders/lerobot-soarm101:arm-{{_date}}"

# Build and push arm-talk image (--push sends directly to registry from buildx cache)
push-arm-talk:
    docker buildx build --platform linux/arm64 --push \
        -t rianders/lerobot-soarm101:arm-talk \
        -t rianders/lerobot-soarm101:arm-talk-{{_date}} \
        -f channels/arm-talk/Dockerfile .
    @echo "Pushed: rianders/lerobot-soarm101:arm-talk-{{_date}}"
    @echo "Update .env: EDGE_IMAGE_REF=rianders/lerobot-soarm101:arm-talk-{{_date}}"
    @echo "Then run: just restart-arm"

# Build and push the full channel stack: arm base then arm-talk
push-all-channels: push-arm push-arm-talk

# Build and push diagnostic container for CHI@Edge Jetson (fast pull, rich tooling)
# Runs network/GPU/device diagnostics at startup → writes /tmp/diag.json → sleep infinity
# Read results: just jetson-exec cmd="cat /tmp/diag.json"
push-diag:
    docker buildx build --platform linux/arm64 --push \
        -t rianders/lerobot-soarm101:diag-{{_date}} \
        -f channels/diag/Dockerfile .
    @echo "Pushed: rianders/lerobot-soarm101:diag-{{_date}}"
    @echo "Update .env: JETSON_IMAGE_REF=rianders/lerobot-soarm101:diag-{{_date}}"
    @echo "Then run: just restart-jetson"

# Build arm-talk-jetson image (Jetson Orin: CUDA-enabled llama-server + talkbot)
# Must be built ON the Jetson (native arm64 + CUDA headers) — not cross-compiled
build-arm-talk-jetson:
    docker build \
        -t rianders/lerobot-soarm101:arm-talk-jetson \
        -t rianders/lerobot-soarm101:arm-talk-jetson-{{_date}} \
        -f channels/arm-talk-jetson/Dockerfile .

# Push arm-talk-jetson image (run this on the Jetson after building)
push-arm-talk-jetson: build-arm-talk-jetson
    docker push rianders/lerobot-soarm101:arm-talk-jetson-{{_date}}
    @echo "Pushed: rianders/lerobot-soarm101:arm-talk-jetson-{{_date}}"

# ── Access ────────────────────────────────────────────────────────────────────

# SSH to the training node
ssh-node: check-env
    ssh cc@${CONTROL_FLOATING_IP}

# SSH to the arm edge node (alias for arm-ssh)
ssh-pi: check-env
    ssh -p ${PI_PORT} root@{{_arm_host}}

# Open SSH tunnel to JupyterLab on the control node → http://localhost:8888
tunnel: check-env
    @echo "Tunneling JupyterLab → http://localhost:8888"
    ssh -L 8888:localhost:8888 cc@${CONTROL_FLOATING_IP}
