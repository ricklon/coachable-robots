# channels/balena/Dockerfile — Balena channel wrapper
#
# Adds the balena supervisor API label to the app image.
# No openssh-server needed — BalenaOS handles SSH at the host OS level.
# Application stack (Gradio, coachable, LeRobot) is identical to the app image.
#
# Deploy via balena CLI from the channels/balena/ directory:
#   balena push <app-name>
#
# Or build locally:
#   docker buildx build --platform linux/arm64 --load \
#     -t rianders/lerobot-soarm101:balena \
#     -f channels/balena/Dockerfile ../../

FROM rianders/lerobot-soarm101:app

# Enable balena supervisor API (allows querying device state, graceful shutdown)
LABEL io.balena.features.supervisor-api="1"

CMD ["sleep", "infinity"]
