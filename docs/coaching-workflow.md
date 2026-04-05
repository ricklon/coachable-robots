# Coaching Workflow

Step-by-step guide for coaches (students, instructors, agents) working with
SO-ARM101 robots on the coachable platform.

## Prerequisites

- Pi 5 running BalenaOS with `rianders/lerobot-soarm101:latest` pulled
- SO-ARM101 leader + follower arms connected via USB (ttyACM0, ttyACM1)
- Logitech C920 webcam connected (video0)
- `config/fleet.yaml` configured for your lab (see `config/fleet.example.yaml`)
- HuggingFace account with write access

---

## 0. Verify Fleet

Check which robots are available and who is assigned:

```bash
ssh -p 22222 -t root@192.168.4.191 \
  "balena run --rm \
   -v /path/to/fleet.yaml:/app/config/fleet.yaml \
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
  "balena run -d --rm --privileged -v /dev:/dev \
   -p 7860:7860 \
   rianders/lerobot-soarm101:latest \
   coachable --fleet /app/config/fleet.yaml preview --robot alpha"
```

**Open in browser:** http://localhost:7860

The live feed starts automatically. Adjust camera position until the
full workspace (pick and place area) is visible.

---

## 3. Motor Setup (first time only)

> Skip this if the arms were pre-configured by TheRobotStudio.
> You'll know motors need setup if calibration gives a "No motor found" error.

**Follower arm:**
```bash
ssh -p 22222 -t root@192.168.4.191 \
  "balena run -it \
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
  "balena run -it \
   --device=/dev/ttyACM0 \
   rianders/lerobot-soarm101:latest \
   lerobot-setup-motors \
     --teleop.type=so101_leader \
     --teleop.port=/dev/ttyACM0 \
     --teleop.id=alpha_leader"
```

---

## 4. Calibrate

> Run once per arm pair, or after any motor replacement.
> Calibration files are saved to `/mnt/data/calibration` on the Pi.

```bash
ssh -p 22222 -t root@192.168.4.191 \
  "balena run -it \
   --device=/dev/ttyACM0 \
   --device=/dev/ttyACM1 \
   -v /tmp/fleet.yaml:/app/config/fleet.yaml \
   -v /mnt/data/calibration:/app/calibration \
   rianders/lerobot-soarm101:latest \
   coachable --fleet /app/config/fleet.yaml calibrate --robot alpha"
```

**What happens:**
1. Follower arm calibrates first — move each joint to min/max when prompted
2. Leader arm calibrates second — same process
3. Move each joint slowly to its physical limits and press Enter
4. Don't force joints past their mechanical stops

**Joints (6 per arm):** shoulder pan → shoulder lift → elbow flex → wrist flex → wrist roll → gripper

---

## 5. Collect Demonstrations

Coach the robot by demonstrating the task with the leader arm.
The follower arm mirrors your movements and records the episode.

```bash
ssh -p 22222 -t root@192.168.4.191 \
  "balena run -it \
   --device=/dev/ttyACM0 \
   --device=/dev/ttyACM1 \
   -v /tmp/fleet.yaml:/app/config/fleet.yaml \
   -v /mnt/data/calibration:/app/calibration \
   -v /mnt/data/datasets:/app/data \
   rianders/lerobot-soarm101:latest \
   coachable --fleet /app/config/fleet.yaml collect \
     --robot alpha \
     --dataset pick_block \
     --episodes 20 \
     --task 'Pick up the block and place it in the box'"
```

Dataset will be pushed to HuggingFace Hub at:
`https://huggingface.co/datasets/{hf_user}/soarm101-{dataset}`

**Tips:**
- Demonstrate slowly and smoothly — the policy learns from your style
- Keep demonstrations consistent (same start position each episode)
- 20 episodes is a good starting point; 50+ for better policies

---

## 6. Train (on Chameleon MI100)

From the Chameleon JupyterHub notebook, run Part 4 to trigger training.
Or SSH to the MI100 node and run:

```bash
conda activate lerobot
python lerobot/scripts/train.py \
    --dataset.repo_id={hf_user}/soarm101-pick_block \
    --policy.path=lerobot/act \
    --output_dir=outputs/train/act_pick_block \
    --policy.device=cuda
```

---

## 7. Fetch Trained Policy

After training completes and the checkpoint is uploaded to HF Hub:

```bash
ssh -p 22222 -t root@192.168.4.191 \
  "balena run -it \
   -v /mnt/data/checkpoints:/app/checkpoints \
   rianders/lerobot-soarm101:latest \
   coachable fetch --repo {hf_user}/act-pick_block"
```

---

## 8. Run Policy (Autonomous Execution)

```bash
ssh -p 22222 -t root@192.168.4.191 \
  "balena run -it \
   --device=/dev/ttyACM1 \
   -v /tmp/fleet.yaml:/app/config/fleet.yaml \
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
| `ttyACM0: Permission denied` | Missing `--device` flag | Add `--device=/dev/ttyACM0` |
| Wrong arm responds to leader | Leader/follower ports swapped | Swap `leader_port`/`follower_port` in `fleet.yaml` |
| Camera black / no image | Wrong camera index | Try `--camera 1` or `--camera 2` |
| `/data/calibration: read-only` | BalenaOS read-only root | Use `/mnt/data/calibration` instead |
| `OCI runtime: open /dev/console` | Full `-v /dev:/dev` mount | Use `--device` flags for specific devices only |
