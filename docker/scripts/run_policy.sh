#!/bin/bash
# run_policy.sh — Run a trained policy on the SO-ARM101 (autonomous execution)
#
# Usage: bash scripts/run_policy.sh [checkpoint_dir] [task_description]
#
# Run fetch_checkpoint.sh first to pull the policy from HuggingFace Hub.
set -euo pipefail

CHECKPOINT_DIR=${1:-"/app/checkpoints/latest"}
TASK_DESC=${2:-"Pick up the object and place it in the target location"}

FOLLOWER_PORT=${FOLLOWER_PORT:-/dev/ttyACM1}
CAMERA_INDEX=${CAMERA_INDEX:-0}

if [ ! -d "$CHECKPOINT_DIR" ]; then
    echo "ERROR: Checkpoint not found at ${CHECKPOINT_DIR}"
    echo "  Run: bash scripts/fetch_checkpoint.sh your-hf-username/your-model"
    exit 1
fi

echo "=== Running Policy ==="
echo "Checkpoint: ${CHECKPOINT_DIR}"
echo "Task:       ${TASK_DESC}"
echo "Follower:   ${FOLLOWER_PORT}"
echo "Camera:     /dev/video${CAMERA_INDEX}"
echo ""

lerobot-record \
    --robot.type=so101_follower \
    --robot.port="$FOLLOWER_PORT" \
    --robot.id=follower_arm \
    --robot.cameras="{ top: {type: opencv, index_or_path: ${CAMERA_INDEX}, width: 640, height: 480, fps: 30} }" \
    --policy.path="${CHECKPOINT_DIR}" \
    --dataset.repo_id="${HF_USER}/eval_run" \
    --dataset.single_task="${TASK_DESC}" \
    --dataset.num_episodes=5 \
    --dataset.push_to_hub=false
