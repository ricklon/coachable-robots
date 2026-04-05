"""coachable calibrate — calibrate a robot's arms."""

from pathlib import Path

from coachable.fleet import load_fleet, get_robot
from coachable.lerobot_cli import calibrate as _calibrate


def register(subparsers) -> None:
    p = subparsers.add_parser("calibrate", help="Calibrate a robot's leader and follower arms")
    p.add_argument("--robot", required=True, help="Robot name (e.g. alpha)")
    p.set_defaults(func=run)


def run(args) -> None:
    fleet = load_fleet(Path(args.fleet))
    robot = get_robot(fleet, args.robot)

    if robot.status == "offline":
        print(f"Warning: robot '{robot.name}' is marked offline in fleet config.")

    print(f"Calibrating robot '{robot.name}' ({robot.type})")
    print(f"  Leader:   {robot.leader_port}")
    print(f"  Follower: {robot.follower_port}")
    print()

    _calibrate(robot)
    print("\nCalibration complete.")
