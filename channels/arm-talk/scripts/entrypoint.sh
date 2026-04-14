#!/bin/bash
# channels/arm-talk/scripts/entrypoint.sh
#
# Extended entrypoint for arm-talk channel.
# CHI@Edge Zun ignores Dockerfile CMD — this entrypoint always starts
# llama-server + talkbot serve after sshd + tailscale.

set -e

# ── SSH daemon ──
mkdir -p /run/sshd /root/.ssh
chmod 700 /root/.ssh

if [ -n "${SSH_PUBKEY:-}" ]; then
    echo "$SSH_PUBKEY" >> /root/.ssh/authorized_keys
    chmod 600 /root/.ssh/authorized_keys
fi

sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/'          /etc/ssh/sshd_config
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

# ── Start talkbot (llama-server + Gradio UI) ──
# CHI@Edge Zun does not honor Dockerfile CMD — start explicitly here.
echo "[entrypoint] starting talkbot stack..."
exec /app/scripts/start-llama-server.sh
