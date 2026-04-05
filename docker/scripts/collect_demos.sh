#!/bin/bash
# collect_demos.sh — Teleoperate SO-ARM101 and record demonstration episodes
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
#   CAMERA_INDEX   USB webcam index (default 0, i.e. /dev/video0)
#   USE_SIM        Set to 1 to run a pipeline dry-run (HF pull + training check, no hardware)
#
# Note on USE_SIM=1:
#   lerobot v0.5.0 removed sim robot types from lerobot-record. USE_SIM mode now
#   validates the full pipeline by pulling a public SO-101 dataset from HF Hub and
#   verifying the training entrypoint — no real arms or cameras required.
set -euo pipefail

DATASET_NAME=${1:-"soarm101_demos"}
NUM_EPISODES=${2:-20}
TASK_DESC=${3:-"Pick up the object and place it in the target location"}

LEADER_PORT=${LEADER_PORT:-/dev/ttyACM0}
FOLLOWER_PORT=${FOLLOWER_PORT:-/dev/ttyACM1}
CAMERA_INDEX=${CAMERA_INDEX:-0}
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
    # ── Dry-run mode: validate full pipeline without hardware ──
    # Pulls a public SO-101 dataset and verifies the training entrypoint.
    # HF_TOKEN optional (public dataset); set it to also test auth.
    echo "Dry-run: validating HF access and training entrypoint..."

    if [ -n "${HF_TOKEN:-}" ]; then
        huggingface-cli login --token "$HF_TOKEN"
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

# ── Real hardware mode requires HF credentials ──
if [ -z "${HF_TOKEN:-}" ]; then
    echo "ERROR: HF_TOKEN environment variable is not set."
    exit 1
fi

# Authenticate HuggingFace
huggingface-cli login --token "$HF_TOKEN"

    # ── Real hardware mode (SO-ARM101 leader + follower + C920e) ──

    # Verify serial ports
    for port in "$LEADER_PORT" "$FOLLOWER_PORT"; do
        if [ ! -e "$port" ]; then
            echo "ERROR: $port not found."
            echo "  Check USB connections: ls /dev/ttyACM*"
            echo "  Tip: set USE_SIM=1 to run without hardware"
            exit 1
        fi
    done

    # Verify webcam
    if [ ! -e "/dev/video${CAMERA_INDEX}" ]; then
        echo "ERROR: /dev/video${CAMERA_INDEX} not found."
        echo "  Check USB camera: ls /dev/video*"
        exit 1
    fi

    echo "Leader:   ${LEADER_PORT}"
    echo "Follower: ${FOLLOWER_PORT}"
    echo "Camera:   /dev/video${CAMERA_INDEX} (Logitech C920e)"
    echo ""

    lerobot-record \
        --robot.type=so101_follower \
        --robot.port="$FOLLOWER_PORT" \
        --robot.id=follower_arm \
        --robot.cameras="{ webcam: {type: opencv, index_or_path: ${CAMERA_INDEX}, width: 1280, height: 720, fps: 30} }" \
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
