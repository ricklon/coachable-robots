# channels/arm-talk/Dockerfile — arm + Talkbot Gradio UI (remote inference)
#
# Adds talkbot with Gradio web UI to the arm base image.
# Inference runs OFF-DEVICE — point TALKBOT_LOCAL_SERVER_URL at a Jetson,
# MI100, or use TALKBOT_LLM_BACKEND=openrouter for cloud inference.
#
# The Pi handles: robot control, camera capture, talkbot UI.
# The Pi does NOT run: llama-server, any local LLM.
#
# Fleet role: arm-talk — voice coaching UI alongside LeRobot recording
#
# Runtime env vars (from .env):
#   TS_AUTHKEY                — Tailscale auth key (reusable+ephemeral)
#   TS_HOSTNAME               — e.g. arm-01
#   SSH_PUBKEY                — injected into root authorized_keys
#   TALKBOT_LOCAL_SERVER_URL  — remote inference endpoint (default: http://127.0.0.1:8000/v1)
#   TALKBOT_AGENT_PROMPT      — coaching personality (append /no_think for Qwen3 models)
#   TALKBOT_LLM_BACKEND       — local_server | openrouter (default: local_server)
#   OPENROUTER_API_KEY        — only if TALKBOT_LLM_BACKEND=openrouter
#   TALKBOT_PORT              — Gradio port (default: 7860)
#
# Ports:
#   22    — sshd
#   7860  — Gradio web UI
#
# Build:
#   docker buildx build --platform linux/arm64 --push \
#     -t rianders/lerobot-soarm101:arm-talk \
#     -t rianders/lerobot-soarm101:arm-talk-$(date +%Y%m%d) \
#     -f channels/arm-talk/Dockerfile .

FROM rianders/lerobot-soarm101:chi-edge-20260413

# ── System deps ────────────────────────────────────────────────────────────────
# espeak-ng: KittenTTS backend (generates audio to file, served to browser)
RUN apt-get update && apt-get install -y --no-install-recommends \
        espeak-ng \
        espeak-ng-data \
        git \
    && rm -rf /var/lib/apt/lists/*

# ── talkbot — install with gradio extra ───────────────────────────────────────
ARG TALKBOT_BRANCH=main
RUN git clone --depth 1 --branch "${TALKBOT_BRANCH}" \
        https://github.com/ricklon/talkbot.git /app/talkbot \
    && cd /app/talkbot \
    && pip install uv \
    && uv sync --extra gradio \
    && uv run talkbot --help > /dev/null

# ── entrypoint ────────────────────────────────────────────────────────────────
COPY channels/arm-talk/scripts/entrypoint.sh /app/scripts/arm-talk-entrypoint.sh
RUN chmod +x /app/scripts/arm-talk-entrypoint.sh

EXPOSE 22
EXPOSE 7860

ENTRYPOINT ["/app/scripts/arm-talk-entrypoint.sh"]
