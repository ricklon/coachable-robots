#!/bin/bash
# start-llama-server.sh — Jetson Orin variant
# Downloads GGUF model if missing, starts llama-server with GPU offload,
# then starts talkbot serve in the foreground.
#
# Env vars:
#   LLAMA_MODEL_REPO    — HF repo (default: Qwen/Qwen3.5-1.5B-GGUF)
#   LLAMA_MODEL_FILE    — filename (default: qwen3.5-1.5b-q8_0.gguf)
#   LLAMA_MODEL_DIR     — local path (default: /app/models)
#   LLAMA_PORT          — llama-server port (default: 8000)
#   LLAMA_CTX           — context size (default: 4096)
#   LLAMA_N_GPU_LAYERS  — GPU layers to offload (default: 99 = all)
#   TALKBOT_PORT        — Gradio UI port (default: 7860)
#   TALKBOT_HOST        — Gradio bind address (default: 0.0.0.0)
#   HF_TOKEN            — HuggingFace token (optional)

set -e

# Jetson defaults: gemma-4-26b-A4B (MoE: 26B total, 4B active — fits in 64GB, runs at 4B speed)
# Q4_K_M is ~17GB; override with LLAMA_MODEL_REPO/FILE env vars to use a different model.
LLAMA_MODEL_REPO="${LLAMA_MODEL_REPO:-bartowski/google_gemma-4-26B-A4B-it-GGUF}"
LLAMA_MODEL_FILE="${LLAMA_MODEL_FILE:-google_gemma-4-26B-A4B-it-Q4_K_M.gguf}"
LLAMA_MODEL_DIR="${LLAMA_MODEL_DIR:-/app/models}"
LLAMA_PORT="${LLAMA_PORT:-8000}"
LLAMA_CTX="${LLAMA_CTX:-4096}"
LLAMA_N_GPU_LAYERS="${LLAMA_N_GPU_LAYERS:-99}"
TALKBOT_PORT="${TALKBOT_PORT:-7860}"
TALKBOT_HOST="${TALKBOT_HOST:-0.0.0.0}"

MODEL_PATH="${LLAMA_MODEL_DIR}/${LLAMA_MODEL_FILE}"

echo "[start-llama-server] model: ${LLAMA_MODEL_REPO}/${LLAMA_MODEL_FILE}"
echo "[start-llama-server] GPU layers: ${LLAMA_N_GPU_LAYERS}"

# ── Download model if not present ─────────────────────────────────────────────
if [ ! -f "${MODEL_PATH}" ]; then
    echo "[start-llama-server] model not found — downloading from HuggingFace..."
    mkdir -p "${LLAMA_MODEL_DIR}"

    MODEL_URL="https://huggingface.co/${LLAMA_MODEL_REPO}/resolve/main/${LLAMA_MODEL_FILE}"
    echo "[start-llama-server] GET ${MODEL_URL}"
    curl -L --progress-bar \
        ${HF_TOKEN:+-H "Authorization: Bearer ${HF_TOKEN}"} \
        -o "${MODEL_PATH}" \
        "${MODEL_URL}"
    echo "[start-llama-server] model downloaded to ${MODEL_PATH}"
else
    echo "[start-llama-server] model already present at ${MODEL_PATH}"
fi

# ── Start llama-server in the background ──────────────────────────────────────
echo "[start-llama-server] starting llama-server on port ${LLAMA_PORT}..."
/app/bin/llama-server \
    --model "${MODEL_PATH}" \
    --ctx-size "${LLAMA_CTX}" \
    --n-gpu-layers "${LLAMA_N_GPU_LAYERS}" \
    --port "${LLAMA_PORT}" \
    --host 127.0.0.1 \
    &
LLAMA_PID=$!
echo "[start-llama-server] llama-server PID ${LLAMA_PID}"

# Wait for llama-server to become ready
echo "[start-llama-server] waiting for llama-server to be ready..."
for i in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:${LLAMA_PORT}/health" >/dev/null 2>&1; then
        echo "[start-llama-server] llama-server ready after ${i}s"
        break
    fi
    sleep 1
done

# ── Start talkbot serve in the foreground ─────────────────────────────────────
echo "[start-llama-server] starting talkbot serve on ${TALKBOT_HOST}:${TALKBOT_PORT}..."
cd /app/talkbot
# Export env vars so talkbot picks them up via envvar= defaults
export TALKBOT_LLM_PROVIDER=local_server
export TALKBOT_LOCAL_SERVER_URL="http://127.0.0.1:${LLAMA_PORT}/v1"

exec uv run talkbot serve \
    --host "${TALKBOT_HOST}" \
    --port "${TALKBOT_PORT}"
