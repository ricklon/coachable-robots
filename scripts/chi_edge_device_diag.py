#!/usr/bin/env python3
"""Diagnose CHI@Edge camera and serial passthrough from inside a container.

Run inside the CHI@Edge container:

    python /tmp/chi_edge_device_diag.py
    python /tmp/chi_edge_device_diag.py --json

The script uses only the Python standard library for device discovery and V4L2
capability probing. If OpenCV or pyserial are installed, it also tries frame
capture and serial open checks.
"""

from __future__ import annotations

import argparse
import ctypes
import fcntl
import glob
import grp
import json
import multiprocessing as mp
import os
import pwd
import queue
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any


VIDIOC_QUERYCAP = 0x80685600


class V4L2Capability(ctypes.Structure):
    _fields_ = [
        ("driver", ctypes.c_char * 16),
        ("card", ctypes.c_char * 32),
        ("bus_info", ctypes.c_char * 32),
        ("version", ctypes.c_uint32),
        ("capabilities", ctypes.c_uint32),
        ("device_caps", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32 * 3),
    ]


def _decode(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("utf-8", errors="replace")


def group_name(gid: int) -> str:
    try:
        return grp.getgrgid(gid).gr_name
    except KeyError:
        return str(gid)


def node_info(path: str) -> dict[str, Any]:
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return {"path": path, "exists": False}

    mode = stat.filemode(st.st_mode)
    try:
        user = pwd.getpwuid(st.st_uid).pw_name
    except KeyError:
        user = str(st.st_uid)
    try:
        group = grp.getgrgid(st.st_gid).gr_name
    except KeyError:
        group = str(st.st_gid)

    info: dict[str, Any] = {
        "path": path,
        "exists": True,
        "mode": mode,
        "uid": st.st_uid,
        "gid": st.st_gid,
        "user": user,
        "group": group,
        "major": os.major(st.st_rdev) if stat.S_ISCHR(st.st_mode) else None,
        "minor": os.minor(st.st_rdev) if stat.S_ISCHR(st.st_mode) else None,
        "readable": os.access(path, os.R_OK),
        "writable": os.access(path, os.W_OK),
    }
    return info


def v4l2_querycap(path: str) -> dict[str, Any]:
    info: dict[str, Any] = {"path": path}
    try:
        with open(path, "rb", buffering=0) as fh:
            cap = V4L2Capability()
            fcntl.ioctl(fh, VIDIOC_QUERYCAP, cap)
    except Exception as exc:  # noqa: BLE001 - diagnostic output should keep raw failures
        info["ok"] = False
        info["error"] = f"{type(exc).__name__}: {exc}"
        return info

    info.update(
        {
            "ok": True,
            "driver": _decode(bytes(cap.driver)),
            "card": _decode(bytes(cap.card)),
            "bus_info": _decode(bytes(cap.bus_info)),
            "version": cap.version,
            "capabilities_hex": hex(cap.capabilities),
            "device_caps_hex": hex(cap.device_caps),
        }
    )
    return info


def _opencv_probe_worker(path: str, result_queue: mp.Queue) -> None:
    try:
        import cv2  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        result_queue.put({"path": path, "available": False, "error": f"{type(exc).__name__}: {exc}"})
        return

    result: dict[str, Any] = {
        "path": path,
        "available": True,
        "cv2_version": getattr(cv2, "__version__", "unknown"),
    }
    try:
        cap = cv2.VideoCapture(path, cv2.CAP_V4L2)
        result["opened"] = bool(cap.isOpened())
        ok, frame = cap.read() if cap.isOpened() else (False, None)
        result["read"] = bool(ok)
        result["shape"] = list(frame.shape) if frame is not None else None
        if ok:
            out = f"/tmp/{Path(path).name}.jpg"
            result["write_ok"] = bool(cv2.imwrite(out, frame))
            result["output"] = out
        cap.release()
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"{type(exc).__name__}: {exc}"
    result_queue.put(result)


def opencv_probe(path: str, timeout: float = 4.0) -> dict[str, Any]:
    result_queue: mp.Queue = mp.Queue()
    proc = mp.Process(target=_opencv_probe_worker, args=(path, result_queue))
    proc.start()
    proc.join(timeout)
    if proc.is_alive():
        proc.terminate()
        proc.join(1)
        if proc.is_alive():
            proc.kill()
            proc.join(1)
        return {
            "path": path,
            "available": None,
            "timeout": True,
            "error": f"OpenCV probe timed out after {timeout:.1f}s",
        }
    try:
        return result_queue.get_nowait()
    except queue.Empty:
        return {
            "path": path,
            "available": None,
            "exitcode": proc.exitcode,
            "error": "OpenCV probe exited without returning a result",
        }


def serial_probe(path: str) -> dict[str, Any]:
    result: dict[str, Any] = {"path": path}
    try:
        import serial  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        result.update({"available": False, "error": f"{type(exc).__name__}: {exc}"})
        return result

    result["available"] = True
    try:
        ser = serial.Serial(path, baudrate=1_000_000, timeout=0.2)
        result["open"] = True
        ser.close()
    except Exception as exc:  # noqa: BLE001
        result["open"] = False
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def command_probe(command: list[str]) -> dict[str, Any]:
    if not shutil.which(command[0]):
        return {"command": command, "available": False}
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    except Exception as exc:  # noqa: BLE001
        return {"command": command, "available": True, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "command": command,
        "available": True,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
    }


def collect() -> dict[str, Any]:
    video_nodes = sorted(glob.glob("/dev/video*"))
    serial_nodes = sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"))
    return {
        "identity": {
            "hostname": os.uname().nodename,
            "uid": os.getuid(),
            "gid": os.getgid(),
            "groups": [group_name(gid) for gid in os.getgroups()],
        },
        "environment": {
            key: os.getenv(key)
            for key in ("TS_HOSTNAME", "LEADER_PORT", "FOLLOWER_PORT", "CAMERA_INDEX")
            if os.getenv(key) is not None
        },
        "commands": {
            "v4l2_ctl": command_probe(["v4l2-ctl", "--list-devices"]),
            "ffmpeg": command_probe(["ffmpeg", "-hide_banner", "-version"]),
        },
        "video": [
            {
                "node": node_info(path),
                "v4l2": v4l2_querycap(path),
                "opencv": opencv_probe(path),
            }
            for path in video_nodes
        ],
        "serial": [
            {
                "node": node_info(path),
                "serial": serial_probe(path),
            }
            for path in serial_nodes
        ],
    }


def print_human(report: dict[str, Any]) -> None:
    print("== Identity ==")
    print(json.dumps(report["identity"], indent=2))
    print("\n== Environment ==")
    print(json.dumps(report["environment"], indent=2))
    print("\n== Tools ==")
    for name, result in report["commands"].items():
        print(f"{name}: available={result.get('available')} rc={result.get('returncode')}")
    print("\n== Video ==")
    if not report["video"]:
        print("no /dev/video* nodes")
    for item in report["video"]:
        node = item["node"]
        v4l2 = item["v4l2"]
        cv = item["opencv"]
        print(
            f"{node['path']} {node.get('mode')} {node.get('user')}:{node.get('group')} "
            f"rw={node.get('readable')}/{node.get('writable')}"
        )
        print(f"  v4l2 ok={v4l2.get('ok')} card={v4l2.get('card')} error={v4l2.get('error')}")
        print(
            f"  opencv available={cv.get('available')} opened={cv.get('opened')} "
            f"read={cv.get('read')} shape={cv.get('shape')} error={cv.get('error')}"
        )
    print("\n== Serial ==")
    if not report["serial"]:
        print("no /dev/ttyACM* or /dev/ttyUSB* nodes")
    for item in report["serial"]:
        node = item["node"]
        ser = item["serial"]
        print(
            f"{node['path']} {node.get('mode')} {node.get('user')}:{node.get('group')} "
            f"rw={node.get('readable')}/{node.get('writable')} open={ser.get('open')} "
            f"error={ser.get('error')}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print full JSON report")
    args = parser.parse_args()

    report = collect()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_human(report)


if __name__ == "__main__":
    main()
