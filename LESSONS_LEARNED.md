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

### Dual serial ports: pass `["ttyacm0","ttyacm1"]` in `device_profiles`
**Problem:** The SO-ARM101 setup needs two serial ports — leader on `ttyACM0`, follower on `ttyACM1`. The `pi_serial` device profile only whitelists `ttyACM0`.  
**Fix (confirmed by Chameleon helpdesk):** Pass each port as a lowercase list entry in `device_profiles`:
```python
device_profiles=["ttyacm0", "ttyacm1", "pi_camera"]
```
No custom named profile needed — the port names themselves are valid profile entries.

### Available CHI@Edge device profiles for Raspberry Pi
- `ttyacm0` → `/dev/ttyACM0` (individual serial port entry)
- `ttyacm1` → `/dev/ttyACM1` (individual serial port entry)
- `pi_serial` → `/dev/ttyACM0` only (legacy; use `ttyacm0`/`ttyacm1` directly instead)
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
**Fix:** Add a credentials cell at the top that sources `app-cred-chi-edge-openrc.sh` (CHI@Edge) or `app-cred-kvm-tacc-openrc.sh` (KVM@TACC) and injects `OS_*` env vars into the Python session.

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
Which arm lands on `ttyACM0` vs `ttyACM1` depends on USB enumeration order (which was plugged in first, or last disconnected/reconnected). Never hardcode assumptions — verify on every session.

**Definitive identification method:** run `lerobot-teleoperate` and watch which arm's motors activate. The arm that stiffens = follower (receives mirrored commands). The arm that stays loose = leader (reads your input).

Confirmed serial numbers for the alpha station:
- Leader: `5970072696` → always configured as `/dev/ttyACM0`
- Follower: `5970072616` → always configured as `/dev/ttyACM1`

These are stored in `config/fleet.yaml` as `leader_serial` and `follower_serial`.

### `lsusb` identifies both arms as `QinHeng Electronics USB Single Serial` (1a86:55d3)
No way to distinguish leader from follower by USB ID alone. Use `lerobot-teleoperate` — the arm whose motors lock up on connect is the follower.

### Missing motor ID 6 is almost always an accidental disconnect
**Symptom:** `FeetechMotorsBus motor check failed — Missing motor IDs: 6`  
**Cause:** The gripper servo cable can pull out when rotating the wrist during calibration or teleoperation. The servo is physically present but not on the bus.  
**Fix:** Check the cable connecting motor 6 (gripper) and reseat it. Re-run calibration or `lerobot-setup-motors` only if the ID was never assigned.

### Gripper servo unplugs easily during wrist rotation
The wrist_roll joint twists the servo cable bundle. During calibration, when moving joints through their full range, the gripper cable (motor ID 6) can disconnect.  
**Prevention:** Before calibration, route the gripper cable with enough slack to allow full wrist rotation without tension.

### Calibration files persist across container restarts
Files saved to `/mnt/data/calibration` on BalenaOS survive reboots and container updates. Mount with `-v /mnt/data/calibration:/app/calibration` and pass `--robot.calibration_dir=/app/calibration` to avoid re-calibrating every session. Only recalibrate if a servo is replaced or the arm is reassembled.

---

## BalenaOS Container Runtime

### `balena run --rm` is not supported
**Problem:** `balena run --rm ...` exits with "unknown flag: --rm".  
**Cause:** balena-engine is a fork of Docker with `--rm` removed.  
**Fix:** Omit `--rm` entirely. Containers persist until manually removed with `balena rm`.

### `-v /dev:/dev` breaks interactive containers on BalenaOS
**Problem:** `balena run -it -v /dev:/dev ...` fails with `OCI runtime: open /dev/console: no such file or directory`.  
**Cause:** BalenaOS does not expose `/dev/console` in its `/dev` tree.  
**Fix:** Use `--privileged` with specific `--device` flags:
```bash
balena run -it --privileged \
  --device=/dev/ttyACM0 \
  --device=/dev/ttyACM1 \
  --device=/dev/video0 \
  ...
```
`--privileged` alone (without `-v /dev:/dev`) works correctly.

### UVC cameras require `--privileged` for container access
Using `--device=/dev/videoN` alone is insufficient for USB cameras (UVC protocol). The kernel exposes many `/dev/videoN` nodes for a single camera (metadata, control, etc.), and the container also needs memory device access.  
**Fix:** Always pair camera device access with `--privileged`:
```bash
balena run -it --privileged --device=/dev/video0 ...
```

