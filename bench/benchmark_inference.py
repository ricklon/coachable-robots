#!/usr/bin/env python3
"""
benchmark_inference.py — Inference latency benchmark across hardware tiers

Runs on the local machine. Call via SSH or `just bench-inference` to target
remote nodes. Results written to bench/results/ as JSON.

Usage:
    python bench/benchmark_inference.py [--output-dir PATH] [--tag LABEL]

    --output-dir  Directory to write results JSON (default: bench/results/)
    --tag         Label to include in filename, e.g. 'mi100' or 'h100' or 'pi5'
                  Defaults to auto-detected device name.

Designed to run on any tier:
    Local:   python bench/benchmark_inference.py --tag local
    MI100:   ssh cc@<ip> python coachable-robots/bench/benchmark_inference.py --tag mi100
    H100:    ssh cc@<ip> python coachable-robots/bench/benchmark_inference.py --tag h100
    Pi5:     ssh -p 22222 root@<pi> python coachable-robots/bench/benchmark_inference.py --tag pi5
"""

import argparse
import json
import platform
import sys
import time
from datetime import datetime
from pathlib import Path


def detect_device() -> dict:
    info = {
        "hostname": platform.node(),
        "arch":     platform.machine(),
        "os":       platform.system(),
        "python":   platform.python_version(),
    }

    try:
        import torch
        info["pytorch"] = torch.__version__
        info["cuda_available"] = torch.cuda.is_available()
        if torch.cuda.is_available():
            info["device_name"] = torch.cuda.get_device_name(0)
            info["device_count"] = torch.cuda.device_count()
            try:
                # ROCm exposes VRAM via cuda API
                props = torch.cuda.get_device_properties(0)
                info["vram_gb"] = round(props.total_memory / 1e9, 1)
            except Exception:
                pass
        else:
            info["device_name"] = platform.processor() or "cpu"
    except ImportError:
        info["pytorch"] = "not installed"
        info["cuda_available"] = False
        info["device_name"] = "cpu"

    return info


def run_tensor_benchmarks(device: str, warmup: int = 20, reps: int = 200) -> list[dict]:
    """Micro-benchmarks: interpolation and matmul at typical policy input shapes."""
    import torch

    results = []

    configs = [
        ("policy_input_480p",    (1, 3, 480, 640)),
        ("policy_input_224",     (1, 3, 224, 224)),
        ("matmul_512",           None),   # matmul benchmark
        ("matmul_2048",          None),
    ]

    for label, shape in configs:
        try:
            if shape is not None:
                x = torch.randn(*shape, device=device)
                # Warmup
                for _ in range(warmup):
                    _ = torch.nn.functional.interpolate(x, size=(224, 224), mode="bilinear", align_corners=False)
                if device != "cpu":
                    torch.cuda.synchronize()

                times = []
                for _ in range(reps):
                    t0 = time.perf_counter()
                    _ = torch.nn.functional.interpolate(x, size=(224, 224), mode="bilinear", align_corners=False)
                    if device != "cpu":
                        torch.cuda.synchronize()
                    times.append((time.perf_counter() - t0) * 1000)
            else:
                # Matmul size from label
                n = int(label.split("_")[1])
                a = torch.randn(n, n, device=device)
                b = torch.randn(n, n, device=device)
                for _ in range(warmup):
                    _ = torch.matmul(a, b)
                if device != "cpu":
                    torch.cuda.synchronize()

                times = []
                for _ in range(reps):
                    t0 = time.perf_counter()
                    _ = torch.matmul(a, b)
                    if device != "cpu":
                        torch.cuda.synchronize()
                    times.append((time.perf_counter() - t0) * 1000)

            times_sorted = sorted(times)
            results.append({
                "name":    label,
                "shape":   list(shape) if shape else [n, n],
                "reps":    reps,
                "avg_ms":  round(sum(times) / len(times), 3),
                "p50_ms":  round(times_sorted[len(times) // 2], 3),
                "p95_ms":  round(times_sorted[int(len(times) * 0.95)], 3),
                "p99_ms":  round(times_sorted[int(len(times) * 0.99)], 3),
                "min_ms":  round(times_sorted[0], 3),
                "max_ms":  round(times_sorted[-1], 3),
            })
        except Exception as e:
            results.append({"name": label, "error": str(e)})

    return results


def run_cpu_fallback_benchmarks() -> list[dict]:
    """NumPy-based benchmarks for devices without PyTorch."""
    try:
        import numpy as np
    except ImportError:
        return [{"name": "numpy_unavailable", "error": "numpy not installed"}]

    results = []
    configs = [
        ("numpy_matmul_512",  512),
        ("numpy_matmul_2048", 2048),
    ]
    for label, n in configs:
        a = np.random.randn(n, n).astype(np.float32)
        b = np.random.randn(n, n).astype(np.float32)
        # Warmup
        for _ in range(5):
            _ = a @ b
        times = []
        for _ in range(50):
            t0 = time.perf_counter()
            _ = a @ b
            times.append((time.perf_counter() - t0) * 1000)
        times_sorted = sorted(times)
        results.append({
            "name":   label,
            "shape":  [n, n],
            "reps":   50,
            "avg_ms": round(sum(times) / len(times), 3),
            "p50_ms": round(times_sorted[len(times) // 2], 3),
            "p99_ms": round(times_sorted[int(len(times) * 0.99)], 3),
        })
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=None,
                        help="Directory to write results JSON")
    parser.add_argument("--tag", default=None,
                        help="Device label for filename (e.g. mi100, h100, pi5)")
    parser.add_argument("--no-save", action="store_true",
                        help="Print results to stdout only, do not write file")
    args = parser.parse_args()

    t_start = time.monotonic()
    device_info = detect_device()

    # Select compute device
    try:
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        benchmarks = run_tensor_benchmarks(device)
    except ImportError:
        device = "cpu"
        benchmarks = run_cpu_fallback_benchmarks()

    elapsed = round(time.monotonic() - t_start, 2)
    tag     = args.tag or device_info.get("device_name", "unknown").lower().replace(" ", "_")
    ts      = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    result = {
        "tag":          tag,
        "timestamp":    datetime.utcnow().isoformat(),
        "elapsed_s":    elapsed,
        "device":       device_info,
        "compute":      device,
        "benchmarks":   benchmarks,
    }

    print(json.dumps(result, indent=2))

    if not args.no_save:
        # Resolve output dir relative to repo root or CWD
        if args.output_dir:
            out_dir = Path(args.output_dir)
        else:
            script_dir = Path(__file__).parent
            out_dir = script_dir / "results"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"bench_inference_{tag}_{ts}.json"
        out_path.write_text(json.dumps(result, indent=2))
        print(f"\nResults saved: {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
