#!/usr/bin/env python3
"""Validate that .env does not contain placeholder values."""

import os
from pathlib import Path
import sys


def main() -> None:
    env_path = Path(".env")
    if not env_path.exists():
        print("ERROR: .env not found - run 'just vault-to-env' first")
        sys.exit(1)

    for line in env_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"'))

    required = {
        "HF_USER",
        "HF_TOKEN",
        "CHI_CREDENTIAL_ID",
        "CHI_CREDENTIAL_SECRET",
        "LEASE_NAME",
        "KEY_PAIR_NAME",
        "PI_HOST",
        "PI_PORT",
    }
    if os.environ.get("OS_AUTH_TYPE") != "v3applicationcredential":
        required.add("OS_PROJECT_NAME")
    placeholders = ("REPLACE_ME", "your_hf_username", "your_keypair_name", "CHI-XXXXXX")
    bad = [
        key
        for key, value in os.environ.items()
        if key in required
        if any(placeholder in str(value) for placeholder in placeholders)
    ]
    if bad:
        print("Placeholders found: " + ", ".join(sorted(bad)))
        sys.exit(1)
    print("ENV: no placeholders")


if __name__ == "__main__":
    main()