### Stop camera preview container before collecting
The Gradio preview container holds `/dev/video0` open. Attempting to record while it is running causes lerobot to fail acquiring the camera.  
**Fix:** Before each collect session, identify and stop the preview container:
```bash
ssh -p 22222 root@192.168.4.191 "balena ps"
# Find the Gradio container name (e.g. "competent_benz")
ssh -p 22222 root@192.168.4.191 "balena stop competent_benz"
```
The coachable `collect` CLI checks with `fuser /dev/videoN` and warns if the device is held.

---

## Logitech C920 Camera

### C920 defaults to 10 fps without MJPG fourcc
**Problem:** `lerobot-record` configured with `width=1280, height=720, fps=30` fails with `fps must be one of [10]`.  
**Cause:** The C920 defaults to YUYV pixel format, which maxes out at 10 fps at 720p due to USB bandwidth. MJPEG compression allows 30 fps at full resolution.  
**Fix:** Add `"fourcc": "MJPG"` to the camera config in `lerobot_cli.py`:
```python
"fourcc": "MJPG",
```
This is now baked into the `record()` function.

---

## Dataset Collection

### Dataset root must include `repo_id` — not just the parent directory
**Problem:** `lerobot-record --dataset.root=/app/data` caused `FileExistsError` when resuming, and saved data into `/app/data` instead of a per-dataset subdirectory.  
**Cause:** lerobot's `root` flag is the *full path to the dataset*, not a parent directory. If you pass the parent, it tries to use the entire data dir as one flat dataset.  
**Fix:**
```bash
--dataset.root=/app/data/ricklon/soarm101-pick_block
# OR equivalently in code:
cmd.append(f"--dataset.root={dataset_root}/{repo_id}")
```

### `--play_sounds=false` flag required — and `speech-dispatcher` must be installed
**Problem:** Even with `--play_sounds=false`, lerobot imports the TTS module and fails if `spd-say` is not on PATH.  
**Fix (both required):**
1. Always pass `--play_sounds=false` to `lerobot-record`
2. Add `speech-dispatcher` to the Dockerfile apt installs (provides `spd-say`)

### lerobot dumps a full config before recording — users don't know when to start
**Problem:** lerobot prints hundreds of lines of config after the command starts. Users have no idea when the recording window actually opens and will miss the first seconds of each episode.  
**Fix:** Added a warning banner in `lerobot_cli.py` `record()` that prints before the subprocess call:
```
==================================================
WAIT: Ignore the config dump below.
Watch for:  'Recording episode 0'
THAT is when you start moving the leader arm.
==================================================
```

