# dev channel — x86_64 development and simulation

For laptops, CI, and classroom demos without physical hardware.
Adds simulation environments (`gym-pusht`, `gym-aloha`) to the base stack.

**Tag:** `rianders/lerobot-soarm101:dev`  
**Platform:** linux/amd64 (NOT arm64 — won't run on Pi)

## Build

```bash
make build-dev
```

## Usage

```bash
# Simulation only (no hardware needed)
docker run -it -e USE_SIM=1 -e HF_TOKEN=hf_xxx -e HF_USER=yourname \
  rianders/lerobot-soarm101:dev \
  bash scripts/collect_demos.sh sim_test 5 "Test run"

# With real USB arms connected to laptop
docker run -it --privileged -v /dev:/dev \
  -e HF_TOKEN=hf_xxx -e HF_USER=yourname \
  rianders/lerobot-soarm101:dev
```
