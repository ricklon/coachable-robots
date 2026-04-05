#!/bin/bash
# collect_demos.sh — Teleoperate SO-ARM101 and record demonstration episodes
#
# Usage: bash scripts/collect_demos.sh [dataset_name] [num_episodes] [task_description]
#
# Examples:
#   bash scripts/collect_demos.sh pick_block 20 "Pick up the block and place it in the box"
#   bash scripts/collect_demos.sh             # uses defaults below
#
# USB layout (adjust via env vars if arms enumerate differently):
#   Leader arm:   LEADER_PORT  (default /dev/ttyACM0)
#   Follower arm: FOLLOWER_PORT (default /dev/ttyACM1)
#   Webcam:       CAMERA_INDEX (default 0)
set -euo pipefail

DATASET_NAME=${1:-"soarm101_demos"}
NUM_EPISODES=${2:-20}
TASK_DESC=${3:-"Pick up the object and place it in the target location"}

LEADER_PORT=${LEADER_PORT:-/dev/ttyACM0}
FOLLOWER_PORT=${FOLLOWER_PORT:-/dev/ttyACM1}
CAMERA_INDEX=${CAMERA_INDEX:-0}

if [ -z "${HF_USER:-}" ]; then
    echo "ERROR: HF_USER environment variable is not set."
    echo "  Run: export HF_USER=your-huggingface-username"
    exit 1
fi

if [ -z "${HF_TOKEN:-}" ]; then
    echo "ERROR: HF_TOKEN environment variable is not set."
    echo "  Run: export HF_TOKEN=hf_xxx"
    exit 1
fi

echo "=== SO-ARM101 Demo Collection ==="
echo "Dataset:  ${HF_USER}/${DATASET_NAME}"
echo "Episodes: ${NUM_EPISODES}"
echo "Task:     ${TASK_DESC}"
echo "Leader:   ${LEADER_PORT}"
echo "Follower: ${FOLLOWER_PORT}"
echo "Camera:   /dev/video${CAMERA_INDEX}"
echo ""

# Verify devices
for port in "$LEADER_PORT" "$FOLLOWER_PORT"; do
    if [ ! -e "$port" ]; then
        echo "ERROR: $port not found. Check USB connections: ls /dev/ttyACM*"
        exit 1
    fi
done

if [ ! -e "/dev/video${CAMERA_INDEX}" ]; then
    echo "ERROR: /dev/video${CAMERA_INDEX} not found. Check USB camera: ls /dev/video*"
    exit 1
fi

# Authenticate HuggingFace
huggingface-cli login --token "$HF_TOKEN"

lerobot-record \
    --robot.type=so101_follower \
    --robot.port="$FOLLOWER_PORT" \
    --robot.id=follower_arm \
    --robot.cameras="{ top: {type: opencv, index_or_path: ${CAMERA_INDEX}, width: 640, height: 480, fps: 30} }" \
    --teleop.type=so101_leader \
    --teleop.port="$LEADER_PORT" \
    --teleop.id=leader_arm \
    --dataset.repo_id="${HF_USER}/${DATASET_NAME}" \
    --dataset.num_episodes="${NUM_EPISODES}" \
    --dataset.single_task="${TASK_DESC}" \
    --dataset.episode_time_s=30 \
    --dataset.reset_time_s=10 \
    --dataset.fps=30 \
    --dataset.push_to_hub=true

echo ""
echo "Done! Dataset at: https://huggingface.co/datasets/${HF_USER}/${DATASET_NAME}"
