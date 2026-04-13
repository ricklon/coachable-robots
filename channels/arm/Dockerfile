# channels/arm/Dockerfile — arm fleet deployment channel (CHI@Edge)
#
# Adds openssh-server + Tailscale to the app image so the container joins the
# tailnet on startup and is reachable via `ssh root@arm-01` from any node.
# Device passthrough (ttyACM/video) is provided by CHI@Edge device_profiles.
#
# Runtime env vars (set by reserve_edge.py):
#   TS_AUTHKEY   — reusable+ephemeral Tailscale auth key
#   TS_HOSTNAME  — Tailscale hostname, e.g. arm-01, arm-02
#   SSH_PUBKEY   — injected into root authorized_keys at startup
#
# Build (use dated tag to bust CHI@Edge image cache — image_pull_policy=always forbidden):
#   docker buildx build --platform linux/arm64 --load \
#     -t rianders/lerobot-soarm101:arm \
#     -t rianders/lerobot-soarm101:arm-$(date +%Y%m%d) \
#     -f channels/arm/Dockerfile .

FROM rianders/lerobot-soarm101:app

RUN apt-get update && apt-get install -y --no-install-recommends \
        openssh-server \
        ca-certificates \
    && curl -fsSL https://pkgs.tailscale.com/stable/debian/bookworm.noarmor.gpg \
        | tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null \
    && curl -fsSL https://pkgs.tailscale.com/stable/debian/bookworm.tailscale-keyring.list \
        | tee /etc/apt/sources.list.d/tailscale.list \
    && apt-get update && apt-get install -y --no-install-recommends tailscale \
    && rm -rf /var/lib/apt/lists/*

COPY docker/scripts/entrypoint.sh /app/scripts/entrypoint.sh
RUN chmod +x /app/scripts/entrypoint.sh

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["sleep", "infinity"]
