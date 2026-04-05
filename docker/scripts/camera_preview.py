#!/usr/bin/env python3
"""
camera_preview.py — Live camera preview via Gradio

Runs a Gradio app inside the Pi container for remote monitoring during
calibration. Access via SSH port-forward:

  ssh -p 22222 -L 7860:localhost:7860 root@192.168.4.191

Then open http://localhost:7860 in your browser.

Usage:
  python scripts/camera_preview.py [--camera 0] [--port 7860]
"""

import argparse
import time

import cv2
import gradio as gr
import numpy as np


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", type=int, default=0, help="Camera index (default: 0)")
    parser.add_argument("--port", type=int, default=7860, help="Gradio server port (default: 7860)")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    return parser.parse_args()


def main():
    args = parse_args()

    cap = cv2.VideoCapture(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, args.fps)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera {args.camera}")

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    actual_fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"Camera {args.camera} opened: {actual_w}x{actual_h} @ {actual_fps:.0f}fps")

    def stream_frames():
        while True:
            ret, frame = cap.read()
            if not ret:
                yield np.zeros((actual_h, actual_w, 3), dtype=np.uint8)
            else:
                yield cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            time.sleep(1 / args.fps)

    with gr.Blocks(title="SO-ARM101 Camera Preview") as demo:
        gr.Markdown("## SO-ARM101 Camera Preview")
        gr.Markdown(f"`/dev/video{args.camera}` — {actual_w}x{actual_h} @ {actual_fps:.0f}fps")

        img = gr.Image(label="Live Feed", streaming=True)

        demo.load(fn=stream_frames, outputs=img)

    demo.queue()
    demo.launch(server_name="0.0.0.0", server_port=args.port, share=False)


if __name__ == "__main__":
    main()
