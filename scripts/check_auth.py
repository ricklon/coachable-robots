#!/usr/bin/env python3
"""
check_auth.py — Validate live credentials for Chameleon and HuggingFace

Exits 0 if all required credentials work, 1 if any fail.
Designed to be called by `just check-auth` and by agents before operations.

Usage:
    python scripts/check_auth.py [--json]
"""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=False)

results: dict[str, dict] = {}


def configure_chameleon_env(strip_app_credential_scope: bool = False) -> None:
    """Mirror repo credential names to the OpenStack names python-chi expects."""
    if os.getenv("CHI_CREDENTIAL_ID") and not os.getenv("OS_APPLICATION_CREDENTIAL_ID"):
        os.environ["OS_APPLICATION_CREDENTIAL_ID"] = os.getenv("CHI_CREDENTIAL_ID", "")
    if os.getenv("CHI_CREDENTIAL_SECRET") and not os.getenv("OS_APPLICATION_CREDENTIAL_SECRET"):
        os.environ["OS_APPLICATION_CREDENTIAL_SECRET"] = os.getenv("CHI_CREDENTIAL_SECRET", "")
    os.environ.setdefault("OS_AUTH_TYPE", "v3applicationcredential")
    os.environ.setdefault("OS_PROJECT_DOMAIN_NAME", "chameleon")
    if strip_app_credential_scope and os.getenv("OS_AUTH_TYPE") == "v3applicationcredential":
        for key in ("OS_PROJECT_ID", "OS_PROJECT_NAME", "OS_PROJECT_DOMAIN_ID", "OS_PROJECT_DOMAIN_NAME"):
            os.environ.pop(key, None)


def check_hf() -> dict:
    token = os.getenv("HF_TOKEN", "")
    user  = os.getenv("HF_USER", "")
    if not token or token in ("hf_REPLACE_ME", "REPLACE_ME"):
        return {"ok": False, "error": "HF_TOKEN not set or still placeholder"}
    try:
        from huggingface_hub import HfApi
        api  = HfApi(token=token)
        info = api.whoami()
        name = info.get("name", "unknown")
        return {"ok": True, "user": name, "configured_user": user,
                "match": name == user or not user}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def check_chameleon() -> dict:
    configure_chameleon_env(strip_app_credential_scope=True)
    cred_id     = os.getenv("CHI_CREDENTIAL_ID", "")
    cred_secret = os.getenv("CHI_CREDENTIAL_SECRET", "")
    project     = os.getenv("OS_PROJECT_NAME", "")
    auth_url    = os.getenv("OS_AUTH_URL", "https://chi.tacc.chameleoncloud.org:5000/v3")

    if not cred_id or cred_id == "REPLACE_ME":
        return {"ok": False, "error": "CHI_CREDENTIAL_ID not set or still placeholder"}
    if not cred_secret or cred_secret == "REPLACE_ME":
        return {"ok": False, "error": "CHI_CREDENTIAL_SECRET not set or still placeholder"}

    try:
        import chi
        region   = os.getenv("OS_REGION_NAME", "CHI@TACC")
        domain   = os.getenv("OS_PROJECT_DOMAIN_NAME", "chameleon")
        _site_map = {"CHI@TACC": "CHI@TACC", "CHI@UC": "CHI@UC", "CHI@Edge": "CHI@Edge"}
        chi.use_site(_site_map.get(region, "CHI@TACC"))
        if os.getenv("OS_AUTH_TYPE") == "v3applicationcredential":
            chi.set("auth_type", "v3applicationcredential")
            chi.set("application_credential_id", os.getenv("OS_APPLICATION_CREDENTIAL_ID"))
            chi.set("application_credential_secret", os.getenv("OS_APPLICATION_CREDENTIAL_SECRET"))
        else:
            chi.set("project_name", project)
            chi.set("project_domain_name", domain)
        # Attempt a lightweight API call — list leases
        from chi import lease
        leases = lease.list_leases()
        return {"ok": True, "project": project, "active_leases": len(leases)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def check_env_completeness() -> dict:
    configure_chameleon_env()
    required = [
        "HF_USER", "HF_TOKEN",
        "CHI_CREDENTIAL_ID", "CHI_CREDENTIAL_SECRET",
        "OS_AUTH_TYPE", "OS_APPLICATION_CREDENTIAL_ID",
        "OS_APPLICATION_CREDENTIAL_SECRET",
        "LEASE_NAME", "KEY_PAIR_NAME",
        "PI_HOST", "PI_PORT",
    ]
    if os.getenv("OS_AUTH_TYPE") != "v3applicationcredential":
        required.extend(["OS_PROJECT_NAME", "OS_PROJECT_DOMAIN_NAME"])
    placeholders = ("REPLACE_ME", "your_hf_username", "your_keypair_name", "CHI-XXXXXX")
    missing      = []
    placeholder  = []

    for key in required:
        val = os.getenv(key, "")
        if not val:
            missing.append(key)
        elif any(p in val for p in placeholders):
            placeholder.append(key)

    ok = not missing and not placeholder
    result: dict = {"ok": ok}
    if missing:
        result["missing"] = missing
    if placeholder:
        result["placeholder_values"] = placeholder
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument(
        "--only",
        choices=("all", "chameleon", "huggingface", "env"),
        default="all",
        help="Run only one check group",
    )
    args = parser.parse_args()

    if args.only == "all":
        checks = {
            "env":       check_env_completeness(),
            "chameleon": check_chameleon(),
            "huggingface": check_hf(),
        }
    elif args.only == "chameleon":
        checks = {"chameleon": check_chameleon()}
    elif args.only == "huggingface":
        checks = {"huggingface": check_hf()}
    else:
        checks = {"env": check_env_completeness()}

    all_ok = all(v["ok"] for v in checks.values())

    if args.json:
        print(json.dumps({"ok": all_ok, "checks": checks}, indent=2))
    else:
        width = max(len(k) for k in checks)
        for name, result in checks.items():
            icon  = "OK  " if result["ok"] else "FAIL"
            extra = ""
            if result["ok"]:
                if name == "chameleon":
                    extra = f"  ({result.get('project')} — {result.get('active_leases', 0)} active leases)"
                elif name == "huggingface":
                    extra = f"  (logged in as {result.get('user')})"
            else:
                extra = f"  ERROR: {result.get('error', '')}"
            print(f"  [{icon}] {name:<{width}}{extra}")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
