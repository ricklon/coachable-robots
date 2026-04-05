"""
hub.py — HuggingFace Hub CLI wrappers.

Thin subprocess wrappers around huggingface-cli.
Handles login, dataset/checkpoint download and upload.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def login(token: str) -> None:
    """Authenticate with HuggingFace Hub."""
    subprocess.run(
        ["huggingface-cli", "login", "--token", token],
        check=True,
    )


def download(repo_id: str, local_dir: Path, repo_type: str = "model") -> None:
    """Download a repo from HuggingFace Hub to a local directory."""
    local_dir.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {repo_id} → {local_dir}")
    subprocess.run(
        [
            "huggingface-cli", "download",
            repo_id,
            "--repo-type", repo_type,
            "--local-dir", str(local_dir),
        ],
        check=True,
    )


def upload(local_dir: Path, repo_id: str, repo_type: str = "model") -> None:
    """Upload a local directory to HuggingFace Hub."""
    print(f"Uploading {local_dir} → {repo_id}")
    subprocess.run(
        [
            "huggingface-cli", "upload",
            repo_id,
            str(local_dir),
            "--repo-type", repo_type,
        ],
        check=True,
    )
