# channels/arm-infer/Dockerfile — arm + inference runtime
#
# Adds inference-optimized runtime to the arm base image for autonomous policy
# execution on the edge. Pulls the trained policy checkpoint from HuggingFace Hub.
#
# fleet.yaml: image: arm-infer, infer_host: null (co-located)
#
# Compared to arm:
#   - May include ONNX runtime or TorchScript optimization for lower latency
#   - Checkpoint download at startup or baked in at build time
#
# Runtime env vars:
#   MODEL_REPO_ID   — HuggingFace checkpoint repo, e.g. rianders/act-pick-block
#   HF_TOKEN        — for private model repos
#
# Build:
#   docker buildx build --platform linux/arm64 --load \
#     -t rianders/lerobot-soarm101:arm-infer \
#     -t rianders/lerobot-soarm101:arm-infer-$(date +%Y%m%d) \
#     -f channels/arm-infer/Dockerfile .

FROM rianders/lerobot-soarm101:arm

# TODO: inference optimizations (ONNX export, TorchScript, etc.)
# RUN uv pip install --system --no-cache onnxruntime

# TODO: checkpoint download script
# COPY docker/scripts/fetch_checkpoint.sh /app/scripts/fetch_checkpoint.sh

# Entrypoint inherited from arm — sshd + tailscale start before CMD
