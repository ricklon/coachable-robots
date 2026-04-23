# channels/dev/Dockerfile — Development / simulation channel (x86_64)
#
# For laptops and CI — runs on x86_64, not arm64.
# Adds simulation environments (gym-pusht, gym-aloha) for testing the full
# pipeline without physical hardware.
#
# Build:
#   docker buildx build --platform linux/amd64 --load \
#     -t rianders/lerobot-soarm101:dev -f channels/dev/Dockerfile .
#
# Run (simulation, no hardware):
#   docker run -it -e USE_SIM=1 -e HF_TOKEN=hf_xxx -e HF_USER=yourname \
#     rianders/lerobot-soarm101:dev
#
# Run (with real USB arms on laptop):
#   docker run -it --privileged -v /dev:/dev \
#     -e HF_TOKEN=hf_xxx -e HF_USER=yourname \
#     rianders/lerobot-soarm101:dev

FROM python:3.12-slim-bookworm

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

RUN curl -Ls https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# CPU PyTorch for x86 dev (override with CUDA/ROCm wheels if available)
RUN uv pip install --system --no-cache \
    torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cpu

# LeRobot with simulation extras
RUN git clone https://github.com/huggingface/lerobot.git /app/lerobot \
    && cd /app/lerobot \
    && git checkout v0.5.0 \
    && uv pip install --system --no-cache -e '.[feetech,aloha,pusht]'

COPY pyproject.toml README.md /app/coachable-robots/
COPY src/ /app/coachable-robots/src/
RUN uv pip install --system --no-cache -e /app/coachable-robots

RUN pip install --no-cache-dir "huggingface-hub[hf_xet,cli]"

COPY docker/scripts/ /app/scripts/
RUN chmod +x /app/scripts/*.sh 2>/dev/null || true

COPY config/fleet.example.yaml /app/config/fleet.yaml
RUN mkdir -p /app/calibration /app/data /app/checkpoints

ENV HF_LEROBOT_HOME="/app"
ENV FLEET_CONFIG="/app/config/fleet.yaml"
ENV USE_SIM=0

EXPOSE 7860

CMD ["/bin/bash"]
