"""
camera_preview.py — Live dual-camera preview with system status, calibration
panel, and arm control via Gradio.

Runs on the Pi container at 0.0.0.0:7860.  Notebook launches it via
container.execute() and shows the URL — no Gradio code in the notebook.

CLI usage:
  coachable preview --robot alpha
  coachable preview --camera 0

Programmatic usage (tests / notebook exec_python):
  from coachable.camera_preview import launch
  launch(cameras={"top": 0, "gripper": 2}, robot=robot_obj)
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

import cv2
import gradio as gr
import numpy as np


# ---------------------------------------------------------------------------
# Calibration step-by-step instructions
# ---------------------------------------------------------------------------

_CALIBRATION_INSTRUCTIONS = {
    "follower": """\
### Follower arm calibration (so101_follower)

The follower arm receives commands — calibrate it first.

1. Connect the follower arm to its serial port and power it on.
2. Move the arm to a relaxed middle position by hand.
3. Run: `coachable calibrate --robot {name} --calibration-dir /app/calibration`
4. When prompted, rotate each joint slowly through its full range.
5. Calibration file saved as `{name}_follower.json`.

> **Tip:** If motor ID 6 (gripper) is missing, check the gripper servo cable.
""",
    "leader": """\
### Leader arm calibration (so101_leader)

The leader arm is the one you hold — calibrate it after the follower.

1. Connect the leader arm and power it on.
2. Hold loosely — do not apply force.
3. Calibration runs as the second stage of `coachable calibrate`.
4. When prompted, move each joint through its full range.
5. Calibration file saved as `{name}_leader.json`.

