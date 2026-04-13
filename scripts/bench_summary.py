#!/usr/bin/env python3
"""Print the latest inference benchmark result per tag."""

import glob
import json
import os


def main() -> None:
    files = sorted(glob.glob("bench/results/bench_inference_*.json"), key=os.path.getmtime)
    if not files:
        print("No benchmark results yet")
        return

    seen = {}
    for path in files:
        with open(path) as f:
            data = json.load(f)
        seen[data.get("tag", "?")] = path

    print(f"{'tag':<12} {'device':<30} {'p50_matmul_512':>16} {'p50_224':>12}")
    print("-" * 72)
    for path in seen.values():
        with open(path) as f:
            data = json.load(f)
        benchmarks = data.get("benchmarks", [])
        matmul = next((b.get("p50_ms", "?") for b in benchmarks if b.get("name") == "matmul_512"), "?")
        policy = next((b.get("p50_ms", "?") for b in benchmarks if b.get("name") == "policy_input_224"), "?")
        device = data.get("device", {}).get("device_name", "?")[:30]
        print(f"{data.get('tag', '?'):<12} {device:<30} {matmul:>16} {policy:>12}")


if __name__ == "__main__":
    main()
