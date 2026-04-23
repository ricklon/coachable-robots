#!/usr/bin/env python3
"""Record SO-ARM101 episodes while protecting follower wrist-roll cable slack."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.datasets.pipeline_features import aggregate_pipeline_dataset_features, create_initial_features
from lerobot.datasets.utils import combine_feature_dicts
from lerobot.datasets.video_utils import VideoEncodingManager
from lerobot.processor import RobotAction
from lerobot.processor.factory import make_default_processors
from lerobot.robots.so_follower.config_so_follower import SO101FollowerConfig
from lerobot.robots.so_follower.so_follower import SO101Follower
from lerobot.scripts.lerobot_record import record_loop
from lerobot.teleoperators.so_leader.config_so_leader import SO101LeaderConfig
from lerobot.teleoperators.so_leader.so_leader import SO101Leader
from lerobot.teleoperators.teleoperator import Teleoperator


WRIST_KEY = "wrist_roll.pos"
FULL_TURN_DEGREES = 360.0


class SafeWristLeader(Teleoperator):
    """LeRobot teleoperator wrapper that clamps follower wrist-roll commands."""

    name = "safe_so101_leader"
    config_class = SO101LeaderConfig

    def __init__(
        self,
        leader: SO101Leader,
        leader_wrist_start: float,
        follower_wrist_start: float,
        wrist_safe_degrees: float,
        freeze_wrist_roll: bool,
    ) -> None:
        self.leader = leader
        self.id = leader.id
        self.leader_wrist_start = leader_wrist_start
        self.follower_wrist_start = follower_wrist_start
        self.wrist_low = follower_wrist_start - wrist_safe_degrees
        self.wrist_high = follower_wrist_start + wrist_safe_degrees
        self.freeze_wrist_roll = freeze_wrist_roll

    @property
    def action_features(self) -> dict[str, type]:
        return self.leader.action_features

    @property
    def feedback_features(self) -> dict[str, type]:
        return self.leader.feedback_features

    @property
    def is_connected(self) -> bool:
        return self.leader.is_connected

    @property
    def is_calibrated(self) -> bool:
        return self.leader.is_calibrated

    def connect(self, calibrate: bool = True) -> None:
        if not self.leader.is_connected:
            self.leader.connect(calibrate=calibrate)

    def calibrate(self) -> None:
        self.leader.calibrate()

    def configure(self) -> None:
        self.leader.configure()

    def send_feedback(self, feedback: dict) -> None:
        self.leader.send_feedback(feedback)

    def disconnect(self) -> None:
        if self.leader.is_connected:
            self.leader.disconnect()

    def get_action(self) -> RobotAction:
        action = self.leader.get_action()
        if self.freeze_wrist_roll:
            action[WRIST_KEY] = self.follower_wrist_start
        else:
            leader_delta = shortest_delta_degrees(action[WRIST_KEY], self.leader_wrist_start)
            action[WRIST_KEY] = clamp(
                self.follower_wrist_start + leader_delta,
                self.wrist_low,
                self.wrist_high,
            )
        return action


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-id", required=True, help="Hugging Face dataset repo, e.g. user/touch-red-block-v1")
    parser.add_argument("--task", required=True, help="Natural language task label stored with each frame")
    parser.add_argument("--num-episodes", type=int, default=20)
    parser.add_argument("--episode-time-s", type=float, default=30.0)
    parser.add_argument("--reset-time-s", type=float, default=10.0)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--leader-port", default="/dev/ttyACM0")
    parser.add_argument("--follower-port", default="/dev/ttyACM1")
    parser.add_argument("--leader-id", default="alpha_leader")
    parser.add_argument("--follower-id", default="alpha_follower")
    parser.add_argument("--calibration-dir", type=Path, default=Path("/app/calibration"))
    parser.add_argument("--dataset-root", type=Path, default=Path("/app/data"))
    parser.add_argument("--wrist-safe-degrees", type=float, default=15.0)
    parser.add_argument("--freeze-wrist-roll", action="store_true")
    parser.add_argument("--max-relative-target", type=float, default=15.0)
    parser.add_argument("--no-push", action="store_true")
    parser.add_argument("--no-video", action="store_true")
    parser.add_argument("--image-writer-processes", type=int, default=0)
    parser.add_argument("--image-writer-threads-per-camera", type=int, default=4)
    parser.add_argument("--vcodec", default="libsvtav1")
    parser.add_argument("--streaming-encoding", action="store_true")
    return parser.parse_args()


def clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def shortest_delta_degrees(current: float, start: float) -> float:
    return (current - start + FULL_TURN_DEGREES / 2) % FULL_TURN_DEGREES - FULL_TURN_DEGREES / 2


def make_cameras(fps: int) -> dict[str, OpenCVCameraConfig]:
    return {
        "top": OpenCVCameraConfig(index_or_path=0, width=1280, height=720, fps=fps),
        "gripper": OpenCVCameraConfig(index_or_path=2, width=1920, height=1080, fps=fps, fourcc="MJPG"),
    }


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    robot = SO101Follower(
        SO101FollowerConfig(
            port=args.follower_port,
            id=args.follower_id,
            calibration_dir=args.calibration_dir,
            max_relative_target=args.max_relative_target,
            cameras=make_cameras(args.fps),
        )
    )
    leader = SO101Leader(
        SO101LeaderConfig(
            port=args.leader_port,
            id=args.leader_id,
            calibration_dir=args.calibration_dir,
        )
    )

    teleop_action_processor, robot_action_processor, robot_observation_processor = make_default_processors()
    features = combine_feature_dicts(
        aggregate_pipeline_dataset_features(
            pipeline=teleop_action_processor,
            initial_features=create_initial_features(action=robot.action_features),
            use_videos=not args.no_video,
        ),
        aggregate_pipeline_dataset_features(
            pipeline=robot_observation_processor,
            initial_features=create_initial_features(observation=robot.observation_features),
            use_videos=not args.no_video,
        ),
    )

    dataset = LeRobotDataset.create(
        args.repo_id,
        args.fps,
        root=args.dataset_root,
        robot_type=robot.name,
        features=features,
        use_videos=not args.no_video,
        image_writer_processes=args.image_writer_processes,
        image_writer_threads=args.image_writer_threads_per_camera * len(robot.cameras),
        vcodec=args.vcodec,
        streaming_encoding=args.streaming_encoding,
    )

    events = {"exit_early": False, "stop_recording": False, "rerecord_episode": False}
    try:
        robot.connect()
        leader.connect()
        leader_wrist_start = leader.get_action()[WRIST_KEY]
        follower_wrist_start = robot.get_observation()[WRIST_KEY]
        teleop = SafeWristLeader(
            leader=leader,
            leader_wrist_start=leader_wrist_start,
            follower_wrist_start=follower_wrist_start,
            wrist_safe_degrees=args.wrist_safe_degrees,
            freeze_wrist_roll=args.freeze_wrist_roll,
        )

        print("Safe SO101 recording started.")
        print(f"  dataset: {args.repo_id}")
        print(f"  task: {args.task}")
        print(f"  episodes: {args.num_episodes}")
        print(f"  episode/reset: {args.episode_time_s:g}s/{args.reset_time_s:g}s")
        print(f"  leader wrist start:   {leader_wrist_start:.2f}")
        print(f"  follower wrist start: {follower_wrist_start:.2f}")
        if args.freeze_wrist_roll:
            print("  follower wrist mode: frozen")
        else:
            print(
                "  follower wrist clamp: "
                f"{teleop.wrist_low:.2f}..{teleop.wrist_high:.2f}"
            )
        print()

        with VideoEncodingManager(dataset):
            for episode in range(args.num_episodes):
                print(f"Episode {episode}: RECORD for {args.episode_time_s:g}s")
                record_loop(
                    robot=robot,
                    events=events,
                    fps=args.fps,
                    teleop_action_processor=teleop_action_processor,
                    robot_action_processor=robot_action_processor,
                    robot_observation_processor=robot_observation_processor,
                    dataset=dataset,
                    teleop=teleop,
                    control_time_s=args.episode_time_s,
                    single_task=args.task,
                )
                if episode < args.num_episodes - 1:
                    print(f"Episode {episode}: RESET for {args.reset_time_s:g}s")
                    record_loop(
                        robot=robot,
                        events=events,
                        fps=args.fps,
                        teleop_action_processor=teleop_action_processor,
                        robot_action_processor=robot_action_processor,
                        robot_observation_processor=robot_observation_processor,
                        teleop=teleop,
                        control_time_s=args.reset_time_s,
                        single_task=args.task,
                    )
                dataset.save_episode()
    except KeyboardInterrupt:
        print("\nStopping safe recording.")
    finally:
        dataset.finalize()
        if robot.is_connected:
            robot.disconnect()
        if leader.is_connected:
            leader.disconnect()

    if not args.no_push:
        dataset.push_to_hub()
        print(f"Dataset at: https://huggingface.co/datasets/{args.repo_id}")


if __name__ == "__main__":
    main()
