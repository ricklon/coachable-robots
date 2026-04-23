# Coaching Workflow

Step-by-step guide for coaches (students, instructors, agents) working with
SO-ARM101 robots on the coachable platform.

> **Current path:** for CHI@Edge + Tailscale operation and the first real
> LeRobot training session, use
> [lerobot-training-session.md](lerobot-training-session.md). This file keeps
> the local Balena/Pi workflow because it is still useful for host-level repair,
> camera isolation, and offline robot work.

## Access Modes

Use one robot owner at a time:

| Mode | Access | Use |
|------|--------|-----|
| CHI@Edge container | `just arm-*`, `ssh root@arm-01` | Current teaching/training path |
| Balena host | `ssh -p 22222 root@192.168.4.191` | Host repair, local preview, device checks |
| MI100 training node | `just reserve`, `just provision`, `ssh cc@train-mi100` | Cloud training |

The Pi has one set of serial ports and cameras. Do not run Balena preview,
Balena robot workloads, and CHI@Edge robot workloads at the same time.

## Prerequisites

- Pi 5 running BalenaOS with `rianders/lerobot-soarm101:latest` pulled
- SO-ARM101 leader + follower arms connected via USB (ttyACM0, ttyACM1)
- Logitech C920 webcam connected (video0)
- `config/fleet.yaml` configured for your lab (see `config/fleet.example.yaml`)
- HuggingFace account (`ricklon`) with write-scoped token

---

## 0. Verify Fleet

Check which robots are available and who is assigned:

```bash
ssh -p 22222 -t root@192.168.4.191 \
  "balena run -i \
   -v /mnt/data/fleet.yaml:/app/config/fleet.yaml \
   rianders/lerobot-soarm101:latest \
   coachable --fleet /app/config/fleet.yaml fleet"
```

---

## 1. Verify Devices

Confirm arms and camera are visible on the Pi:

```bash
ssh -p 22222 root@192.168.4.191 "ls /dev/ttyACM* /dev/video0"
```

Expected output:
```
/dev/ttyACM0  /dev/ttyACM1  /dev/video0
```

If `ttyACM*` are missing: check USB connections and power to the servo controller boards.

> **Port assignment is not deterministic.** `ttyACM0`/`ttyACM1` can swap on reconnect.
> The fleet config uses serial numbers to track which is which, but always confirm
> with a teleoperate test (Step 3b) before collecting.

---

## 2. Camera Preview

Verify the camera view and adjust framing before collecting demos.

**Open SSH tunnel (keep this terminal open):**
```bash
ssh -p 22222 -L 7860:localhost:7860 -f -N root@192.168.4.191
```

**Start the preview container:**
```bash
ssh -p 22222 root@192.168.4.191 \
  "balena run -d --privileged \
   --device=/dev/video0 \
   -p 7860:7860 \
   -v /mnt/data/fleet.yaml:/app/config/fleet.yaml \
   rianders/lerobot-soarm101:latest \
   coachable --fleet /app/config/fleet.yaml preview --robot alpha"
```

**Open in browser:** http://localhost:7860

The live feed starts automatically. Adjust camera position until the
full workspace (pick and place area) is visible.

> **Important:** Note the container name from `balena ps`. You must stop it
> before collecting (Step 5) — it holds `/dev/video0` open.

---

## 3. Motor Setup (first time only)

> Skip this if the arms were pre-configured by TheRobotStudio.
> You'll know motors need setup if calibration gives a "No motor found" error.

**Follower arm:**
```bash
ssh -p 22222 -t root@192.168.4.191 \
  "balena run -it --privileged \
   --device=/dev/ttyACM1 \
   rianders/lerobot-soarm101:latest \
   lerobot-setup-motors \
     --robot.type=so101_follower \
     --robot.port=/dev/ttyACM1 \
     --robot.id=alpha_follower"
```

Connect each motor individually when prompted.

**Leader arm:**
```bash
ssh -p 22222 -t root@192.168.4.191 \
  "balena run -it --privileged \
   --device=/dev/ttyACM0 \
   rianders/lerobot-soarm101:latest \
   lerobot-setup-motors \
     --teleop.type=so101_leader \
     --teleop.port=/dev/ttyACM0 \
     --teleop.id=alpha_leader"
```

---

## 3b. Confirm Port Assignment (teleoperate test)

