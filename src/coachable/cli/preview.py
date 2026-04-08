"""coachable preview — live camera feed via Gradio."""

from pathlib import Path


def register(subparsers) -> None:
    p = subparsers.add_parser("preview", help="Live camera preview via Gradio")
    p.add_argument("--robot", help="Robot name — look up cameras from fleet config")
    p.add_argument("--camera", type=int, help="Single camera index override (default: from fleet)")
    p.add_argument("--port", type=int, default=7860, help="Gradio server port (default: 7860)")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument(
        "--calibration-dir",
        default="/app/calibration",
        dest="calibration_dir",
        help="Directory containing calibration JSON files (default: /app/calibration)",
    )
    p.set_defaults(func=run)


def run(args) -> None:
    calibration_dir = Path(args.calibration_dir) if args.calibration_dir else None

    # Resolve cameras
    if args.camera is not None:
        # Direct single-camera override
        cameras = {"camera": args.camera}
        robot = None
    elif args.robot:
        from coachable.fleet import load_fleet, get_robot
        fleet = load_fleet(Path(args.fleet))
        robot = get_robot(fleet, args.robot)
        cameras = robot.cameras
        print(f"Robot '{robot.name}' → cameras {cameras}")
    else:
        cameras = {"camera": 0}
        robot = None

    from coachable.camera_preview import launch
    launch(
        cameras=cameras,
        port=args.port,
        width=args.width,
        height=args.height,
        fps=args.fps,
        calibration_dir=calibration_dir,
        robot=robot,
    )
