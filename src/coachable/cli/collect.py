"""coachable collect — record demonstration episodes."""

from pathlib import Path

from coachable.fleet import load_fleet, get_robot, dataset_repo_id
from coachable.lerobot_cli import record


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
    p.set_defaults(func=run)


def run(args) -> None:
    fleet = load_fleet(Path(args.fleet))
    robot = get_robot(fleet, args.robot)
    repo_id = dataset_repo_id(fleet, robot, args.dataset)

    print(f"Coach:    {robot.coach or 'unassigned'}")
    print(f"Robot:    {robot.name} ({robot.type})")
    print(f"Dataset:  {repo_id}")
    print(f"Episodes: {args.episodes}")
    print(f"Task:     {args.task}")
    print()

    record(
        robot=robot,
        repo_id=repo_id,
        num_episodes=args.episodes,
        task=args.task,
        episode_time_s=args.episode_time_s,
        reset_time_s=args.reset_time_s,
        fps=args.fps,
        push_to_hub=not args.no_push,
    )

    if not args.no_push:
        print(f"\nDataset at: https://huggingface.co/datasets/{repo_id}")
