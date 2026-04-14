#!/bin/bash
# entrypoint.sh — container startup for CHI@Edge SO-ARM101 container
#
# Starts sshd so the container is reachable at the floating IP.
# Pass SSH_PUBKEY env var to inject an authorized key for the root user.
#
# Usage (normal):  CMD in Dockerfile calls this, then falls through to CMD
# Usage (override): docker run ... rianders/lerobot-soarm101 bash

set -e

# ── Export container env to SSH sessions ──────────────────────────────────────
# SSH sessions start a fresh shell and don't inherit PID 1 env vars.
printenv | grep -v '^_=' | grep -v '^SHLVL=' > /etc/environment
echo "[entrypoint] env exported to /etc/environment ($(wc -l < /etc/environment) vars)"

# ── SSH daemon ──
mkdir -p /run/sshd /root/.ssh
chmod 700 /root/.ssh

# Inject authorized key if provided at runtime
if [ -n "${SSH_PUBKEY:-}" ]; then
    echo "$SSH_PUBKEY" >> /root/.ssh/authorized_keys
    chmod 600 /root/.ssh/authorized_keys
fi

# Allow root login; disable password auth (key-only)
sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/'          /etc/ssh/sshd_config
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#*PubkeyAuthentication.*/PubkeyAuthentication yes/'    /etc/ssh/sshd_config

# Generate host keys if missing (first boot)
ssh-keygen -A

/usr/sbin/sshd
echo "[entrypoint] sshd started — SSH available on port 22"

# ── Tailscale ──
if [ -n "${TS_AUTHKEY:-}" ]; then
    mkdir -p /var/run/tailscale /var/lib/tailscale
    tailscaled --state=/var/lib/tailscale/tailscaled.state \
               --socket=/var/run/tailscale/tailscaled.sock \
               --tun=userspace-networking &
    sleep 2
    tailscale --socket=/var/run/tailscale/tailscaled.sock \
        up --authkey="${TS_AUTHKEY}" --hostname="${TS_HOSTNAME:-arm-01}" --accept-routes
    echo "[entrypoint] tailscale up — hostname: ${TS_HOSTNAME:-arm-01}"
else
    echo "[entrypoint] TS_AUTHKEY not set — skipping tailscale"
fi

# ── Fall through to CMD ──
exec "$@"
