# channels/app/Dockerfile — SO-ARM101 application image (arm64)
#
# THE shared application layer for all Pi 5 deployment channels.
# Contains everything the robot needs: LeRobot, coachable, Gradio, HF CLI.
# Does NOT include openssh-server — that is a channel concern, not an app concern.
#
# Channels that build FROM this image:
#   channels/arm/Dockerfile       — adds sshd and Tailscale for CHI@Edge
#   channels/balena/Dockerfile    — adds balena supervisor label
#   channels/local/docker-compose.yml — runs this image directly with --privileged
#
# Direct build:
#   docker buildx build --platform linux/arm64 --load \
#     -t rianders/lerobot-soarm101:app -f channels/app/Dockerfile .

FROM arm64v8/python:3.12-slim-bookworm

# System deps: USB serial, V4L2 cameras, video encoding
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ffmpeg \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libusb-1.0-0 \
    usbutils \
    v4l-utils \
    curl \
    build-essential \
    linux-libc-dev \
    speech-dispatcher \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -Ls https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# CPU-only PyTorch (Pi 5 has no GPU)
RUN uv pip install --system --no-cache \
    torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cpu

# LeRobot v0.5.0 with Feetech servo support (SO-ARM101 uses STS3215)
RUN git clone https://github.com/huggingface/lerobot.git /app/lerobot \
    && cd /app/lerobot \
    && git checkout v0.5.0 \
    && uv pip install --system --no-cache -e '.[feetech]'

# Install coachable package (fleet management + coaching CLI + Gradio)
COPY pyproject.toml README.md /app/coachable-robots/
COPY src/ /app/coachable-robots/src/
RUN uv pip install --system --no-cache -e /app/coachable-robots

# HuggingFace CLI
RUN pip install --no-cache-dir "huggingface-hub[hf_xet,cli]"

# Scripts
COPY docker/scripts/ /app/scripts/
RUN chmod +x /app/scripts/*.sh 2>/dev/null || true

# Fleet config — override at runtime with -v /path/to/fleet.yaml:/app/config/fleet.yaml
COPY config/fleet.example.yaml /app/config/fleet.yaml
RUN mkdir -p /app/calibration /app/data /app/checkpoints

ENV HF_LEROBOT_HOME="/app"
ENV FLEET_CONFIG="/app/config/fleet.yaml"
ENV LEADER_PORT="/dev/ttyACM0"
ENV FOLLOWER_PORT="/dev/ttyACM1"
ENV CAMERA_INDEX="0"

# Gradio preview — available on all channels
EXPOSE 7860

CMD ["/bin/bash"]
