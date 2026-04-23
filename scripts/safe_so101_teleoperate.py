#!/usr/bin/env python3
"""Teleoperate SO-ARM101 while protecting follower wrist-roll cable slack.

This is a local safety wrapper around LeRobot's SO101 leader/follower classes.
It treats the current physical wrist-roll alignment as the matched start pose:

    follower_goal = follower_start + (leader_now - leader_start)

The follower wrist-roll goal is clamped around the follower start pose so the
gripper cable cannot be wound through the full wrist-roll range.
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

from lerobot.robots.so_follower.config_so_follower import SO101FollowerConfig
from lerobot.robots.so_follower.so_follower import SO101Follower
from lerobot.teleoperators.so_leader.config_so_leader import SO101LeaderConfig
from lerobot.teleoperators.so_leader.so_leader import SO101Leader


WRIST_KEY = "wrist_roll.pos"
FULL_TURN_DEGREES = 360.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--leader-port", default="/dev/ttyACM0")
    parser.add_argument("--follower-port", default="/dev/ttyACM1")
    parser.add_argument("--leader-id", default="alpha_leader")
    parser.add_argument("--follower-id", default="alpha_follower")
    parser.add_argument("--calibration-dir", type=Path, default=Path("/app/calibration"))
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument(
        "--wrist-safe-degrees",
        type=float,
        default=15.0,
        help="Allowed follower wrist-roll movement on either side of the aligned start pose.",
    )
    parser.add_argument(
        "--freeze-wrist-roll",
        action="store_true",
        help="Hold follower wrist-roll exactly at the aligned start pose.",
    )
    parser.add_argument(
        "--max-relative-target",
        type=float,
        default=15.0,
        help="LeRobot safety cap for per-command follower movement in calibrated units.",
    )
    return parser.parse_args()


def clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def shortest_delta_degrees(current: float, start: float) -> float:
    """Return signed wrist-roll delta in the shortest direction around one turn."""

    delta = (current - start + FULL_TURN_DEGREES / 2) % FULL_TURN_DEGREES - FULL_TURN_DEGREES / 2
    return delta


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    period_s = 1.0 / args.fps
    leader = SO101Leader(
        SO101LeaderConfig(
            port=args.leader_port,
            id=args.leader_id,
            calibration_dir=args.calibration_dir,
        )
    )
    follower = SO101Follower(
        SO101FollowerConfig(
            port=args.follower_port,
            id=args.follower_id,
            calibration_dir=args.calibration_dir,
            max_relative_target=args.max_relative_target,
            cameras={},
        )
    )

    leader.connect()
    follower.connect()
    try:
        start_action = leader.get_action()
        start_obs = follower.get_observation()
        leader_wrist_start = start_action[WRIST_KEY]
        follower_wrist_start = start_obs[WRIST_KEY]
        wrist_low = follower_wrist_start - args.wrist_safe_degrees
        wrist_high = follower_wrist_start + args.wrist_safe_degrees

        print("Safe SO101 teleop started.")
        print(f"  fps: {args.fps:g}")
        print(f"  leader wrist start:   {leader_wrist_start:.2f}")
        print(f"  follower wrist start: {follower_wrist_start:.2f}")
        if args.freeze_wrist_roll:
            print("  follower wrist mode: frozen")
        else:
            print(f"  follower wrist clamp: {wrist_low:.2f}..{wrist_high:.2f}")
        print("Press Ctrl+C to stop.")

        while True:
            loop_start = time.perf_counter()
            action = leader.get_action()

            if args.freeze_wrist_roll:
                action[WRIST_KEY] = follower_wrist_start
            else:
                leader_delta = shortest_delta_degrees(action[WRIST_KEY], leader_wrist_start)
                action[WRIST_KEY] = clamp(follower_wrist_start + leader_delta, wrist_low, wrist_high)

            follower.send_action(action)

            elapsed_s = time.perf_counter() - loop_start
            sleep_s = max(0.0, period_s - elapsed_s)
            if sleep_s:
                time.sleep(sleep_s)
            loop_ms = (time.perf_counter() - loop_start) * 1000
            print(f"Safe teleop loop time: {loop_ms:.2f}ms ({1 / max(loop_ms / 1000, 1e-9):.0f} Hz)", end="\r")
    except KeyboardInterrupt:
        print("\nStopping safe teleop.")
    finally:
        leader.disconnect()
        follower.disconnect()


if __name__ == "__main__":
    main()
