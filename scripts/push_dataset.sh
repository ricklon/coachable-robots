#!/bin/bash
# Push a local dataset from the Pi to HuggingFace Hub.
# Usage: ./scripts/push_dataset.sh <dataset_slug> [local_org]
# Example: ./scripts/push_dataset.sh test_calibration3

set -e

DATASET_SLUG=${1:-test_calibration3}
HF_ORG="ricklon"
LOCAL_ORG=${2:-rianders}
REPO_ID="${HF_ORG}/soarm101-${DATASET_SLUG}"
DATASET_PATH="/app/data/${LOCAL_ORG}/soarm101-${DATASET_SLUG}"
PI_HOST="root@192.168.4.191"
PI_PORT="22222"

echo "Dataset: ${REPO_ID}"
echo "Path on Pi: ${DATASET_PATH}"
echo ""
read -s -p "HF Token (write): " HF_TOKEN
echo ""

# Write token to temp file to avoid shell quoting issues
TMPFILE=$(mktemp)
echo "$HF_TOKEN" > "$TMPFILE"
scp -P ${PI_PORT} "$TMPFILE" ${PI_HOST}:/tmp/hf_token
rm "$TMPFILE"

ssh -p ${PI_PORT} ${PI_HOST} \
  "HF_TOKEN=\$(cat /tmp/hf_token) && \
   balena run -i \
   -v /mnt/data/datasets:/app/data \
   -e HF_TOKEN=\$HF_TOKEN \
   rianders/lerobot-soarm101:latest \
   python3 -c \"
import os
from huggingface_hub import login, whoami
login(token=os.environ['HF_TOKEN'])
user = whoami()['name']
print('Logged in as:', user)
from lerobot.datasets.lerobot_dataset import LeRobotDataset
ds = LeRobotDataset('${REPO_ID}', root='${DATASET_PATH}')
ds.push_to_hub()
print('Pushed to: https://huggingface.co/datasets/${REPO_ID}')
\" && rm /tmp/hf_token"
