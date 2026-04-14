# channels/diag/Dockerfile — Diagnostic container for CHI@Edge Jetson Orin
#
# Purpose: Understand what the Jetson node exposes to containers:
#   - Outbound network (DNS, HTTP, HTTPS to key services)
#   - GPU/CUDA device access (/dev/nvidia*, nvcc, nvidia-smi)
#   - Host mounts, devices, and k8s environment
#   - Tailscale connectivity
#
# Design principles:
#   - Small base (fast pull — critical when debugging image pull failures)
#   - Rich tooling (iproute2, curl, dnsutils, python3, etc.)
#   - Entrypoint runs diagnostics → writes /tmp/diag.json → sleep infinity
#   - Container stays up even if Tailscale / network fails
#   - Results readable via Zun exec: zun exec <name> cat /tmp/diag.json
#
# Build (cross-compile from x86):
#   docker buildx build --platform linux/arm64 \
#     -t rianders/lerobot-soarm101:diag-$(date +%Y%m%d) \
#     -f channels/diag/Dockerfile --push .
#
# Deploy to Jetson:
#   Update JETSON_IMAGE_REF=rianders/lerobot-soarm101:diag-YYYYMMDD in .env
#   just restart-jetson

FROM arm64v8/ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# ── Network + system diagnostic tools ────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        openssh-server \
        ca-certificates \
        curl \
        wget \
        iproute2 \
        net-tools \
        iputils-ping \
        traceroute \
        dnsutils \
        netcat-openbsd \
        lsof \
        strace \
        python3 \
        python3-json5 \
        jq \
        pciutils \
        usbutils \
        kmod \
    && rm -rf /var/lib/apt/lists/*

# ── Tailscale ─────────────────────────────────────────────────────────────────
RUN curl -fsSL https://pkgs.tailscale.com/stable/debian/bookworm.noarmor.gpg \
        | tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null \
    && curl -fsSL https://pkgs.tailscale.com/stable/debian/bookworm.tailscale-keyring.list \
        | tee /etc/apt/sources.list.d/tailscale.list \
    && apt-get update && apt-get install -y --no-install-recommends tailscale \
    && rm -rf /var/lib/apt/lists/*

# ── Entrypoint ────────────────────────────────────────────────────────────────
COPY channels/diag/scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
