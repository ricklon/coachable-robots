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


def calibrate(robot: Robot) -> subprocess.CompletedProcess:
    """Calibrate both leader and follower arms for a robot station."""
    results = []
    for arm_type, port, arm_id in [
        ("so101_leader", robot.leader_port, f"{robot.name}_leader"),
        ("so101_follower", robot.follower_port, f"{robot.name}_follower"),
    ]:
        cmd = [
            "lerobot-calibrate",
            f"--robot.type={arm_type}",
            f"--robot.port={port}",
            f"--robot.id={arm_id}",
        ]
        print(f"Calibrating {arm_type} on {port}...")
        result = subprocess.run(cmd, check=True)
        results.append(result)
    return results[-1]


def record(
    robot: Robot,
    repo_id: str,
    num_episodes: int,
    task: str,
    episode_time_s: int = 30,
    reset_time_s: int = 10,
    fps: int = 30,
    push_to_hub: bool = True,
) -> subprocess.CompletedProcess:
    """Record demonstration episodes using lerobot-record."""
    cameras = {
        "webcam": {
            "type": "opencv",
            "index_or_path": robot.camera_index,
            "width": 1280,
            "height": 720,
            "fps": fps,
        }
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
    ]

    print(f"Recording {num_episodes} episodes → {repo_id}")
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
