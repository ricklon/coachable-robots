"""
camera_preview.py — Live camera preview via Gradio.

Can be launched via CLI:
  coachable preview --robot alpha
  coachable preview --camera 0

Or called directly from a notebook:
  from coachable.camera_preview import launch
  launch(camera_index=0)
"""

from __future__ import annotations

import time

import cv2
import gradio as gr
import numpy as np


def launch(
    camera_index: int = 0,
    port: int = 7860,
    width: int = 1280,
    height: int = 720,
    fps: int = 30,
) -> None:
    cap = cv2.VideoCapture(camera_index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)

    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera {camera_index}")

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    actual_fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"Camera {camera_index}: {actual_w}x{actual_h} @ {actual_fps:.0f}fps")

    def stream_frames():
        while True:
            ret, frame = cap.read()
            if not ret:
                yield np.zeros((actual_h, actual_w, 3), dtype=np.uint8)
            else:
                yield cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            time.sleep(1 / fps)

    with gr.Blocks(title="Coachable — Camera Preview") as demo:
        gr.Markdown("## Coachable Robot Camera Preview")
        gr.Markdown(f"`/dev/video{camera_index}` — {actual_w}x{actual_h} @ {actual_fps:.0f}fps")
        img = gr.Image(label="Live Feed", streaming=True)
        demo.load(fn=stream_frames, outputs=img)

    demo.queue()
    demo.launch(server_name="0.0.0.0", server_port=port, share=False)
