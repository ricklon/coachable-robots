"""
lerobot_cli.py — Subprocess wrappers around the lerobot CLI.

This is the single file that knows about lerobot flag names.
If lerobot changes its CLI, only this file needs updating.

No lerobot imports. All calls go through subprocess.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from coachable.fleet import Robot


def calibrate(robot: Robot, calibration_dir: Path | None = None) -> None:
    """Calibrate both follower and leader arms for a robot station.

    In lerobot v0.5.0:
    - Follower arm is a robot device:  --robot.type=so101_follower
    - Leader arm is a teleop device:   --teleop.type=so101_leader

    Calibrate follower first (per lerobot docs), then leader.
    """
    # Calibrate follower (robot) first
    cmd = [
        "lerobot-calibrate",
        f"--robot.type=so101_follower",
        f"--robot.port={robot.follower_port}",
        f"--robot.id={robot.name}_follower",
    ]
    if calibration_dir:
        cmd.append(f"--robot.calibration_dir={calibration_dir}")
    print(f"Calibrating follower (so101_follower) on {robot.follower_port}...")
    subprocess.run(cmd, check=True)

    # Calibrate leader (teleop) second
    cmd = [
        "lerobot-calibrate",
        f"--teleop.type=so101_leader",
        f"--teleop.port={robot.leader_port}",
        f"--teleop.id={robot.name}_leader",
    ]
    if calibration_dir:
        cmd.append(f"--teleop.calibration_dir={calibration_dir}")
    print(f"Calibrating leader (so101_leader) on {robot.leader_port}...")
    subprocess.run(cmd, check=True)


def record(
    robot: Robot,
    repo_id: str,
    num_episodes: int,
    task: str,
    calibration_dir: Path | None = None,
    dataset_root: Path | None = None,
    episode_time_s: int = 30,
    reset_time_s: int = 10,
    fps: int = 30,
    push_to_hub: bool = True,
) -> subprocess.CompletedProcess:
    """Record demonstration episodes using lerobot-record."""
    cameras = {
        cam_name: {
            "type": "opencv",
            "index_or_path": cam_idx,
            "width":  robot.camera_config.get(cam_name, {}).get("width",  1280),
            "height": robot.camera_config.get(cam_name, {}).get("height", 720),
            "fps":    robot.camera_config.get(cam_name, {}).get("fps",    fps),
            "fourcc": robot.camera_config.get(cam_name, {}).get("fourcc", "MJPG"),
        }
        for cam_name, cam_idx in robot.cameras.items()
    }

    cmd = [
        "lerobot-record",
        f"--robot.type=so101_follower",
        f"--robot.port={robot.follower_port}",
        f"--robot.id={robot.name}_follower",
        f"--robot.cameras={json.dumps(cameras)}",
        f"--teleop.type=so101_leader",
        f"--teleop.port={robot.leader_port}",
        f"--teleop.id={robot.name}_leader",
        f"--dataset.repo_id={repo_id}",
        f"--dataset.num_episodes={num_episodes}",
        f"--dataset.single_task={task}",
        f"--dataset.episode_time_s={episode_time_s}",
        f"--dataset.reset_time_s={reset_time_s}",
        f"--dataset.fps={fps}",
        f"--dataset.push_to_hub={'true' if push_to_hub else 'false'}",
        "--play_sounds=false",
    ]
    if calibration_dir:
        cmd.append(f"--robot.calibration_dir={calibration_dir}")
        cmd.append(f"--teleop.calibration_dir={calibration_dir}")
    if dataset_root:
        # lerobot root = full dataset path, not parent dir
        cmd.append(f"--dataset.root={dataset_root}/{repo_id}")

    print(f"Recording {num_episodes} episodes → {repo_id}")
    print()
    print("=" * 50)
    print("WAIT: Ignore the config dump below.")
    print("Watch for:  'Recording episode 0'")
    print("THAT is when you start moving the leader arm.")
    print("=" * 50)
    return subprocess.run(cmd, check=True)


def run_policy(
    robot: Robot,
    checkpoint_dir: Path,
    repo_id: str,
    task: str,
    num_episodes: int = 5,
    fps: int = 30,
) -> subprocess.CompletedProcess:
    """Run a trained policy on a robot station."""
    cameras = {
        "webcam": {
            "type": "opencv",
            "index_or_path": robot.camera_index,
            "width": 640,
            "height": 480,
            "fps": fps,
        }
    }

    cmd = [
        "lerobot-record",
        f"--robot.type=so101_follower",
        f"--robot.port={robot.follower_port}",
        f"--robot.id={robot.name}_follower",
        f"--robot.cameras={json.dumps(cameras)}",
        f"--policy.path={checkpoint_dir}",
        f"--dataset.repo_id={repo_id}",
        f"--dataset.single_task={task}",
        f"--dataset.num_episodes={num_episodes}",
        f"--dataset.push_to_hub=false",
    ]

    print(f"Running policy from {checkpoint_dir} on robot '{robot.name}'")
    return subprocess.run(cmd, check=True)
