#!/bin/bash
# calibrate.sh — Calibrate leader and follower SO-ARM101 arms
# Run this once before collecting demos. Calibration files are saved to
# /app/calibration/ — mount a volume there to persist across containers.
#
# Usage: bash scripts/calibrate.sh
#
# USB layout (adjust if arms enumerate differently):
#   Leader arm:   /dev/ttyACM0
#   Follower arm: /dev/ttyACM1
set -euo pipefail

LEADER_PORT=${LEADER_PORT:-/dev/ttyACM0}
FOLLOWER_PORT=${FOLLOWER_PORT:-/dev/ttyACM1}

echo "=== SO-ARM101 Calibration ==="
echo "Leader port:   $LEADER_PORT"
echo "Follower port: $FOLLOWER_PORT"
echo ""
echo "You will be prompted to move each joint to its min/max positions."
echo ""

# Verify ports exist
for port in "$LEADER_PORT" "$FOLLOWER_PORT"; do
    if [ ! -e "$port" ]; then
        echo "ERROR: $port not found. Check USB connections and run: ls /dev/ttyACM*"
        exit 1
    fi
done

echo "--- Calibrating leader arm ---"
python -m lerobot.scripts.control_robot \
    --robot.type=so101_leader \
    --robot.port="$LEADER_PORT" \
    --robot.id=leader_arm \
    --control.type=calibrate

echo ""
echo "--- Calibrating follower arm ---"
python -m lerobot.scripts.control_robot \
    --robot.type=so101_follower \
    --robot.port="$FOLLOWER_PORT" \
    --robot.id=follower_arm \
    --control.type=calibrate

echo ""
echo "Calibration complete. Files saved to ~/.cache/huggingface/lerobot/calibration/"
