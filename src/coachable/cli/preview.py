"""coachable preview — live camera feed via Gradio."""

from pathlib import Path


def register(subparsers) -> None:
    p = subparsers.add_parser("preview", help="Live camera preview via Gradio")
    p.add_argument("--robot", help="Robot name — look up camera index from fleet config")
    p.add_argument("--camera", type=int, help="Camera index override (default: from fleet)")
    p.add_argument("--port", type=int, default=7860, help="Gradio server port (default: 7860)")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    p.add_argument("--fps", type=int, default=30)
    p.set_defaults(func=run)


def run(args) -> None:
    # Resolve camera index from fleet or direct arg
    camera_index = args.camera
    if camera_index is None:
        if args.robot:
            from coachable.fleet import load_fleet, get_robot
            fleet = load_fleet(Path(args.fleet))
            robot = get_robot(fleet, args.robot)
            camera_index = robot.camera_index
            print(f"Robot '{robot.name}' → camera index {camera_index}")
        else:
            camera_index = 0

    # Import here so gradio is only required when preview is used
    from coachable.camera_preview import launch
    launch(
        camera_index=camera_index,
        port=args.port,
        width=args.width,
        height=args.height,
        fps=args.fps,
    )