Before collecting, verify which arm is which. Move the leader arm and watch:

```bash
ssh -p 22222 -t root@192.168.4.191 \
  "balena run -it --privileged \
   --device=/dev/ttyACM0 \
   --device=/dev/ttyACM1 \
   -v /mnt/data/calibration:/app/calibration \
   rianders/lerobot-soarm101:latest \
   lerobot-teleoperate \
     --robot.type=so101_follower \
     --robot.port=/dev/ttyACM1 \
     --robot.id=alpha_follower \
     --robot.calibration_dir=/app/calibration \
     --teleop.type=so101_leader \
     --teleop.port=/dev/ttyACM0 \
     --teleop.id=alpha_leader \
     --teleop.calibration_dir=/app/calibration"
```

**What to expect:**
- The follower arm's motors stiffen immediately on connect
- Move the leader arm — the follower should mirror your movements
- If motors activate on the wrong arm: swap `leader_port`/`follower_port` in `fleet.yaml`

Press `Ctrl+C` to exit (exits cleanly).

---

## 4. Calibrate

> Run once per arm pair, or after any motor replacement or reassembly.
> Calibration is stored in servo EEPROM and in `/mnt/data/calibration/*.json`.
> It persists across container restarts and reboots.

Back up the JSON files after a successful calibration. We use the same leader
and follower arms across sessions, and losing these files means recalibrating
before the next training run:

```bash
just arm-calibration-backup label=alpha-good
just arm-calibration-backups
```

Restore only when you are sure the same physical arms and motor IDs are attached:

```bash
just arm-calibration-restore archive=calibration-backups/<backup>.tgz
```

```bash
ssh -p 22222 -t root@192.168.4.191 \
  "balena run -it --privileged \
   --device=/dev/ttyACM0 \
   --device=/dev/ttyACM1 \
   -v /mnt/data/fleet.yaml:/app/config/fleet.yaml \
   -v /mnt/data/calibration:/app/calibration \
   rianders/lerobot-soarm101:latest \
   coachable --fleet /app/config/fleet.yaml calibrate --robot alpha \
     --calibration-dir /app/calibration"
```

**What happens:**
1. Follower arm calibrates first — move each joint to its physical min/max when prompted
2. Leader arm calibrates second — same process
3. Move each joint slowly to its mechanical limits and press Enter
4. **Do not force joints past their mechanical stops**

**Joints (6 per arm):** shoulder pan → shoulder lift → elbow flex → wrist flex → wrist roll → gripper

> **Gripper cable warning:** The wrist_roll joint can pull the gripper servo cable
> (motor ID 6) loose during calibration. Route the cable with slack to allow full
> rotation. If you see "Missing motor IDs: 6" — reseat the cable and retry.

---

## 5. Collect Demonstrations

**First: stop the camera preview container** (it holds `/dev/video0`):
```bash
ssh -p 22222 root@192.168.4.191 "balena ps"
# Find the preview container name, e.g. "competent_benz"
ssh -p 22222 root@192.168.4.191 "balena stop competent_benz"
```

**Then collect:**
```bash
ssh -p 22222 -t root@192.168.4.191 \
  "balena run -it --privileged \
   --device=/dev/ttyACM0 \
   --device=/dev/ttyACM1 \
   --device=/dev/video0 \
   -v /mnt/data/fleet.yaml:/app/config/fleet.yaml \
   -v /mnt/data/calibration:/app/calibration \
   -v /mnt/data/datasets:/app/data \
   -e HF_TOKEN=\$(cat /mnt/data/hf_token) \
   rianders/lerobot-soarm101:latest \
   coachable --fleet /app/config/fleet.yaml collect \
     --robot alpha \
     --dataset pick_block \
     --episodes 20 \
     --task 'Pick up the block and place it in the box' \
     --calibration-dir /app/calibration \
     --dataset-root /app/data"
```

**When to start moving:**
After the command starts, lerobot prints a large config block — ignore it.
A banner will appear:
```
==================================================
WAIT: Ignore the config dump below.
Watch for:  'Recording episode 0'
THAT is when you start moving the leader arm.
==================================================
```
Only start your demonstration when you see `Recording episode 0`.

The CLI also prints the exact timing window for each episode:
```
Episode 0: RECORD 0s–30s  →  RESET 30s–40s (return arm to start)
Episode 1: RECORD 40s–70s  →  RESET 70s–80s ...
```

