# channels/arm-talk-jetson/Dockerfile — Talkbot + Gradio UI on Jetson Orin
#
# Jetson variant of arm-talk: uses CUDA-enabled llama-server for fast inference.
# Targets Jetson Orin (arm64, CUDA 12.x, JetPack 6.x).
#
# Key differences from channels/arm-talk/:
#   - Base: dustynv/jetson-containers python:3.12 (JetPack 6, CUDA 12.6)
#   - llama.cpp built with -DGGML_CUDA=ON (GPU inference)
#   - No LeRobot / robot hardware deps — pure talkbot node
#   - llama-server binds GPU layers via --n-gpu-layers 99
#
# Jetson Orin performance vs Pi CM4:
#   - qwen3.5-0.5b Q8: ~50-100ms vs ~1400ms
#   - qwen3.5-1.5b Q8: feasible (~200ms) vs impractical (>5s)
#   - Enables larger models: qwen3.5-1.5b, qwen3-4b
#
# Fleet role: talkbot node — voice coaching UI, no arm hardware
#
# Runtime env vars:
#   TS_AUTHKEY          — Tailscale auth key
#   TS_HOSTNAME         — e.g. talkbot-orin
#   SSH_PUBKEY          — injected into root authorized_keys
#   HF_TOKEN            — HuggingFace token for model download
#   LLAMA_MODEL_REPO    — default: Qwen/Qwen3.5-1.5B-GGUF
#   LLAMA_MODEL_FILE    — default: qwen3.5-1.5b-q8_0.gguf
#   LLAMA_N_GPU_LAYERS  — layers to offload to GPU (default: 99 = all)
#
# Ports:
#   22    — sshd
#   7860  — Gradio web UI
#   8000  — llama-server API
#
# Build:
#   docker build \
#     -t rianders/lerobot-soarm101:arm-talk-jetson \
#     -t rianders/lerobot-soarm101:arm-talk-jetson-$(date +%Y%m%d) \
#     -f channels/arm-talk-jetson/Dockerfile .
#
# Note: Build on the Jetson itself (native arm64 + CUDA headers available).
# Cross-compiling CUDA from x86 requires the full CUDA cross-toolkit — not worth it.

# JetPack 6.x + CUDA 12.6 + Python 3.12
# dustynv containers: https://github.com/dusty-nv/jetson-containers
FROM dustynv/python:3.12-r36.4.0

# ── System deps ────────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        openssh-server \
        ca-certificates \
        espeak-ng \
        espeak-ng-data \
        git \
        cmake \
        build-essential \
        python3-dev \
        curl \
    && curl -fsSL https://pkgs.tailscale.com/stable/debian/bookworm.noarmor.gpg \
        | tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null \
    && curl -fsSL https://pkgs.tailscale.com/stable/debian/bookworm.tailscale-keyring.list \
        | tee /etc/apt/sources.list.d/tailscale.list \
    && apt-get update && apt-get install -y --no-install-recommends tailscale \
    && rm -rf /var/lib/apt/lists/*

# ── llama.cpp — build from source with CUDA ───────────────────────────────────
# GGML_CUDA=ON: GPU inference (dramatically faster on Orin vs CPU-only)
# GGML_NATIVE=OFF: portable binary across Orin variants (NX, AGX, Nano)
# n-gpu-layers=99 at runtime offloads all layers to iGPU
ARG LLAMA_CPP_TAG=b8781
RUN git clone --depth 1 --branch "${LLAMA_CPP_TAG}" \
        https://github.com/ggerganov/llama.cpp /tmp/llama.cpp \
    && cmake -B /tmp/llama.cpp/build /tmp/llama.cpp \
        -DCMAKE_BUILD_TYPE=Release \
        -DLLAMA_BUILD_SERVER=ON \
        -DGGML_CUDA=ON \
        -DGGML_NATIVE=OFF \
    && cmake --build /tmp/llama.cpp/build -j$(nproc) --target llama-server llama-cli \
    && mkdir -p /app/bin \
    && cp /tmp/llama.cpp/build/bin/llama-server /app/bin/llama-server \
    && cp /tmp/llama.cpp/build/bin/llama-cli /app/bin/llama-cli \
    && rm -rf /tmp/llama.cpp
ENV PATH="/app/bin:${PATH}"

# ── talkbot — install with gradio extra ───────────────────────────────────────
ARG TALKBOT_BRANCH=main
RUN git clone --depth 1 --branch "${TALKBOT_BRANCH}" \
        https://github.com/ricklon/talkbot.git /app/talkbot \
    && cd /app/talkbot \
    && pip install uv \
    && uv sync --extra gradio \
    && uv run talkbot --version

# ── entrypoint + startup script ───────────────────────────────────────────────
COPY docker/scripts/entrypoint.sh /app/scripts/entrypoint.sh
COPY channels/arm-talk-jetson/scripts/start-llama-server.sh /app/scripts/start-llama-server.sh
RUN chmod +x /app/scripts/entrypoint.sh /app/scripts/start-llama-server.sh

WORKDIR /app

EXPOSE 22
EXPOSE 7860
EXPOSE 8000

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
# Default: use larger model since Orin can handle it
CMD ["/app/scripts/start-llama-server.sh"]
