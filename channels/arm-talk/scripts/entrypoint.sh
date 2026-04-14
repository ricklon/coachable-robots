#!/bin/bash
# channels/arm-talk/scripts/entrypoint.sh
#
# CHI@Edge Zun ignores Dockerfile CMD — this entrypoint starts everything.
# Inference is REMOTE — set TALKBOT_LOCAL_SERVER_URL to point at your
# Jetson, MI100, or set TALKBOT_LLM_BACKEND=openrouter for cloud inference.

set -e

# ── Export container env to SSH sessions ──────────────────────────────────────
# SSH sessions start a fresh shell and don't inherit the container's PID 1 env.
# Write all env vars to /etc/environment so they're available to every session.
printenv | grep -v '^_=' | grep -v '^SHLVL=' > /etc/environment
echo "[entrypoint] env exported to /etc/environment ($(wc -l < /etc/environment) vars)"

# ── SSH daemon ──
mkdir -p /run/sshd /root/.ssh
chmod 700 /root/.ssh

if [ -n "${SSH_PUBKEY:-}" ]; then
    echo "$SSH_PUBKEY" >> /root/.ssh/authorized_keys
    chmod 600 /root/.ssh/authorized_keys
fi

sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/'              /etc/ssh/sshd_config
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#*PubkeyAuthentication.*/PubkeyAuthentication yes/'    /etc/ssh/sshd_config

ssh-keygen -A
/usr/sbin/sshd
echo "[entrypoint] sshd started"

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

# ── Talkbot Gradio UI ──────────────────────────────────────────────────────────
# Inference is remote — TALKBOT_LOCAL_SERVER_URL points at Jetson/MI100/OpenRouter.
# Default falls back to http://127.0.0.1:8000/v1 (useful for local testing).
TALKBOT_PORT="${TALKBOT_PORT:-7860}"
TALKBOT_HOST="${TALKBOT_HOST:-0.0.0.0}"

echo "[entrypoint] starting talkbot serve on ${TALKBOT_HOST}:${TALKBOT_PORT}"
echo "[entrypoint] inference backend: ${TALKBOT_LLM_BACKEND:-local_server}"
echo "[entrypoint] server url: ${TALKBOT_LOCAL_SERVER_URL:-http://127.0.0.1:8000/v1}"

cd /app/talkbot
exec uv run talkbot serve \
    --host "${TALKBOT_HOST}" \
    --port "${TALKBOT_PORT}" \
    --no-tts
