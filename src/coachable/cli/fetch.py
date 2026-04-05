"""coachable fetch — pull a trained checkpoint from HuggingFace Hub."""

from pathlib import Path

from coachable.hub import download


def register(subparsers) -> None:
    p = subparsers.add_parser("fetch", help="Pull a trained checkpoint from HuggingFace Hub")
    p.add_argument("--repo", required=True, help="HF repo ID (e.g. rianders/act-alice-pick_block)")
    p.add_argument(
        "--dir",
        default="/app/checkpoints/latest",
        dest="local_dir",
        help="Local directory to save checkpoint (default: /app/checkpoints/latest)",
    )
    p.set_defaults(func=run)


def run(args) -> None:
    local_dir = Path(args.local_dir)
    download(repo_id=args.repo, local_dir=local_dir, repo_type="model")
    print(f"\nCheckpoint ready at {local_dir}")
    print(f"Run with: coachable run --robot <name> --checkpoint {local_dir}")