### All recorded joint values flat (0-range) — arm was on wrong port
**Symptom:** `lerobot-replay` does nothing. Inspection shows all joints recorded 0° range.  
**Cause:** The leader arm (the arm the coach moves) was connected to `ttyACM1` but the config had leader on `ttyACM0`. lerobot was reading from the follower arm (which wasn't being moved).  
**Fix:** Verify port assignment with `lerobot-teleoperate` before collecting. The arm that moves freely = leader; record its port as `leader_port`.

---

## HuggingFace Hub

### HF account is `ricklon` — not `rianders`
The container image is hosted at `rianders/lerobot-soarm101` (Docker Hub) but the HuggingFace account for datasets and models is `ricklon`. These are different services with different accounts.  
- Docker Hub image: `rianders/lerobot-soarm101:latest`
- HF datasets: `ricklon/soarm101-{task}`
- HF models: `ricklon/act-{task}`

### Passing HF token via `-e HF_TOKEN=$TOKEN` fails for tokens with special characters
**Problem:** HF tokens contain `_` and mixed case and can contain characters that break shell variable interpolation when passed through SSH + container `-e`.  
**Fix:** Write the token to a temp file, `scp` it to the Pi, then read it inside the container:
```bash
TMPFILE=$(mktemp)
echo "$HF_TOKEN" > "$TMPFILE"
scp -P 22222 "$TMPFILE" root@192.168.4.191:/tmp/hf_token
rm "$TMPFILE"
ssh -p 22222 root@192.168.4.191 \
  "HF_TOKEN=\$(cat /tmp/hf_token) && balena run -i -e HF_TOKEN=\$HF_TOKEN ..."
```
See `scripts/push_dataset.sh` for the full implementation.

### HF tokens shown in screenshots are immediately auto-revoked
HuggingFace's security system detects token strings in public content and immediately revokes them. If a token appears in a screenshot, log, or shared file, treat it as compromised and rotate immediately at https://huggingface.co/settings/tokens.

---

## CHI@Edge Remote Access

### Notebook needs a reconnect cell — container creation deletes existing containers
The `create-container` cell deletes any existing container before recreating it. Reopening the notebook in a new session and running top-to-bottom destroys running work.  
**Fix:** Added a "Reconnect to existing session" cell at the top of `Request_LeRobot_SOARM101.ipynb` that looks up `my_lease` and `my_container` by name and prints the floating IP without touching anything.

### `chi.set("project_name", ...)` breaks authentication with application credentials
Application credentials in OpenStack v3 are already project-scoped. Adding `chi.set("project_name", "CHI-261589")` causes keystoneauth to require `project_domain_id` or `project_domain_name`, which then fails.  
**Fix:** Omit `chi.set("project_name", ...)` entirely when using application credentials.

### python-chi 0.15.x uses functional API; notebooks require 1.0+ class-based API
`from chi.container import Container` only exists in python-chi 1.0+. Local installs typically have 0.15.x.  
**Fix:** Upgrade locally:
```bash
pip install --upgrade python-chi --break-system-packages
```
**Note:** `python-chi-edge 0.2.4` pins `python-chi<0.16.0` — it becomes incompatible after upgrade. This is acceptable since chi-edge CLI is used separately.

### CHI@Edge container network is `caliconet`, not `containernet1`
`create_container()` defaults to `network_name="containernet1"` which doesn't exist on CHI@Edge.  
**Fix:** Pass `network_name="caliconet"` explicitly. Available networks: `public` and `caliconet`.

### "Unschedulable" containers = Pi k8s node is NotReady
When a container lands in `Error` status with `status_detail: Unschedulable`, the Pi's Kubernetes node is not ready — not a code problem.  
**Diagnosis:**
```bash
chi-edge device show soarm101-1
# Check 'last_seen' timestamp in balena health — if days old, Pi is offline
```
**Fix:** Power cycle the Pi, confirm Ethernet is connected, wait 5-10 min for k8s to rejoin. Then:
```bash
chi-edge device sync soarm101-1
# Wait ~90s, then re-check all states are STEADY
```

### CHI@Edge openrc lives in `ansible/`, not `~/Downloads/`
The correct credential file for CHI@Edge is `ansible/app-cred-chi-edge-openrc.sh`.  
`~/Downloads/app-cred-coachable-robots-openrc.sh` and `app-cred-kvm-tacc-openrc.sh` are both KVM@TACC credentials despite their names.

### Stale coordinator lock blocks all container scheduling after hardware maintenance
**Symptom:** Containers stuck in `Error / Unschedulable` immediately after Pi reboot following physical work.  
**Cause:** The CHI@Edge coordinator holds a distributed update lock. If the Pi is powered off mid-operation (e.g. for hardware maintenance), the lock is never released.  
**Fix:**
```bash
ssh -p 22222 root@192.168.4.191 \
  "balena restart coordinator_<uuid>"
# Logs will show: "Breaking stale update lock from previous run"
```
Also restart k3s and re-sync:
```bash
ssh -p 22222 root@192.168.4.191 "balena restart k3s-rpi5_<uuid>"
chi-edge device sync soarm101-1
```

### `pi_camera` device profile requires CSI devices not present on Pi 5 with USB cameras
**Symptom:** Container Unschedulable with:  
`1 Insufficient smarter-devices/vchiq, 1 Insufficient smarter-devices/vcsm-cma, 1 Insufficient smarter-devices/v4l-subdev0, 1 Insufficient smarter-devices/video10-18`  
**Cause:** The `pi_camera` profile was designed for Pi 4 CSI camera modules. `vchiq`, `vcsm-cma`, and `video10-18` are VideoCore / CSI interface devices. The Pi 5 with USB cameras (Logitech C920) only exposes `video0` and `video1` — the CSI devices don't exist.  
**Workaround for local network:** Use `balena run` directly with `--device=/dev/video0 --device=/dev/video1 --privileged` — bypasses CHI@Edge scheduling entirely.  
**Long-term fix needed:** Submit a Chameleon helpdesk ticket requesting a USB-camera-only device profile (e.g. `usb_camera`) that maps to `video0`/`video1` without requiring CSI devices.

### BalenaOS root filesystem is read-only — use `/mnt/data/` for persistent files
`/app/` and most of the root filesystem are read-only on BalenaOS. The writable persistent volume is `/mnt/data/`.  
**Fix:** Store fleet.yaml and calibration files at `/mnt/data/config/` and `/mnt/data/calibration/`:
```bash
ssh -p 22222 root@192.168.4.191 "mkdir -p /mnt/data/config"
scp -P 22222 config/fleet.yaml root@192.168.4.191:/mnt/data/config/fleet.yaml
```
Mount into containers with `-v /mnt/data/config/fleet.yaml:/app/config/fleet.yaml`.
