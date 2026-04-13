# channels/arm-talk/Dockerfile — arm + Talkbot voice coaching
#
# Adds ricklon/talkbot (local-first STT + LLM + TTS) to the arm base image.
# Used when Talkbot runs co-located in the same container as LeRobot.
#
# fleet.yaml: image: arm-talk, talkbot: co-located
#
# Talkbot dependencies:
#   - faster-whisper (STT)
#   - kitten-tts (TTS)
#   - LLM backend: local (ollama or llamacpp) or OpenRouter
#
# Runtime env vars (from .env / fleet.yaml):
#   TALKBOT_LLM_BACKEND     — local | openrouter
#   OPENROUTER_API_KEY      — if using OpenRouter
#   TALKBOT_AGENT_PROMPT    — coaching personality prompt
#
# Build:
#   docker buildx build --platform linux/arm64 --load \
#     -t rianders/lerobot-soarm101:arm-talk \
#     -t rianders/lerobot-soarm101:arm-talk-$(date +%Y%m%d) \
#     -f channels/arm-talk/Dockerfile .

FROM rianders/lerobot-soarm101:arm

# TODO: install talkbot
# RUN git clone https://github.com/ricklon/talkbot.git /app/talkbot \
#     && cd /app/talkbot \
#     && uv pip install --system --no-cache -e .

# TODO: Talkbot audio deps (portaudio, speechd, etc.)
# RUN apt-get update && apt-get install -y --no-install-recommends \
#         portaudio19-dev \
#         libspeechd-dev \
#     && rm -rf /var/lib/apt/lists/*

# TODO: expose Talkbot port
# EXPOSE 8080

# Entrypoint inherited from arm — sshd + tailscale start before CMD
