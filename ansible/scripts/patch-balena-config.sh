#!/bin/bash
# patch-balena-config.sh
# Mounts a BalenaOS image's boot partition, injects developmentMode and
# an SSH public key into config.json, then unmounts cleanly.
#
# Usage:
#   sudo ./patch-balena-config.sh <image.img> <ssh-public-key-file>
#
# Example:
#   sudo ./patch-balena-config.sh ~/Downloads/balena-raspberrypi5-6.10.24.dev.img ~/.ssh/id_ed25519.pub

set -euo pipefail

IMAGE="${1:-}"
KEYFILE="${2:-}"
MOUNTPOINT="/mnt/balena-boot"

if [[ -z "$IMAGE" || -z "$KEYFILE" ]]; then
    echo "Usage: $0 <image.img> <ssh-public-key-file>"
    exit 1
fi

if [[ ! -f "$IMAGE" ]]; then
    echo "Error: image file not found: $IMAGE"
    exit 1
fi

if [[ ! -f "$KEYFILE" ]]; then
    echo "Error: SSH public key file not found: $KEYFILE"
    exit 1
fi

SSH_KEY=$(cat "$KEYFILE")
OFFSET=$(( 8192 * 512 ))

echo "Mounting boot partition from $IMAGE..."
mkdir -p "$MOUNTPOINT"
mount -o loop,offset="$OFFSET" "$IMAGE" "$MOUNTPOINT"

echo "Current config.json:"
cat "$MOUNTPOINT/config.json"
echo

echo "Patching config.json..."
python3 - <<EOF
import json

with open('${MOUNTPOINT}/config.json') as f:
    cfg = json.load(f)

cfg['developmentMode'] = True
cfg['os'] = {'sshKeys': ['${SSH_KEY}']}

with open('${MOUNTPOINT}/config.json', 'w') as f:
    json.dump(cfg, f, indent=2)
EOF

echo
echo "Updated config.json:"
cat "$MOUNTPOINT/config.json"

echo
echo "Unmounting..."
umount "$MOUNTPOINT"

echo "Done. Image is ready to flash."
