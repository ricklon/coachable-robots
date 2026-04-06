"""coachable collect — record demonstration episodes."""

import subprocess
from pathlib import Path

from coachable.fleet import load_fleet, get_robot, dataset_repo_id
from coachable.lerobot_cli import record


def _check_camera_free(camera_index: int) -> None:
    """Warn if /dev/videoN is held by another process."""
    device = f"/dev/video{camera_index}"
    try:
        result = subprocess.run(
            ["fuser", device], capture_output=True, text=True
        )
        pids = result.stdout.strip()
        if pids:
            print(f"WARNING: {device} is in use by PID(s): {pids}")
            print("  Stop the conflicting process (e.g. camera preview container) before collecting.")
            raise SystemExit(1)
    except FileNotFoundError:
        pass  # fuser not available, skip check


def register(subparsers) -> None:
    p = subparsers.add_parser("collect", help="Record demonstration episodes")
    p.add_argument("--robot", required=True, help="Robot name (e.g. alpha)")
    p.add_argument("--dataset", required=True, help="Dataset task slug (e.g. pick_block)")
    p.add_argument("--episodes", type=int, default=20, help="Number of episodes (default: 20)")
    p.add_argument(
        "--task",
        default="Pick up the object and place it in the target location",
        help="Natural language task description",
    )
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--episode-time", type=int, default=30, dest="episode_time_s")
    p.add_argument("--reset-time", type=int, default=10, dest="reset_time_s")
    p.add_argument("--no-push", action="store_true", help="Don't push to HuggingFace Hub")
    p.add_argument(
        "--calibration-dir",
        default="/app/calibration",
        dest="calibration_dir",
        help="Calibration directory (default: /app/calibration)",
    )
    p.add_argument(
        "--dataset-root",
        default="/app/data",
        dest="dataset_root",
        help="Local dataset root (default: /app/data)",
    )
    p.set_defaults(func=run)


def run(args) -> None:
    fleet = load_fleet(Path(args.fleet))
    robot = get_robot(fleet, args.robot)
    repo_id = dataset_repo_id(fleet, robot, args.dataset)

    _check_camera_free(robot.camera_index)

    episode_s = args.episode_time_s
    reset_s = args.reset_time_s
    total_s = args.episodes * (episode_s + reset_s) - reset_s

    print(f"Coach:    {robot.coach or 'unassigned'}")
    print(f"Robot:    {robot.name} ({robot.type})")
    print(f"Dataset:  {repo_id}")
    print(f"Episodes: {args.episodes}  x  {episode_s}s record + {reset_s}s reset")
    print(f"Total:    ~{total_s}s ({total_s // 60}m {total_s % 60}s)")
    print(f"Task:     {args.task}")
    print()
    print("Episode timing (headless mode — no keyboard/audio cues):")
    for i in range(args.episodes):
        start = i * (episode_s + reset_s)
        end = start + episode_s
        print(f"  Episode {i}: RECORD {start}s–{end}s  →  RESET {end}s–{end + reset_s}s (return arm to start)")
    print()

    record(
        robot=robot,
        repo_id=repo_id,
        num_episodes=args.episodes,
        task=args.task,
        calibration_dir=Path(args.calibration_dir),
        dataset_root=Path(args.dataset_root),
        episode_time_s=args.episode_time_s,
        reset_time_s=args.reset_time_s,
        fps=args.fps,
        push_to_hub=not args.no_push,
    )

    if not args.no_push:
        print(f"\nDataset at: https://huggingface.co/datasets/{repo_id}")
