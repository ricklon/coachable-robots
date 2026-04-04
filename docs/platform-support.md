# Platform Support Matrix

LeRobot v0.5.0 recording and teleoperation support across target systems.

## Supported Robots

Both the **SO-ARM100** and **SO-ARM101** are supported. The SO-ARM101 is a
cosmetic update to the SO-ARM100 — same servos (Feetech STS3215), same
kinematics, same LeRobot configs. Use whichever you have:

| Robot | LeRobot `--robot.type` | LeRobot `--teleop.type` |
|-------|----------------------|------------------------|
| SO-ARM100 follower | `so100_follower` | `so100_leader` |
| SO-ARM101 follower | `so101_follower` | `so101_leader` |

All teleop types (keyboard, gamepad, phone) work with both robots.

## Target Systems

| System | OS | Arch | GPU | Primary Use |
|--------|----|------|-----|-------------|
| Pi 5 on CHI@Edge | BalenaOS | ARM64 | None | Remote data collection via containers |
| Pi 5 local | Raspberry Pi OS / Debian | ARM64 | None | Local data collection |
| Linux laptop | Ubuntu 22.04+ | x86_64 | Optional | Development, recording, simulation |
| macOS | macOS 13+ | Apple Silicon | MPS | Development, recording, simulation |

## Installation

### Pi 5 (CHI@Edge)

Runs inside a Docker container managed by `Request_LeRobot_SOARM101.ipynb`.
The container image (`rianders/lerobot-soarm101:main`) includes LeRobot
and all dependencies. No manual install needed.

### Pi 5 (Local)

```bash
# CPU-only PyTorch to save space
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install lerobot[feetech]
```

### Linux Laptop

```bash
pip install lerobot[feetech,gamepad]

# For simulation environments:
pip install lerobot[pusht]        # gym-pusht (2D pushing task)
pip install lerobot[aloha]        # gym-aloha (bimanual sim)
```

### macOS

```bash
pip install lerobot[feetech,gamepad]

# For simulation environments:
pip install lerobot[pusht]
pip install lerobot[aloha]
```

USB serial drivers: macOS needs the CH340 VCP driver for Feetech servo
communication. Install from the manufacturer or via Homebrew.

## Teleop Input Compatibility

| Teleop Type | CLI Flag | Pi 5 (CHI@Edge) | Pi 5 (Local) | Linux Laptop | macOS |
|---|---|---|---|---|---|
| **Leader arm** | `--teleop.type=so100_leader` or `so101_leader` | YES | YES | YES | YES |
| **Gamepad** | `--teleop.type=gamepad` | YES | YES | YES | YES* |
| **Keyboard** | `--teleop.type=keyboard` | NO (headless) | YES (with display) | YES | YES |
| **Keyboard EE** | `--teleop.type=keyboard_ee` | NO (headless) | YES (with display) | YES | YES |
| **Phone** | `--teleop.type=phone` | YES | YES | YES | YES |

*macOS gamepad uses `hidapi` backend instead of `pygame`. Hardcoded for
Logitech RumblePad 2 — Xbox and PS5 controllers may need byte offset
adjustments in `teleop_gamepad.py`.

### Notes

- **Pi headless**: `keyboard` and `keyboard_ee` require the `DISPLAY`
  environment variable. They are blocked on headless systems (CHI@Edge
  containers, SSH sessions). Use leader arm, gamepad, or phone instead.
- **Gamepad on Pi**: Uses `pygame` joystick subsystem — works headless,
  does not require a display.
- **Phone teleop**: Requires `pip install lerobot[phone]`. Uses IK with
  the SO-100/SO-101 URDF. Control via iOS (HEBI Mobile I/O) or Android
  (WebXR).
- **CPU-only**: Recording and teleop work without a GPU on all platforms.
  PyTorch is required but nothing in the teleop/recording path uses CUDA.

## Simulation Environments

Simulation lets students practice the LeRobot workflow without hardware.

| Environment | Robot | Platforms | Install Extra | Notes |
|---|---|---|---|---|
| **gym-pusht** | 2D T-shape | Linux, macOS | `[pusht]` | Simple 2D pushing task, good for learning the pipeline |
| **gym-aloha** | ALOHA bimanual | Linux, macOS | `[aloha]` | Bimanual manipulation sim |
| **Meta-World** | Sawyer arm | Linux, macOS | `[metaworld]` | 50 manipulation tasks |
| **LeIsaac** | SO-101 | Linux (NVIDIA GPU only) | Separate IsaacSim install | Only SO-101 sim, but requires NVIDIA GPU |
| **LIBERO** | Franka Panda | Linux only | `[libero]` | 130 lifelong learning tasks |

### SO-100/SO-101 Simulation Gap

There is currently no lightweight, cross-platform SO-100/SO-101 simulation
in LeRobot. The only SO-101 sim (LeIsaac) requires an NVIDIA GPU and
Linux — it won't run on Pi, macOS, or AMD GPUs (MI100).

The SO-101 URDF exists at `TheRobotStudio/SO-ARM100/Simulation/SO101/` and
could be used to build a MuJoCo-based environment publishable via
LeRobot's EnvHub. This is a future goal for the project.

**For now**: Use `gym-pusht` or `gym-aloha` on laptops to learn the
LeRobot training pipeline before working with real hardware.

### Running Simulation

```bash
# Record simulated episodes with keyboard teleop
lerobot-record \
    --env.type=pusht \
    --teleop.type=keyboard \
    --dataset.repo_id=USER/pusht_demos \
    --dataset.num_episodes=10

# Train on simulated data (same command as real data)
python lerobot/scripts/train.py \
    --dataset.repo_id=USER/pusht_demos \
    --policy.type=diffusion
```

## Quick Reference: Recording on Each Platform

### Pi 5 (CHI@Edge container)

```bash
lerobot-record \
    --robot.type=so101_follower \
    --teleop.type=so101_leader \
    --robot.cameras='{ top: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 15} }' \
    --dataset.repo_id=USER/dataset_name \
    --dataset.num_episodes=10 \
    --dataset.push_to_hub=true
```

### Pi 5 (Local) with Gamepad

```bash
lerobot-record \
    --robot.type=so100_follower \
    --teleop.type=gamepad \
    --robot.cameras='{ top: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 15} }' \
    --dataset.repo_id=USER/dataset_name \
    --dataset.num_episodes=10 \
    --dataset.push_to_hub=true
```

### Linux Laptop with Keyboard

```bash
lerobot-record \
    --robot.type=so101_follower \
    --teleop.type=keyboard_ee \
    --robot.cameras='{ top: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 15} }' \
    --dataset.repo_id=USER/dataset_name \
    --dataset.num_episodes=10 \
    --dataset.push_to_hub=true
```

### macOS with Phone Teleop

```bash
lerobot-record \
    --robot.type=so100_follower \
    --teleop.type=phone \
    --robot.cameras='{ top: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 15} }' \
    --dataset.repo_id=USER/dataset_name \
    --dataset.num_episodes=10 \
    --dataset.push_to_hub=true
```

## Calibration

Before first use on any platform, calibrate the arms:

```bash
# Calibrate follower
lerobot-calibrate --robot.type=so101_follower

# Calibrate leader (if using leader arm teleop)
lerobot-calibrate --teleop.type=so101_leader
```

Calibration data is saved locally and reused across sessions.
