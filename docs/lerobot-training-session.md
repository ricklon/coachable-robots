# LeRobot Training Session Runbook

This is the current operator runbook for a real coachable-robots LeRobot
training session using CHI@Edge for SO-ARM101 data collection and CHI@TACC MI100
for ACT training.

Use this for the first repeatable training session. Keep the task simple:
`touch_object_v1` before pick-and-place.

## Goals

- Preserve known-good arm calibration.
- Confirm CHI@Edge serial and camera passthrough before collecting data.
- Confirm wrist roll is cable-safe before any demonstration session.
- Collect a small LeRobot dataset and push it to Hugging Face.
- Train an ACT policy on MI100.
- Replay or deploy the checkpoint only after the dataset replay looks correct.

## Session Defaults

| Item | Value |
|------|-------|
| Arm host | `arm-01` or current Tailscale hostname from `just arm-host` |
| Leader port | `/dev/ttyACM0` |
| Follower port | `/dev/ttyACM1` |
| Capture cameras | `/dev/video0`, `/dev/video2` |
| Calibration dir | `/app/calibration` in CHI@Edge container |
| First task | `touch_object_v1` |
| First policy | ACT |
| First dataset size | 10-20 episodes |
| Wrist clamp | +/- 15 degrees |

## 1. Operator Preflight

Run from the control node:

```bash
just check-env
just check-auth-json
just edge-status
just arm-host
just arm-test
```

Expected:

- CHI@Edge container is reachable over Tailscale.
- `/dev/ttyACM0` and `/dev/ttyACM1` are present.
- `/dev/video0` through `/dev/video3` are present.
- Calibration JSON files are present.

If the Pi was rebooted or physically serviced, recreate the CHI@Edge container
before trusting device mounts.

## 2. Back Up Calibration

The same physical leader and follower arms are reused across sessions. Losing
the calibration JSON files means recalibrating before training.

```bash
just arm-calibration-backup label=alpha-before-training
just arm-calibration-backups
```

Backups are stored under `calibration-backups/`, which is intentionally ignored
by git. Publish them only to a private artifact store if a shared backup is
needed.

Restore only when the same physical arms and motor IDs are attached:

```bash
just arm-calibration-restore archive=calibration-backups/<backup>.tgz
```

## 3. Camera Check

Use the camera preview only when no robot recording process is using the cameras.

```bash
just arm-preview 0
just tunnel-arm
```

Open `http://localhost:7860`, confirm the workspace is visible, then stop the
preview before teleoperation or collection:

```bash
just arm-preview-stop
```

For two-camera checks, verify `/dev/video0` and `/dev/video2`; `/dev/video1`
and `/dev/video3` are metadata/control nodes.

## 4. Wrist-Safe Teleop Check

Put leader and follower wrists in the same relaxed, cable-safe start pose.

```bash
just arm-teleop-safe 30 15
```

Acceptance criteria:

- Follower mirrors leader motion without a bus timeout.
- Follower wrist roll stays near the matched start pose.
- Gripper cable does not twist, pull, or unplug.

Use the freeze mode for a stricter test:

```bash
just arm-teleop-freeze-wrist 30
```

Stock LeRobot treats `wrist_roll` as a full-turn motor and does not learn a
cable-safe home position for this setup. The safe teleop wrapper records the
matched leader/follower wrist start positions and maps wrist roll relatively
with a clamp.

## 5. Dataset Collection Plan

Start with a task that does not require gripper closure or wrist roll:

```text
touch_object_v1
```

Recommended first collection:

- 10 episodes for a plumbing test.
- 20 episodes for the first real ACT run.
- Consistent start pose before every episode.
- Slow, smooth movements.
- Same object and same workspace location.

Use the wrist-safe recorder for real arm datasets. It uses LeRobot's dataset
writer and episode timing, but clamps follower wrist roll the same way as
`just arm-teleop-safe`.

Current collection entrypoint:

```bash
just arm-record-safe touch_object_v1 20 "Touch the red block on the table"
```

## 6. Replay Before Training

Replay at least one episode before spending MI100 time:

```bash
just arm-replay repo=$HF_USER/touch_object_v1 episode=0
```

Acceptance criteria:

- Motion matches the intended task.
- Cameras captured the workspace.
- The arm starts and resets consistently.
- No unsafe wrist or gripper cable behavior appears.

If replay looks wrong, recollect before training.

## 7. MI100 Training Prep

Reserve and provision the training node:

```bash
just reserve
just provision
just test-node
```

Confirm the node is really an MI100 host:

```bash
ssh cc@train-mi100 'lspci -nn | egrep -i "AMD|Instinct|MI100|1002"; rocm-smi'
```

If `lspci` does not show an AMD/MI100 device, do not train. Release or ignore
that generic host and create a fresh `gpu_mi100` lease.

## 8. ACT Training Target

Use ACT for the first policy. MI100 is gfx908 hardware and does not support
Flash Attention 2, so ACT is the safest default.

Training shape:

```text
dataset.repo_id=$HF_USER/touch_object_v1
policy=act
steps=50k-80k for the first small task
```

Run training from the notebook path or an operator training recipe once the
dataset replay has passed. Keep the run in `tmux` on the MI100 node so it
survives SSH disconnects.

## 9. Checkpoint and Deployment Gate

Before deploying a policy back to the arm:

- Confirm training logs show progress and no dataloader/camera schema errors.
- Upload the checkpoint to Hugging Face.
- Download/fetch the checkpoint on the edge container.
- Run a short autonomous test with the arm in a clear workspace.

Do not use pick-and-place as the first deployment test. Use touch first, then
graduate to gripper tasks after the safe recording path exists.

## 10. Cleanup

After the session:

```bash
just arm-preview-stop
just arm-calibration-backup label=alpha-after-training
```

Release scarce cloud resources when no longer needed:

```bash
COACHABLE_CONFIRM_RELEASE=yes just release
```

Keep the CHI@Edge container only if the next session needs the same live arm
state. After a Pi reboot or hardware maintenance, recreate it.
