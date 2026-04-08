"""
camera_preview.py — Live dual-camera preview with calibration panel via Gradio.

Can be launched via CLI:
  coachable preview --robot alpha
  coachable preview --camera 0

Or called directly from a notebook:
  from coachable.camera_preview import launch
  launch(cameras={"top": 0, "gripper": 1})
  launch(camera_index=0)  # backwards-compat
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Generator

import cv2
import gradio as gr
import numpy as np


# ---------------------------------------------------------------------------
# Calibration step-by-step instructions
# ---------------------------------------------------------------------------

_CALIBRATION_INSTRUCTIONS = {
    "follower": """\
### Follower arm calibration (so101_follower)

The follower arm receives commands — it must be calibrated first.

1. **Connect** the follower arm to its serial port and power it on.
2. **Rest position** — move the arm to a relaxed middle position by hand.
3. **Run calibration:**
   ```
   coachable calibrate --robot alpha --calibration-dir /mnt/data/calibration
   ```
4. When prompted, **rotate each joint** slowly through its full range of motion.
5. The calibration file is saved as `alpha_follower.json`.

> **Tip:** If motor ID 6 (gripper) is missing, check the gripper servo cable — it
> can pull loose during wrist rotation. Reseat it before re-running calibration.
""",
    "leader": """\
### Leader arm calibration (so101_leader)

The leader arm is the one you hold and move — calibrate it after the follower.

1. **Connect** the leader arm to its serial port and power it on.
2. **Hold loosely** — do not apply force; let it move freely.
3. Calibration runs automatically as the second stage of `coachable calibrate`.
4. When prompted, **move each joint** through its full range.
5. The calibration file is saved as `alpha_leader.json`.

