# channels/chi-edge/Dockerfile — CHI@Edge channel wrapper
#
# Adds openssh-server to the app image so the container is reachable at the
# Chameleon floating IP via SSH (key injected via SSH_PUBKEY env var at launch).
# Everything else — Gradio, coachable, LeRobot, scripts — is identical to the app image.
#
# Launched via python-chi Container API with device_profiles (not --privileged):
#   device_profiles=["ttyacm0", "ttyacm1", "video0", "video1", "video2", "video3"]
#
# Build (via Makefile):
#   make build-chi-edge
#
# Direct build:
#   docker buildx build --platform linux/arm64 --load \
#     -t rianders/lerobot-soarm101:chi-edge \
#     -t rianders/lerobot-soarm101:latest \
#     -f channels/chi-edge/Dockerfile .

FROM rianders/lerobot-soarm101:app

RUN apt-get update && apt-get install -y --no-install-recommends openssh-server \
    && rm -rf /var/lib/apt/lists/*

COPY docker/scripts/entrypoint.sh /app/scripts/entrypoint.sh
RUN chmod +x /app/scripts/entrypoint.sh

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["sleep", "infinity"]
