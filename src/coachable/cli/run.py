"""coachable run — execute a trained policy on a robot."""

from pathlib import Path

from coachable.fleet import load_fleet, get_robot, model_repo_id
from coachable.lerobot_cli import run_policy


def register(subparsers) -> None:
    p = subparsers.add_parser("run", help="Run a trained policy on a robot")
    p.add_argument("--robot", required=True, help="Robot name (e.g. alpha)")
    p.add_argument(
        "--checkpoint",
        default="/app/checkpoints/latest",
        help="Path to checkpoint directory (default: /app/checkpoints/latest)",
    )
    p.add_argument("--task", default="Pick up the object and place it in the target location")
    p.add_argument("--episodes", type=int, default=5)
    p.add_argument("--fps", type=int, default=30)
    p.set_defaults(func=_run)


def _run(args) -> None:
    fleet = load_fleet(Path(args.fleet))
    robot = get_robot(fleet, args.robot)
    checkpoint_dir = Path(args.checkpoint)

    if not checkpoint_dir.exists():
        print(f"Checkpoint not found at {checkpoint_dir}")
        print(f"Run: coachable fetch --repo <hf-repo-id>")
        raise SystemExit(1)

    # Eval results go to a repo so they can be reviewed
    eval_repo = model_repo_id(fleet, robot, "eval")

    print(f"Robot:      {robot.name} ({robot.type})")
    print(f"Coach:      {robot.coach or 'unassigned'}")
    print(f"Checkpoint: {checkpoint_dir}")
    print(f"Task:       {args.task}")
    print()

    run_policy(
        robot=robot,
        checkpoint_dir=checkpoint_dir,
        repo_id=eval_repo,
        task=args.task,
        num_episodes=args.episodes,
        fps=args.fps,
    )
