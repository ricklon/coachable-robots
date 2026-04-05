"""coachable fleet — show robot fleet status."""

from pathlib import Path

from coachable.fleet import load_fleet


def register(subparsers) -> None:
    p = subparsers.add_parser("fleet", help="Show fleet status")
    p.add_argument("--list", action="store_true", default=True, help="List all robots")
    p.set_defaults(func=run)


def run(args) -> None:
    fleet = load_fleet(Path(args.fleet))

    print(f"\nFleet: {fleet.name}\n")
    print(f"{'Robot':<12} {'Type':<8} {'Status':<12} {'Coach':<16} {'Dataset prefix'}")
    print("-" * 72)

    for robot in fleet.robots:
        coach_name = robot.coach or "—"
        if robot.coach:
            try:
                from coachable.fleet import get_coach
                coach = get_coach(fleet, robot.coach)
                hf_user = coach.hf_user
            except ValueError:
                hf_user = robot.coach
            prefix = f"{hf_user}/{fleet.hf.dataset_prefix}-{robot.coach}-*"
        else:
            prefix = "—"
        print(f"{robot.name:<12} {robot.type:<8} {robot.status:<12} {coach_name:<16} {prefix}")

    print()
    if fleet.coaches:
        print(f"{'Coach':<16} {'HF User':<20} {'Role'}")
        print("-" * 48)
        for coach in fleet.coaches:
            print(f"{coach.name:<16} {coach.hf_user:<20} {coach.role}")
        print()
