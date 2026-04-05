"""
fleet.py — Data model for the coachable robot fleet.

Loads fleet.yaml and provides typed access to robots and coaches.
No side effects, no subprocess calls — safe to import in notebooks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_FLEET_PATH = Path("/app/config/fleet.yaml")


@dataclass
class Robot:
    name: str                    # short slug used in CLI --robot flag
    type: str                    # "so101", "car", etc.
    leader_port: str             # /dev/ttyACM0
    follower_port: str           # /dev/ttyACM1
    camera_index: int            # /dev/video{camera_index}
    coach: str | None            # name of assigned coach (or None)
    status: str                  # "available" | "in_use" | "offline"


@dataclass
class Coach:
    name: str                    # short slug used in CLI --coach flag
    hf_user: str                 # HuggingFace username
    role: str                    # "student" | "instructor" | "agent"


@dataclass
class HFConfig:
    org: str                     # HF org or username for all repos
    dataset_prefix: str          # dataset repos: {org}/{prefix}-{coach}-{task}
    model_prefix: str            # model repos:   {org}/{prefix}-{coach}-{task}


@dataclass
class FleetConfig:
    name: str
    robots: list[Robot]
    coaches: list[Coach]
    hf: HFConfig


def load_fleet(path: Path = DEFAULT_FLEET_PATH) -> FleetConfig:
    """Load fleet configuration from a YAML file."""
    with open(path) as f:
        data = yaml.safe_load(f)

    robots = [
        Robot(
            name=r["name"],
            type=r.get("type", "so101"),
            leader_port=r.get("leader_port", "/dev/ttyACM0"),
            follower_port=r.get("follower_port", "/dev/ttyACM1"),
            camera_index=r.get("camera_index", 0),
            coach=r.get("coach"),
            status=r.get("status", "available"),
        )
        for r in data["fleet"]["robots"]
    ]

    coaches = [
        Coach(
            name=c["name"],
            hf_user=c["hf_user"],
            role=c.get("role", "student"),
        )
        for c in data.get("coaches", [])
    ]

    hf_data = data.get("hf", {})
    hf = HFConfig(
        org=hf_data.get("org", ""),
        dataset_prefix=hf_data.get("dataset_prefix", "soarm101"),
        model_prefix=hf_data.get("model_prefix", "act"),
    )

    return FleetConfig(
        name=data["fleet"]["name"],
        robots=robots,
        coaches=coaches,
        hf=hf,
    )


def get_robot(fleet: FleetConfig, name: str) -> Robot:
    """Look up a robot by name. Raises ValueError if not found."""
    for robot in fleet.robots:
        if robot.name == name:
            return robot
    available = [r.name for r in fleet.robots]
    raise ValueError(f"Robot '{name}' not found. Available: {available}")


def get_coach(fleet: FleetConfig, name: str) -> Coach:
    """Look up a coach by name. Raises ValueError if not found."""
    for coach in fleet.coaches:
        if coach.name == name:
            return coach
    available = [c.name for c in fleet.coaches]
    raise ValueError(f"Coach '{name}' not found. Available: {available}")


def dataset_repo_id(fleet: FleetConfig, robot: Robot, task: str) -> str:
    """
    Construct the HF dataset repo ID for a robot's current coach and task.

    Format: {hf.org}/{dataset_prefix}-{coach}-{task}
    Example: coachable-lab/soarm101-alice-pick_block
    """
    coach_name = robot.coach or "unassigned"
    # Look up HF username if coach is in the roster
    try:
        coach = get_coach(fleet, coach_name)
        hf_user = coach.hf_user
    except ValueError:
        hf_user = coach_name
    return f"{hf_user}/{fleet.hf.dataset_prefix}-{task}"


def model_repo_id(fleet: FleetConfig, robot: Robot, task: str) -> str:
    """
    Construct the HF model repo ID for a robot's current coach and task.

    Format: {hf.org}/{model_prefix}-{coach}-{task}
    Example: coachable-lab/act-alice-pick_block
    """
    coach_name = robot.coach or "unassigned"
    try:
        coach = get_coach(fleet, coach_name)
        hf_user = coach.hf_user
    except ValueError:
        hf_user = coach_name
    return f"{hf_user}/{fleet.hf.model_prefix}-{task}"
