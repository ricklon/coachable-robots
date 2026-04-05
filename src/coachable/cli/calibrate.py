"""coachable calibrate — calibrate a robot's arms."""

from pathlib import Path

from coachable.fleet import load_fleet, get_robot
from coachable.lerobot_cli import calibrate as _calibrate


def register(subparsers) -> None:
    p = subparsers.add_parser("calibrate", help="Calibrate a robot's follower and leader arms")
    p.add_argument("--robot", required=True, help="Robot name (e.g. alpha)")
    p.add_argument(
        "--calibration-dir",
        default="/app/calibration",
        dest="calibration_dir",
        help="Directory to save calibration files (default: /app/calibration)",
    )
    p.set_defaults(func=run)


def run(args) -> None:
    fleet = load_fleet(Path(args.fleet))
    robot = get_robot(fleet, args.robot)

    if robot.status == "offline":
        print(f"Warning: robot '{robot.name}' is marked offline in fleet config.")

    calibration_dir = Path(args.calibration_dir)
    calibration_dir.mkdir(parents=True, exist_ok=True)

    print(f"Calibrating robot '{robot.name}' ({robot.type})")
    print(f"  Follower: {robot.follower_port}")
    print(f"  Leader:   {robot.leader_port}")
    print(f"  Saving to: {calibration_dir}")
    print()
    print("Calibrate FOLLOWER first, then LEADER (per lerobot docs).")
    print()

    _calibrate(robot, calibration_dir=calibration_dir)
    print(f"\nCalibration complete. Files saved to {calibration_dir}")
