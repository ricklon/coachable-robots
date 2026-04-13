# channels/arm-talk/Dockerfile — arm + Talkbot voice coaching + Gradio UI
#
# Extends the arm image with:
#   - llama.cpp built from source (GLIBC-compatible for Debian Bookworm / arm64)
#   - ricklon/talkbot with [gradio] extra for browser-based chat
#   - espeak-ng for KittenTTS text-to-speech (no speaker required)
#   - llama-server binary at /app/bin/llama-server
#
# Fleet role: arm-talk — co-located voice coaching alongside LeRobot recording
#
# Runtime env vars (from .env):
#   TS_AUTHKEY              — Tailscale auth key (reusable+ephemeral)
#   TS_HOSTNAME             — Tailscale hostname, e.g. arm-01
#   SSH_PUBKEY              — injected into root authorized_keys at startup
#   HF_TOKEN                — HuggingFace token for model download
#   TALKBOT_LLM_BACKEND     — local_server (default) | openrouter
#   TALKBOT_AGENT_PROMPT    — coaching personality prompt
#   OPENROUTER_API_KEY      — only if TALKBOT_LLM_BACKEND=openrouter
#   LLAMA_MODEL_REPO        — HF repo for GGUF model (default: Qwen/Qwen3.5-0.5B-GGUF)
#   LLAMA_MODEL_FILE        — filename in repo (default: qwen3.5-0.5b-q8_0.gguf)
#
# Ports:
#   22    — sshd (Tailscale or floating IP)
#   7860  — Gradio web UI (talkbot serve)
#   8000  — llama-server OpenAI-compatible API
#
# Build (dated tag busts CHI@Edge image cache — image_pull_policy=always forbidden):
#   docker buildx build --platform linux/arm64 --load \
#     -t rianders/lerobot-soarm101:arm-talk \
#     -t rianders/lerobot-soarm101:arm-talk-$(date +%Y%m%d) \
#     -f channels/arm-talk/Dockerfile .
#   docker push rianders/lerobot-soarm101:arm-talk-$(date +%Y%m%d)

FROM rianders/lerobot-soarm101:chi-edge-20260413

# ── System deps ────────────────────────────────────────────────────────────────
# cmake + build-essential: compile llama.cpp from source (GLIBC 2.36-compatible)
# espeak-ng: KittenTTS TTS backend (no speakers needed — saves to file)
# git: clone llama.cpp + talkbot
RUN apt-get update && apt-get install -y --no-install-recommends \
        espeak-ng \
        espeak-ng-data \
        git \
        cmake \
        build-essential \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

# ── llama.cpp — build from source ─────────────────────────────────────────────
# Pre-built binaries require GLIBC 2.38; Debian Bookworm has 2.36.
# Source build produces a GLIBC-compatible binary (~15 min on CM4).
# -DGGML_NATIVE=OFF: portable binary (no host-specific CPU flags)
# -DLLAMA_BUILD_SERVER=ON: include llama-server
ARG LLAMA_CPP_TAG=b8781
RUN git clone --depth 1 --branch "${LLAMA_CPP_TAG}" \
        https://github.com/ggerganov/llama.cpp /tmp/llama.cpp \
    && cmake -B /tmp/llama.cpp/build /tmp/llama.cpp \
        -DCMAKE_BUILD_TYPE=Release \
        -DLLAMA_BUILD_SERVER=ON \
        -DGGML_NATIVE=OFF \
    && cmake --build /tmp/llama.cpp/build -j4 --target llama-server llama-cli \
    && mkdir -p /app/bin \
    && cp /tmp/llama.cpp/build/bin/llama-server /app/bin/llama-server \
    && cp /tmp/llama.cpp/build/bin/llama-cli /app/bin/llama-cli \
    && rm -rf /tmp/llama.cpp
ENV PATH="/app/bin:${PATH}"

# ── talkbot — install with gradio extra ───────────────────────────────────────
# Clones add-gradio-serve branch; uv sync installs all deps including Gradio 6.12+
# /app/talkbot is the working directory; uv manages the .venv
ARG TALKBOT_BRANCH=main
RUN git clone --depth 1 --branch "${TALKBOT_BRANCH}" \
        https://github.com/ricklon/talkbot.git /app/talkbot \
    && cd /app/talkbot \
    && pip install uv \
    && uv sync --extra gradio \
    && uv run talkbot --version

# ── model download script ─────────────────────────────────────────────────────
# Models are NOT baked into the image — too large (~800 MB) and frequently updated.
# /app/scripts/start-llama-server.sh downloads on first run if model not present,
# then starts llama-server on port 8000.
COPY channels/arm-talk/scripts/start-llama-server.sh /app/scripts/start-llama-server.sh
RUN chmod +x /app/scripts/start-llama-server.sh

# ── ports ─────────────────────────────────────────────────────────────────────
EXPOSE 22
EXPOSE 7860
EXPOSE 8000

# ── Entrypoint inherited from arm (sshd + tailscale + CMD) ────────────────────
# Default CMD starts llama-server in the background, then talkbot serve in foreground.
# Override CMD to run just sshd/tailscale without the talkbot UI.
CMD ["/app/scripts/start-llama-server.sh"]
