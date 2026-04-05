# Lessons Learned

Running notes from building the coachable-robots edge-to-cloud pipeline.
Updated as we discover things — not a polished doc.

---

## Docker / Container Build

### `python:3.12-slim-bookworm` requires `build-essential` + `linux-libc-dev` for evdev
**Problem:** `lerobot` v0.5.0 depends on `pynput` which depends on `evdev`. `evdev` builds from source and needs `linux/input.h` and `gcc`.  
**Fix:** Add to Dockerfile apt installs:
```dockerfile
build-essential \
linux-libc-dev \
```
`linux-headers-generic` is Ubuntu-only. `linux-libc-dev` is the Debian Bookworm equivalent.

### `LEROBOT_HOME` was renamed to `HF_LEROBOT_HOME` in lerobot v0.5.0
**Problem:** Container started fine but any lerobot import raised `ValueError: LEROBOT_HOME is deprecated`.  
**Fix:** Change env var in Dockerfile:
```dockerfile
ENV HF_LEROBOT_HOME="/app"
```

### Cross-building arm64 for Pi 5 requires a `docker-container` buildx builder
The default Docker builder only supports the host architecture. QEMU is installed but the `default` builder doesn't use it.  
**Fix:**
```bash
docker buildx create --name multiarch --driver docker-container --use
docker buildx inspect --bootstrap
# Platforms now include linux/arm64
docker buildx build --platform linux/arm64 --load -t image:tag -f Dockerfile .
```

### BalenaOS uses `balena` not `docker`
On the Pi, the container runtime CLI is `balena`, not `docker`. All `docker run`, `docker pull`, `docker ps` commands must use `balena` instead.

---

## lerobot v0.5.0 API Changes

### `aloha` robot type removed from `lerobot-record`
**Problem:** Our sim mode used `--robot.type=aloha` which no longer exists.  
**Impact:** `lerobot-record` is now real-hardware only. Simulation is not available through the CLI.  
**Workaround:** `USE_SIM=1` now does a pipeline dry-run instead — pulls `lerobot/pusht` from HF Hub and verifies the training entrypoint imports.  
**Public dry-run dataset:** Use `lerobot/pusht` (no auth required). `lerobot/so101_strawberry_grape` requires HF auth even though it's listed as public.

### `python -m lerobot.scripts.control_robot` replaced by `lerobot-calibrate`
The old calibration command was `python -m lerobot.scripts.control_robot --control.type=calibrate`. v0.5.0 ships a `lerobot-calibrate` CLI entry point instead.

### Leader arm uses `--teleop.type`, follower uses `--robot.type` in `lerobot-calibrate`
**Problem:** Passing `--robot.type=so101_leader` fails — `so101_leader` is not a valid robot type.  
**Fix:** Leader is a teleop device, follower is a robot device:
```bash
# Leader:
lerobot-calibrate --teleop.type=so101_leader --teleop.port=/dev/ttyACM0

# Follower:
lerobot-calibrate --robot.type=so101_follower --robot.port=/dev/ttyACM1
```

---

## CHI@Edge Device Profiles

### `pi_serial` only exposes `/dev/ttyACM0`
**Problem:** The SO-ARM101 setup needs two serial ports — leader on `ttyACM0`, follower on `ttyACM1`. The `pi_serial` device profile only whitelists `ttyACM0`.  
**Status:** Helpdesk ticket submitted requesting a custom profile that exposes both.  
**Workaround for local testing:** Run with `--privileged -v /dev:/dev`.

### Available CHI@Edge device profiles for Raspberry Pi
- `pi_serial` → `/dev/ttyACM0` only
- `pi_camera` → `/dev/video*` + memory devices
- `pi_gpio` → `/dev/gpiomem`, `/dev/i2c-1`, `/dev/gpiochip0/1`
- `pi_meter` → `/dev/ttyUSB0`

### `lerobot-find-port` is interactive — can't run headlessly
The script waits for a physical unplug event via `input()`. Pipe/redirect causes `EOFError`. Must run in an interactive SSH session.

---

## Gradio Camera Preview

### Gradio `stream_setup` decorator doesn't exist — use `demo.load()`
**Problem:** Used a non-existent `@img.stream_setup` decorator.  
**Fix:** Use `demo.load(fn=stream_frames, outputs=img)` to auto-start the stream on page load.

### `/dev/video0` is the real camera — ignore `/dev/video23-35`
On BalenaOS, the C920 creates many `/dev/video*` nodes. Only `video0` produces frames (YUYV format). The others are metadata/control nodes that time out with `status=False`.

### SSH tunnel must be opened separately from the remote command
Running `-L 7860:localhost:7860` in the same SSH invocation as a remote command causes argument parsing issues with `balena run`.  
**Fix:** Open the tunnel as a background process first:
```bash
ssh -p 22222 -L 7860:localhost:7860 -f -N root@192.168.4.191
# Then separately:
ssh -p 22222 root@192.168.4.191 "balena run ..."
```

---

## Chameleon Notebook

### Chameleon credentials must be loaded before any `chi.*` calls
Running the notebook without sourcing the RC file produces HTTP 401 on all sites.  
**Fix:** Add a credentials cell at the top that sources `app-cred-coachable-robots-openrc.sh` and injects `OS_*` env vars into the Python session.

### Notebook cell order matters — `pi_run()` helper must be defined before §3a
The camera preview cells call `pi_run()` which is defined in the pull+verify cell above it. Running §3a without running the setup cell first causes `NameError`.

---

## Package Architecture

### Stay at the lerobot CLI boundary — don't import lerobot internals
lerobot v0.5.0 already had breaking changes (`LEROBOT_HOME`, removed robot types). Importing internal APIs would make our code fragile to upstream changes. All lerobot interaction goes through subprocess in `lerobot_cli.py`.  
**Rule:** If it's not in `lerobot --help`, don't depend on it.

### Calibration files need a persistent volume
Calibration data written inside a container is lost when the container exits.  
**Fix:** Always mount a host directory:
```bash
balena run -v /data/calibration:/app/calibration ...
```
The lerobot calibration path is `~/.cache/huggingface/lerobot/calibration/` by default — may need `--robot.calibration_dir` flag to redirect to `/app/calibration`.

---

## Hardware

### SO-ARM101 serial port assignment is not deterministic
Which arm lands on `ttyACM0` vs `ttyACM1` depends on USB enumeration order (which was plugged in first). Must verify with `lerobot-find-port` or by running calibration and checking which arm responds.

### `lsusb` identifies both arms as `QinHeng Electronics USB Single Serial` (1a86:55d3)
No way to distinguish leader from follower by USB ID alone. Physical port assignment or calibration response is the only way.
