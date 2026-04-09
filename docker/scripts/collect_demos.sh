#!/bin/bash
# collect_demos.sh — Teleoperate SO-ARM101 and record demonstration episodes
#
# Camera setup:
#   top    — Logitech C920e  (/dev/video0) 1280x720 @ 30fps YUYV
#   gripper — SVPRO OV2710 fisheye (/dev/video2) 1920x1080 @ 30fps MJPG, FOV 150°
#
# Usage: bash scripts/collect_demos.sh [dataset_name] [num_episodes] [task_description]
#
# Examples:
#   bash scripts/collect_demos.sh pick_block 20 "Pick up the block and place it in the box"
#   USE_SIM=1 bash scripts/collect_demos.sh sim_test 5 "Sim test run"
#
# Environment variables:
#   HF_USER        HuggingFace username (required)
#   HF_TOKEN       HuggingFace token (required for push; optional for sim dry-run)
#   LEADER_PORT    Leader arm serial port (default /dev/ttyACM0)
#   FOLLOWER_PORT  Follower arm serial port (default /dev/ttyACM1)
#   USE_SIM        Set to 1 to run a pipeline dry-run (no hardware)
set -euo pipefail

DATASET_NAME=${1:-"soarm101_demos"}
NUM_EPISODES=${2:-20}
TASK_DESC=${3:-"Pick up the object and place it in the target location"}

LEADER_PORT=${LEADER_PORT:-/dev/ttyACM0}
FOLLOWER_PORT=${FOLLOWER_PORT:-/dev/ttyACM1}
USE_SIM=${USE_SIM:-0}

if [ -z "${HF_USER:-}" ]; then
    echo "ERROR: HF_USER environment variable is not set."
    exit 1
fi

echo "=== SO-ARM101 Demo Collection ==="
echo "Dataset:  ${HF_USER}/${DATASET_NAME}"
echo "Episodes: ${NUM_EPISODES}"
echo "Task:     ${TASK_DESC}"
echo "Mode:     $([ "$USE_SIM" = "1" ] && echo "DRY-RUN (pipeline validation, no hardware)" || echo "REAL ARMS")"
echo ""

if [ "$USE_SIM" = "1" ]; then
    echo "Dry-run: validating HF access and training entrypoint..."

    if [ -n "${HF_TOKEN:-}" ]; then
        python3 -m huggingface_hub login --token "$HF_TOKEN"
        echo "HF auth: OK"
    fi

    REF_DATASET="lerobot/pusht"
    echo "Pulling reference dataset: ${REF_DATASET}"
    python -c "
from lerobot.datasets.lerobot_dataset import LeRobotDataset
ds = LeRobotDataset('${REF_DATASET}', episodes=[0])
print(f'Dataset OK: {len(ds)} frames, keys={list(ds[0].keys())}')
"

    echo "Checking training entrypoint..."
    python -c "
from lerobot.scripts.lerobot_train import main as train_main
print('lerobot-train entrypoint: OK')
"

    echo ""
    echo "Pipeline dry-run PASSED. Container is ready for real arm collection."
    exit 0
fi

# ── Real hardware mode ──────────────────────────────────────────────────────────

if [ -z "${HF_TOKEN:-}" ]; then
    echo "ERROR: HF_TOKEN environment variable is not set."
    exit 1
fi

python3 -m huggingface_hub login --token "$HF_TOKEN"

# Verify serial ports
for port in "$LEADER_PORT" "$FOLLOWER_PORT"; do
    if [ ! -e "$port" ]; then
        echo "ERROR: $port not found. Check USB connections: ls /dev/ttyACM*"
        exit 1
    fi
done

# Verify cameras
if [ ! -e "/dev/video0" ]; then
    echo "ERROR: /dev/video0 not found (top camera — Logitech C920e)"
    exit 1
fi
if [ ! -e "/dev/video2" ]; then
    echo "ERROR: /dev/video2 not found (gripper camera — SVPRO OV2710)"
    exit 1
fi

# Configure OV2710 gripper camera: disable dynamic framerate, max backlight compensation
# Must be done before lerobot-record opens the device
echo "Configuring gripper camera (OV2710)..."
v4l2-ctl --device=/dev/video2 \
    --set-ctrl=exposure_dynamic_framerate=0 \
    --set-ctrl=backlight_compensation=2 2>/dev/null || true

echo "Leader:    ${LEADER_PORT}"
echo "Follower:  ${FOLLOWER_PORT}"
echo "Top cam:   /dev/video0  (C920e — 1280x720 @ 30fps)"
echo "Gripper:   /dev/video2  (OV2710 — 1920x1080 @ 30fps MJPG, 150° fisheye)"
echo ""

lerobot-record \
    --robot.type=so101_follower \
    --robot.port="$FOLLOWER_PORT" \
    --robot.id=follower_arm \
    --robot.cameras="{
        top: {
            type: opencv,
            index_or_path: 0,
            width: 1280,
            height: 720,
            fps: 30
        },
        gripper: {
            type: opencv,
            index_or_path: 2,
            width: 1920,
            height: 1080,
            fps: 30
        }
    }" \
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