**Tips:**
- Demonstrate slowly and smoothly — the policy learns from your style
- Keep demonstrations consistent (same start position each episode)
- 20 episodes is a good starting point; 50+ for better policies
- Return the arm to the home position during each reset window

Dataset is pushed to HuggingFace Hub at:
`https://huggingface.co/datasets/ricklon/soarm101-{dataset}`

---

## 5b. Replay to Verify

Replay the last recorded episode to confirm the data was captured correctly:

```bash
ssh -p 22222 -t root@192.168.4.191 \
  "balena run -it --privileged \
   --device=/dev/ttyACM1 \
   -v /mnt/data/calibration:/app/calibration \
   -v /mnt/data/datasets:/app/data \
   rianders/lerobot-soarm101:latest \
   coachable --fleet /app/config/fleet.yaml replay \
     --robot alpha \
     --dataset ricklon/soarm101-pick_block \
     --episode 0 \
     --dataset-root /app/data"
```

The follower arm should reproduce your demonstration movement. If it makes no
movement or only twitches, the episode was likely recorded with the arms on
wrong ports — check LESSONS_LEARNED.md for the flat-values diagnosis.

---

## 5c. Push Dataset (if not auto-pushed)

If `--no-push` was used or the push failed, push manually:

```bash
./scripts/push_dataset.sh pick_block
```

The script prompts for your HF write token, transfers it securely to the Pi,
and pushes the dataset from the container. Token is never written to disk locally.

---

## 6. Train (on Chameleon MI100)

From the Chameleon JupyterHub notebook, run Part 4 to trigger training.
Or SSH to the MI100 node and run:

```bash
conda activate lerobot
python lerobot/scripts/train.py \
    --dataset.repo_id=ricklon/soarm101-pick_block \
    --policy.path=lerobot/act \
    --output_dir=outputs/train/act_pick_block \
    --policy.device=cuda
```

---

## 7. Fetch Trained Policy

After training completes and the checkpoint is uploaded to HF Hub:

```bash
ssh -p 22222 -t root@192.168.4.191 \
  "balena run -it --privileged \
   -v /mnt/data/checkpoints:/app/checkpoints \
   rianders/lerobot-soarm101:latest \
   coachable fetch --repo ricklon/act-pick_block"
```

---

## 8. Run Policy (Autonomous Execution)

```bash
ssh -p 22222 -t root@192.168.4.191 \
  "balena run -it --privileged \
   --device=/dev/ttyACM1 \
   --device=/dev/video0 \
   -v /mnt/data/fleet.yaml:/app/config/fleet.yaml \
   -v /mnt/data/calibration:/app/calibration \
   -v /mnt/data/checkpoints:/app/checkpoints \
   rianders/lerobot-soarm101:latest \
   coachable --fleet /app/config/fleet.yaml run \
     --robot alpha \
     --checkpoint /app/checkpoints/latest \
     --task 'Pick up the block and place it in the box'"
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `No motor found with ID 1` | Motors not configured | Run Step 3 (motor setup) |
| `Missing motor IDs: 6` | Gripper cable unplugged | Reseat cable on wrist servo; retry |
| `ttyACM0: Permission denied` | Missing `--device` flag | Add `--device=/dev/ttyACM0` |
| `OCI runtime: open /dev/console` | Using `-v /dev:/dev` | Use `--privileged` + `--device` flags instead |
| Wrong arm responds to leader | Leader/follower ports swapped | Run teleoperate test (Step 3b); swap ports in `fleet.yaml` |
| All joint values flat (0° range) | Recording from wrong port | See above |
| Camera black / no image | Camera index wrong or held by preview | Stop preview container; verify `video0` |
| `fps must be one of [10]` | C920 in YUYV mode | fourcc=MJPG is set in `lerobot_cli.py` — rebuild image |
| `/data/calibration: read-only` | BalenaOS read-only root | Use `/mnt/data/calibration` |
| `unknown flag: --rm` | balena-engine limitation | Omit `--rm`; use `balena rm` to clean up |
| `FileExistsError` on dataset root | Wrong root path | Pass `--dataset-root /app/data` (parent only, CLI adds repo_id) |
| Push fails with token error | Token has special chars / expired | Use `scripts/push_dataset.sh` for secure token passing |