> **Tip:** The arm whose motors lock up on connect is the follower. The arm
> that stays loose is the leader. Verify with `lerobot-teleoperate` if unsure.
""",
}


# ---------------------------------------------------------------------------
# Camera helpers
# ---------------------------------------------------------------------------

def _open_camera(
    index: int, width: int, height: int, fps: int
) -> tuple[cv2.VideoCapture | None, int, int, float, str | None]:
    """Open a camera. Returns (cap, actual_w, actual_h, actual_fps, error_msg)."""
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        return None, width, height, float(fps), f"Cannot open /dev/video{index}"
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    actual_fps = cap.get(cv2.CAP_PROP_FPS) or fps
    return cap, actual_w, actual_h, actual_fps, None


def _placeholder_frame(width: int, height: int, label: str, error: str) -> np.ndarray:
    """Return a grey placeholder frame with error text."""
    frame = np.full((height, width, 3), 40, dtype=np.uint8)
    cv2.putText(frame, label, (20, height // 2 - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (180, 180, 180), 2)
    cv2.putText(frame, error, (20, height // 2 + 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (120, 120, 120), 1)
    return frame


def _make_stream(
    cap: cv2.VideoCapture | None,
    width: int,
    height: int,
    fps: int,
    label: str,
    error: str | None,
) -> Generator[np.ndarray, None, None]:
    """Infinite generator yielding RGB frames for one camera."""
    delay = 1.0 / max(fps, 1)
    if cap is None:
        placeholder = _placeholder_frame(width, height, label, error or "unavailable")
        while True:
            yield placeholder
            time.sleep(delay)
    else:
        placeholder = _placeholder_frame(width, height, label, "No frame")
        while True:
            ret, frame = cap.read()
            if ret:
                yield cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            else:
                yield placeholder
            time.sleep(delay)


# ---------------------------------------------------------------------------
# Calibration helpers
# ---------------------------------------------------------------------------

def _read_calibration(
    calibration_dir: Path | None, robot_name: str | None, arm: str
) -> tuple[str, str]:
    """
    Read calibration JSON for one arm.
    Returns (status_text, json_text).
    """
    if calibration_dir is None or robot_name is None:
        return "Unknown", ""

    path = calibration_dir / f"{robot_name}_{arm}.json"
    if not path.exists():
        return "Not calibrated", ""

    try:
        data = json.loads(path.read_text())
        mtime = path.stat().st_mtime
        date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        json_text = json.dumps(data, indent=2)
        return f"Calibrated ({date_str})", json_text
    except Exception as exc:
        return f"Error reading file: {exc}", ""


# ---------------------------------------------------------------------------
# Main launch function
# ---------------------------------------------------------------------------

def launch(
    cameras: dict[str, int] | None = None,
    camera_index: int = 0,          # backwards-compat for notebook callers
    port: int = 7860,
    width: int = 1280,
    height: int = 720,
    fps: int = 30,
    calibration_dir: Path | None = None,
    robot=None,                      # Robot dataclass instance, optional
) -> None:
    # Normalise cameras arg
    if cameras is None:
        cameras = {"camera": camera_index}

    robot_name = robot.name if robot else None

    # Open all cameras up front so we can report actual resolutions
    cam_info: dict[str, tuple] = {}  # name → (cap, w, h, actual_fps, error)
    for cam_name, cam_idx in cameras.items():
        cap, w, h, actual_fps, err = _open_camera(cam_idx, width, height, fps)
        cam_info[cam_name] = (cap, w, h, actual_fps, err)
        if err:
            print(f"Warning: {err}")
        else:
            print(f"Camera '{cam_name}' (video{cam_idx}): {w}x{h} @ {actual_fps:.0f}fps")

    # Read calibration status
    follower_status, follower_json = _read_calibration(calibration_dir, robot_name, "follower")
    leader_status, leader_json = _read_calibration(calibration_dir, robot_name, "leader")

    # Build Gradio UI
    with gr.Blocks(title="Coachable — Camera Preview") as demo:
        gr.Markdown("## Coachable Robot Camera Preview")
        if robot_name:
            leader_port = robot.leader_port if robot else "?"
            follower_port = robot.follower_port if robot else "?"
            gr.Markdown(
                f"Robot: **{robot_name}** &nbsp;|&nbsp; "
                f"Leader: `{leader_port}` &nbsp;|&nbsp; "
                f"Follower: `{follower_port}`"
            )

        # Camera feeds
        image_widgets: dict[str, gr.Image] = {}
        with gr.Row():
            for cam_name, (cap, w, h, actual_fps, err) in cam_info.items():
                cam_idx = cameras[cam_name]
                with gr.Column():
                    status_md = (
                        f"`/dev/video{cam_idx}` — {w}×{h} @ {actual_fps:.0f}fps"
                        if not err else f"⚠ {err}"
                    )
                    gr.Markdown(f"**{cam_name}** &nbsp; {status_md}")
                    img = gr.Image(label=cam_name, streaming=False)
                    image_widgets[cam_name] = img

        # Calibration panel
        with gr.Accordion("Calibration", open=True):
            gr.Markdown(
                "_Run `coachable calibrate --robot " +
                (robot_name or "alpha") +
                " --calibration-dir /mnt/data/calibration` to calibrate._"
                if not (follower_json or leader_json) else ""
            )
            with gr.Row():
                for arm, status, json_text in [
                    ("follower", follower_status, follower_json),
                    ("leader", leader_status, leader_json),
                ]:
                    port_str = (
                        (robot.follower_port if arm == "follower" else robot.leader_port)
                        if robot else "?"
                    )
                    status_icon = "✅" if json_text else "❌"
                    with gr.Column():
                        gr.Markdown(f"### {arm.capitalize()} arm")
                        gr.Markdown(f"Port: `{port_str}`  \nStatus: {status_icon} **{status}**")
                        if calibration_dir is None:
                            gr.Markdown(
                                "_No calibration directory specified. "
                                "Use `--calibration-dir` to load calibration data._"
                            )
                        elif json_text:
                            gr.Code(
                                value=json_text,
                                language="json",
                                label=f"{robot_name or 'robot'}_{arm}.json",
                            )
                        else:
                            gr.Markdown(
                                f"_No calibration file found at "
                                f"`{calibration_dir}/{robot_name or 'robot'}_{arm}.json`_"
                            )
                        with gr.Accordion(f"How to calibrate the {arm} arm", open=False):
                            gr.Markdown(
                                _CALIBRATION_INSTRUCTIONS[arm].format(
                                    name=robot_name or "alpha",
                                    port=port_str,
                                )
                            )

        # Wire up streaming generators (one demo.load per camera)
        # demo.load requires a callable, so wrap each generator in a closure
        for cam_name, img_widget in image_widgets.items():
            cap, w, h, actual_fps, err = cam_info[cam_name]

            def _make_fn(c, _w, _h, _fps, _label, _err):
                def stream_fn():
                    yield from _make_stream(c, _w, _h, _fps, _label, _err)
                return stream_fn

            demo.load(fn=_make_fn(cap, w, h, fps, cam_name, err), outputs=img_widget)

    demo.queue()
    demo.launch(server_name="0.0.0.0", server_port=port, share=False, theme=gr.themes.Base())
