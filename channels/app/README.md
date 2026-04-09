# app channel — SO-ARM101 application image

The canonical application image shared by all Pi 5 deployment channels.
Build this first; `chi-edge` and `balena` channels build `FROM` it.

**Tag:** `rianders/lerobot-soarm101:app`

**Contains:** LeRobot v0.5.0, coachable CLI, Gradio, HuggingFace CLI, CPU PyTorch

**Does NOT contain:** openssh-server (channel concern), simulation extras (dev only)

## Build

```bash
make build-app
```

## What's the same across all Pi channels

- LeRobot version
- Servo / camera drivers
- `coachable` CLI and Gradio dashboard
- `docker/scripts/` (collect_demos.sh, fetch_checkpoint.sh)
- `config/fleet.yaml` structure
- `EXPOSE 7860` — Gradio always available
