#!/bin/bash
# fetch_checkpoint.sh — Pull a trained policy checkpoint from HuggingFace Hub
#
# Usage: bash scripts/fetch_checkpoint.sh [hf_repo] [local_dir]
#
# Examples:
#   bash scripts/fetch_checkpoint.sh ricklon/soarm101-act-policy
#   bash scripts/fetch_checkpoint.sh ricklon/soarm101-act-policy /app/checkpoints/my_policy
set -euo pipefail

MODEL_REPO=${1:-"${HF_USER}/soarm101-act-policy"}
LOCAL_DIR=${2:-"/app/checkpoints/latest"}

if [ -z "${HF_TOKEN:-}" ]; then
    echo "ERROR: HF_TOKEN is not set."
    exit 1
fi

echo "Fetching checkpoint from ${MODEL_REPO}..."
python3 -m huggingface_hub login --token "$HF_TOKEN"
python3 -m huggingface_hub download "${MODEL_REPO}" --local-dir "${LOCAL_DIR}"

echo ""
echo "Checkpoint ready at ${LOCAL_DIR}"
echo "Run autonomous policy with:"
echo "  bash scripts/run_policy.sh"
