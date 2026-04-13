# channels/arm-talk-infer/Dockerfile — arm + Talkbot + inference (full stack)
#
# All three capabilities in one container:
#   - LeRobot arm control (SO-ARM101)
#   - Talkbot voice coaching (STT + LLM + TTS)
#   - Inference runtime (autonomous policy execution)
#
# fleet.yaml: image: arm-talk-infer, talkbot: co-located, infer_host: null
#
# Build:
#   docker buildx build --platform linux/arm64 --load \
#     -t rianders/lerobot-soarm101:arm-talk-infer \
#     -t rianders/lerobot-soarm101:arm-talk-infer-$(date +%Y%m%d) \
#     -f channels/arm-talk-infer/Dockerfile .

FROM rianders/lerobot-soarm101:arm-talk

# TODO: add arm-infer layer on top of arm-talk
# (copy inference deps from arm-infer stage or reinstall here)

# Entrypoint inherited from arm — sshd + tailscale start before CMD
