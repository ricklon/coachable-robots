"""
coachable CLI — dispatch to subcommands.

Usage:
  coachable fleet    --list
  coachable preview  --robot alpha
  coachable calibrate --robot alpha
  coachable collect  --robot alpha --dataset pick_block --episodes 20
  coachable fetch    --repo coachable-lab/act-alice-pick_block
  coachable run      --robot alpha --checkpoint /app/checkpoints/latest
"""

import argparse

from coachable.cli import calibrate, collect, fleet, fetch, preview, run


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="coachable",
        description="Coachable — fleet management and coaching workflow for robots",
    )
    parser.add_argument(
        "--fleet",
        default="/app/config/fleet.yaml",
        metavar="PATH",
        help="Path to fleet.yaml (default: /app/config/fleet.yaml)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    fleet.register(subparsers)
    preview.register(subparsers)
    calibrate.register(subparsers)
    collect.register(subparsers)
    fetch.register(subparsers)
    run.register(subparsers)

    args = parser.parse_args()
    args.func(args)