> **Tip:** The arm whose motors lock on connect is the follower.
""",
}


# ---------------------------------------------------------------------------
# Camera helpers
# ---------------------------------------------------------------------------

def _open_camera(
    index: int, width: int, height: int, fps: int, fourcc: str = "MJPG",
    retries: int = 3, retry_delay: float = 1.0,
) -> tuple[cv2.VideoCapture | None, int, int, float, str | None]:
    """Open a V4L2 camera. Returns (cap, actual_w, actual_h, actual_fps, error).

    Retries up to `retries` times with `retry_delay` seconds between attempts.
    Needed in container environments where V4L2 devices may not be fully
    initialised at process start (e.g. CHI@Edge smarter-device-manager).

    Uses device path + CAP_V4L2 — integer index fails silently on Pi 5.
    Skips cap.get() after cap.set() — on FFMPEG fallback those calls block
    waiting for the first frame to determine actual resolution.
    """
    device_path = f"/dev/video{index}"
    for attempt in range(retries):
        cap = cv2.VideoCapture(device_path, cv2.CAP_V4L2)
        if cap.isOpened():
            # Set fourcc before resolution (some drivers require this order)
            fourcc_code = cv2.VideoWriter_fourcc(*fourcc)
            cap.set(cv2.CAP_PROP_FOURCC, fourcc_code)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            cap.set(cv2.CAP_PROP_FPS, fps)
            return cap, width, height, float(fps), None
        cap.release()
        if attempt < retries - 1:
            print(f"  camera /dev/video{index}: not ready, retrying in {retry_delay}s "
                  f"({attempt + 1}/{retries - 1})...")
            time.sleep(retry_delay)
    return None, width, height, float(fps), f"Cannot open /dev/video{index}"


def _placeholder_frame(width: int, height: int, label: str, error: str) -> np.ndarray:
    frame = np.full((height, width, 3), 40, dtype=np.uint8)
    cv2.putText(frame, label, (20, height // 2 - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (180, 180, 180), 2)
    cv2.putText(frame, error, (20, height // 2 + 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (120, 120, 120), 1)
    return frame


def _make_capture_fn(
    cap: cv2.VideoCapture | None,
    width: int,
    height: int,
    label: str,
    error: str | None,
    pre_configure: str | None = None,
):
    """Return a no-arg callable that grabs one RGB frame (for gr.Timer)."""
    placeholder = _placeholder_frame(width, height, label, error or "unavailable")
    _configured = [False]

    def grab() -> np.ndarray:
        if cap is None:
            return placeholder
        # Run v4l2 pre-configuration once on first grab
        if pre_configure and not _configured[0]:
            subprocess.run(pre_configure, shell=True, capture_output=True)
            _configured[0] = True
        ret, frame = cap.read()
        if ret:
            return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return placeholder

    return grab


# ---------------------------------------------------------------------------
# Calibration helpers
# ---------------------------------------------------------------------------

def _read_calibration(
    calibration_dir: Path | None, robot_name: str | None, arm: str
) -> tuple[str, str]:
    """Returns (status_text, json_text)."""
    if calibration_dir is None or robot_name is None:
        return "Unknown", ""
    path = calibration_dir / f"{robot_name}_{arm}.json"
    if not path.exists():
        return "Not calibrated", ""
    try:
        data = json.loads(path.read_text())
        mtime = path.stat().st_mtime
        date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        return f"Calibrated ({date_str})", json.dumps(data, indent=2)
    except Exception as exc:
        return f"Error reading file: {exc}", ""


# ---------------------------------------------------------------------------
# System status helpers
# ---------------------------------------------------------------------------

def _system_status(robot=None) -> tuple[str, str, str]:
    """Returns (serial_text, video_text, info_text)."""
    try:
        dev_files = sorted(os.listdir("/dev"))
    except Exception:
        dev_files = []

    # Serial ports
    acm = [f"/dev/{f}" for f in dev_files if f.startswith("ttyACM")]
    serial_text = "\n".join(acm) if acm else "None found — check USB connections"

    # Video devices (even=capture, odd=UVC metadata)
    videos = [f for f in dev_files if f.startswith("video")]
    video_lines = []
    for v in videos:
        try:
            idx = int(v.replace("video", ""))
            node_type = "capture" if idx % 2 == 0 else "metadata (UVC)"
        except ValueError:
            node_type = "unknown"
        video_lines.append(f"/dev/{v}  ({node_type})")
    video_text = "\n".join(video_lines) if video_lines else "None found"

    # Software info
    try:
        r = subprocess.run(
            ["python3", "-c", "import lerobot; print(lerobot.__version__)"],
            capture_output=True, text=True, timeout=5,
        )
        lerobot_ver = r.stdout.strip() or "not found"
    except Exception:
        lerobot_ver = "not found"

    lines = [f"LeRobot : {lerobot_ver}"]
    if robot:
        lines += [
            f"Robot   : {robot.name} ({robot.type})",
            f"Coach   : {robot.coach or 'unassigned'}",
            f"Follower: {robot.follower_port}",
            f"Leader  : {robot.leader_port}",
            f"Cameras : {robot.cameras}",
        ]
    info_text = "\n".join(lines)

    return serial_text, video_text, info_text


# ---------------------------------------------------------------------------
# Arm control helpers
# ---------------------------------------------------------------------------

def _check_arm_connection(robot, calibration_dir: Path | None) -> str:
    """Check port presence, calibration files, and serial accessibility."""
    lines = []

    # Port presence
    for label, port in [("Follower", robot.follower_port), ("Leader", robot.leader_port)]:
        present = os.path.exists(port)
        icon = "✅" if present else "❌"
        lines.append(f"{icon} {label}: {port} {'(present)' if present else '(NOT FOUND)'}")

    lines.append("")

    # Calibration files
    calib_dir = calibration_dir or Path("/app/calibration")
    for arm in ("follower", "leader"):
        cf = calib_dir / f"{robot.name}_{arm}.json"
        if cf.exists():
            mtime = datetime.fromtimestamp(cf.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            lines.append(f"✅ Calibration ({arm}): {cf.name}  [{mtime}]")
        else:
            lines.append(f"❌ Calibration ({arm}): missing — run coachable calibrate")

    lines.append("")

    # Quick serial open test (no lerobot needed — just pyserial)
    script = (
        "import serial, sys\n"
        f"ports = ['{robot.follower_port}', '{robot.leader_port}']\n"
        "for p in ports:\n"
        "    try:\n"
        "        ser = serial.Serial(p, baudrate=1000000, timeout=0.5)\n"
        "        ser.close()\n"
        "        print(f'Serial OK: {p}')\n"
        "    except Exception as e:\n"
        "        print(f'Serial ERROR: {p} — {e}')\n"
    )
    try:
        r = subprocess.run(
            ["python3", "-c", script],
            capture_output=True, text=True, timeout=10,
        )
        if r.stdout.strip():
            lines.extend(r.stdout.strip().split("\n"))
        if r.stderr.strip():
            lines.append(f"stderr: {r.stderr.strip()[:300]}")
    except subprocess.TimeoutExpired:
        lines.append("Serial check: timeout")
    except Exception as e:
        lines.append(f"Serial check error: {e}")

    return "\n".join(lines)


def _teleop_command(robot) -> str:
    return (
        f"lerobot-teleoperate \\\n"
        f"  --robot.type=so101_follower \\\n"
        f"  --robot.port={robot.follower_port} \\\n"
        f"  --robot.id={robot.name}_follower \\\n"
        f"  --teleop.type=so101_leader \\\n"
        f"  --teleop.port={robot.leader_port} \\\n"
        f"  --teleop.id={robot.name}_leader \\\n"
        f"  --display_cameras=false"
    )


def _calibrate_command(robot, calibration_dir: Path | None) -> str:
    calib = str(calibration_dir or "/app/calibration")
    return (
        f"# Calibrate follower first, then leader:\n"
        f"lerobot-calibrate \\\n"
        f"  --robot.type=so101_follower \\\n"
        f"  --robot.port={robot.follower_port} \\\n"
        f"  --robot.id={robot.name}_follower \\\n"
        f"  --robot.calibration_dir={calib}\n\n"
        f"lerobot-calibrate \\\n"
        f"  --teleop.type=so101_leader \\\n"
        f"  --teleop.port={robot.leader_port} \\\n"
        f"  --teleop.id={robot.name}_leader \\\n"
        f"  --teleop.calibration_dir={calib}"
    )


# ---------------------------------------------------------------------------
# Main launch function
# ---------------------------------------------------------------------------

PORT_FILE = "/tmp/preview.port"
PID_FILE  = "/tmp/preview.pid"


def _find_free_port(start: int = 7860, end: int = 7870) -> int:
    """Return the first free TCP port in [start, end], or start if all busy."""
    import socket
    for p in range(start, end + 1):
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("", p))
            s.close()
            return p
        except OSError:
            s.close()
    return start  # fall through and let Gradio error with a clear message


def launch(
    cameras: dict[str, int] | None = None,
    camera_index: int = 0,          # backwards-compat
    camera_config: dict[str, dict] | None = None,  # per-camera fourcc/width/height
    port: int = 7860,
    width: int = 1280,
    height: int = 720,
    fps: int = 30,
    calibration_dir: Path | None = None,
    robot=None,
) -> None:
    # Write our PID so the notebook can kill us reliably
    Path(PID_FILE).write_text(str(os.getpid()))
    # Find a free port and advertise it
    port = _find_free_port(port, port + 10)
    Path(PORT_FILE).write_text(str(port))
    print(f"Preview binding on port {port}")
    if cameras is None:
        cameras = {"camera": camera_index}

    robot_name = robot.name if robot else None
    cam_cfg = camera_config or (robot.camera_config if robot else {})

    # Open all cameras
    cam_info: dict[str, tuple] = {}
    for cam_name, cam_idx in cameras.items():
        cfg = cam_cfg.get(cam_name, {})
        w       = cfg.get("width",  width)
        h       = cfg.get("height", height)
        f       = cfg.get("fps",    fps)
        fourcc  = cfg.get("fourcc", "MJPG")

        # OV2710: disable dynamic framerate before opening
        pre = None
        if cam_name == "gripper" or fourcc == "MJPG":
            pre = (
                f"v4l2-ctl --device=/dev/video{cam_idx} "
                "--set-ctrl=exposure_dynamic_framerate=0 "
                "--set-ctrl=backlight_compensation=2 2>/dev/null"
            )

        cap, aw, ah, afps, err = _open_camera(cam_idx, w, h, f, fourcc)
        cam_info[cam_name] = (cap, aw, ah, afps, err, pre)
        if err:
            print(f"Warning: {err}")
        else:
            print(f"Camera '{cam_name}' (video{cam_idx}): {aw}x{ah} @ {afps:.0f}fps {fourcc}")

    # Read calibration
    follower_status, follower_json = _read_calibration(calibration_dir, robot_name, "follower")
    leader_status,   leader_json   = _read_calibration(calibration_dir, robot_name, "leader")

    # ── Build Gradio UI ───────────────────────────────────────────────────────
    with gr.Blocks(title="Coachable — Robot Preview") as demo:
        gr.Markdown("## Coachable Robot Preview")
        if robot_name:
            gr.Markdown(
                f"Robot: **{robot_name}** &nbsp;|&nbsp; "
                f"Leader: `{robot.leader_port}` &nbsp;|&nbsp; "
                f"Follower: `{robot.follower_port}` &nbsp;|&nbsp; "
                f"Coach: **{robot.coach or 'unassigned'}**"
            )

        # ── Camera feeds ─────────────────────────────────────────────────────
        gr.Markdown("### Live Camera Feeds")
        image_widgets: dict[str, gr.Image] = {}
        with gr.Row():
            for cam_name, (cap, w, h, afps, err, _pre) in cam_info.items():
                cam_idx = cameras[cam_name]
                with gr.Column():
                    status_md = (
                        f"`/dev/video{cam_idx}` — {w}×{h} @ {afps:.0f}fps"
                        if not err else f"⚠ {err}"
                    )
                    gr.Markdown(f"**{cam_name}** &nbsp; {status_md}")
                    img = gr.Image(label=cam_name, streaming=False)
                    image_widgets[cam_name] = img

        # ── System status ────────────────────────────────────────────────────
        with gr.Accordion("System Status", open=True):
            with gr.Row():
                serial_out = gr.Textbox(label="Serial ports (/dev/ttyACM*)",
                                        interactive=False, lines=4)
                video_out  = gr.Textbox(label="Video devices (/dev/video*)",
                                        interactive=False, lines=4)
                info_out   = gr.Textbox(label="Software & Robot Config",
                                        interactive=False, lines=4)
            refresh_sys_btn = gr.Button("Refresh System Status", size="sm")

            def _refresh_status():
                return _system_status(robot)

            refresh_sys_btn.click(fn=_refresh_status,
                                  outputs=[serial_out, video_out, info_out])

        # ── Arm control ───────────────────────────────────────────────────────
        if robot:
            with gr.Accordion("Arm Control & Verification", open=True):
                gr.Markdown(
                    "**Check Connection** verifies port presence, calibration files, "
                    "and serial accessibility. "
                    "**Teleop** and **Calibrate** commands are run over SSH."
                )
                with gr.Row():
                    arm_status_box = gr.Textbox(
                        label="Arm Status", interactive=False, lines=10, scale=2
                    )
                    with gr.Column(scale=1):
                        check_arm_btn = gr.Button("Check Arm Connection",
                                                  variant="secondary", size="sm")
                        gr.Markdown("**Teleoperate** (SSH):")
                        gr.Code(value=_teleop_command(robot), language="shell",
                                label="")
                        gr.Markdown("**Calibrate** (SSH):")
                        gr.Code(
                            value=_calibrate_command(robot, calibration_dir),
                            language="shell", label="",
                        )

                def _do_arm_check():
                    return _check_arm_connection(robot, calibration_dir)

                check_arm_btn.click(fn=_do_arm_check, outputs=arm_status_box)

        # ── Calibration panel ────────────────────────────────────────────────
        with gr.Accordion("Calibration Files", open=False):
            if not (follower_json or leader_json):
                gr.Markdown(
                    "_No calibration files found. Run `coachable calibrate "
                    f"--robot {robot_name or 'alpha'} --calibration-dir /app/calibration`_"
                )
            with gr.Row():
                for arm, status, json_text in [
                    ("follower", follower_status, follower_json),
                    ("leader",   leader_status,   leader_json),
                ]:
                    port_str = (
                        (robot.follower_port if arm == "follower" else robot.leader_port)
                        if robot else "?"
                    )
                    icon = "✅" if json_text else "❌"
                    with gr.Column():
                        gr.Markdown(
                            f"### {arm.capitalize()} arm\n"
                            f"Port: `{port_str}`  \nStatus: {icon} **{status}**"
                        )
                        if json_text:
                            gr.Code(
                                value=json_text, language="json",
                                label=f"{robot_name or 'robot'}_{arm}.json",
                            )
                        elif calibration_dir:
                            gr.Markdown(
                                f"_No file at `{calibration_dir}/{robot_name or 'robot'}_{arm}.json`_"
                            )
                        with gr.Accordion(f"How to calibrate the {arm} arm", open=False):
                            gr.Markdown(
                                _CALIBRATION_INSTRUCTIONS[arm].format(
                                    name=robot_name or "alpha", port=port_str
                                )
                            )

        # ── Timer: camera + auto-load system status ───────────────────────────
        timer = gr.Timer(value=1.0 / fps)
        for cam_name, img_widget in image_widgets.items():
            cap, w, h, _afps, err, pre = cam_info[cam_name]
            timer.tick(
                fn=_make_capture_fn(cap, w, h, cam_name, err, pre),
                outputs=img_widget,
            )

        # Auto-load system status and arm check on page open
        demo.load(fn=_refresh_status, outputs=[serial_out, video_out, info_out])
        if robot:
            demo.load(fn=_do_arm_check, outputs=arm_status_box)

    demo.queue()
    demo.launch(
        server_name="0.0.0.0",
        server_port=port,
        share=False,
        theme=gr.themes.Base(),
    )
