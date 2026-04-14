#!/usr/bin/env python3
"""
vault_to_env.py — Decrypt ansible vault and write .env

Reads ansible/.vault_pass, decrypts ansible/group_vars/all/vault.yml,
merges with .env.example defaults, and writes .env.

Usage:
    python scripts/vault_to_env.py [--dry-run]

The vault password must exist at ansible/.vault_pass.
Create it with:
    echo 'your-vault-password' > ansible/.vault_pass
    chmod 600 ansible/.vault_pass
"""

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT    = Path(__file__).parent.parent
VAULT_FILE   = REPO_ROOT / "ansible" / "group_vars" / "all" / "vault.yml"
VARS_FILE    = REPO_ROOT / "ansible" / "group_vars" / "all" / "vars.yml"
VAULT_PASS   = REPO_ROOT / "ansible" / ".vault_pass"
ENV_EXAMPLE  = REPO_ROOT / ".env.example"
ENV_OUT      = REPO_ROOT / ".env"
FLEET_FILE   = REPO_ROOT / "config" / "fleet.yaml"
FLEET_EXAMPLE = REPO_ROOT / "config" / "fleet.example.yaml"

# Maps vault variable names → .env key names
VAULT_MAP = {
    "vault_hf_token":              "HF_TOKEN",
    "vault_chi_credential_id":     "CHI_CREDENTIAL_ID",
    "vault_chi_credential_secret": "CHI_CREDENTIAL_SECRET",
    "vault_control_floating_ip":   "CONTROL_FLOATING_IP",
    "vault_ts_authkey":            "TS_AUTHKEY",
    "vault_openrouter_api_key":    "OPENROUTER_API_KEY",
}

# SSH key material goes to files, not .env
SSH_KEY_VARS = {"vault_pi_ssh_private_key", "vault_pi_ssh_host_key"}


def decrypt_vault() -> dict:
    if not VAULT_PASS.exists():
        sys.exit(
            f"ERROR: {VAULT_PASS} not found.\n"
            f"Create it with:  echo 'your-password' > {VAULT_PASS} && chmod 600 {VAULT_PASS}"
        )
    result = subprocess.run(
        ["ansible-vault", "view", str(VAULT_FILE),
         "--vault-password-file", str(VAULT_PASS)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        sys.exit(f"ERROR: ansible-vault view failed:\n{result.stderr}")
    return yaml.safe_load(result.stdout) or {}


def write_ssh_keys(vault: dict) -> None:
    ssh_dir = Path.home() / ".ssh"
    ssh_dir.mkdir(mode=0o700, exist_ok=True)

    if key := vault.get("vault_pi_ssh_private_key"):
        key_path = ssh_dir / "pi_id_rsa"
        key_path.write_text(key)
        key_path.chmod(0o600)
        print(f"  SSH key written: {key_path}")

    if host_key := vault.get("vault_pi_ssh_host_key"):
        known_hosts = ssh_dir / "known_hosts"
        existing = known_hosts.read_text() if known_hosts.exists() else ""
        pi_host = None
        # Try to get PI_HOST from existing .env or default
        if ENV_OUT.exists():
            for line in ENV_OUT.read_text().splitlines():
                if line.startswith("PI_HOST="):
                    pi_host = line.split("=", 1)[1].strip()
        pi_host = pi_host or "192.168.4.191"
        pi_port = "22222"
        entry = f"[{pi_host}]:{pi_port} {host_key}"
        if entry not in existing:
            with known_hosts.open("a") as f:
                f.write(f"\n{entry}\n")
            print(f"  known_hosts updated: {pi_host}:{pi_port}")


def load_env_example() -> dict[str, str]:
    """Parse .env.example into a dict of key → default value."""
    defaults = {}
    for line in ENV_EXAMPLE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            defaults[key.strip()] = val.strip()
    return defaults


def load_existing_env() -> dict[str, str]:
    """Load existing .env if present, preserving manually-set values."""
    if not ENV_OUT.exists():
        return {}
    existing = {}
    for line in ENV_OUT.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            existing[key.strip()] = val.strip()
    return existing


def load_fleet_config() -> dict[str, str]:
    """Read fleet.yaml (or fleet.example.yaml) and return talkbot config as env vars."""
    fleet_path = FLEET_FILE if FLEET_FILE.exists() else FLEET_EXAMPLE
    fleet = yaml.safe_load(fleet_path.read_text()) or {}
    talkbot = fleet.get("talkbot", {})
    result = {}
    if "llm_backend" in talkbot:
        result["TALKBOT_LLM_PROVIDER"] = talkbot["llm_backend"]
    if "default_model" in talkbot:
        result["TALKBOT_DEFAULT_MODEL"] = talkbot["default_model"]
    if "local_server_url" in talkbot:
        result["TALKBOT_LOCAL_SERVER_URL"] = talkbot["local_server_url"]
    if "agent_prompt" in talkbot:
        result["TALKBOT_AGENT_PROMPT"] = talkbot["agent_prompt"]
    # Quote values that contain spaces (required for .env / just parsing)
    for k, v in result.items():
        if " " in v and not (v.startswith('"') and v.endswith('"')):
            result[k] = f'"{v}"'
    if result:
        print(f"  Fleet config loaded: {fleet_path.name}")
    return result


def build_env(vault: dict, dry_run: bool = False) -> None:
    defaults = load_env_example()
    existing = load_existing_env()
    fleet    = load_fleet_config()

    # Priority (highest wins): vault > fleet > existing > example defaults
    merged = {**defaults, **existing, **fleet}

    # Apply vault mappings
    vault_applied = []
    for vault_key, env_key in VAULT_MAP.items():
        if vault_key in vault:
            val = vault[vault_key]
            if val and val != "REPLACE_ME":
                merged[env_key] = val
                vault_applied.append(env_key)

    # python-chi/OpenStack reads OS_APPLICATION_CREDENTIAL_* directly.
    if merged.get("CHI_CREDENTIAL_ID") and merged.get("CHI_CREDENTIAL_ID") != "REPLACE_ME":
        merged["OS_APPLICATION_CREDENTIAL_ID"] = merged["CHI_CREDENTIAL_ID"]
    if merged.get("CHI_CREDENTIAL_SECRET") and merged.get("CHI_CREDENTIAL_SECRET") != "REPLACE_ME":
        merged["OS_APPLICATION_CREDENTIAL_SECRET"] = merged["CHI_CREDENTIAL_SECRET"]
    merged.setdefault("OS_AUTH_TYPE", "v3applicationcredential")
    merged.setdefault("OS_PROJECT_DOMAIN_NAME", "chameleon")

    if dry_run:
        print("DRY RUN — would write to .env:")
        for k, v in merged.items():
            masked = v[:4] + "***" if any(s in k for s in ("TOKEN", "SECRET", "KEY", "PASSWORD")) else v
            print(f"  {k}={masked}")
        print(f"\nVault values applied: {', '.join(vault_applied)}")
        print(f"Fleet config applied: {', '.join(fleet.keys()) or 'none'}")
        return

    # Write .env preserving example structure (comments + ordering)
    lines = []
    written_keys = set()

    for line in ENV_EXAMPLE.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            lines.append(line)
            continue
        if "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in merged:
                lines.append(f"{key}={merged[key]}")
                written_keys.add(key)
            else:
                lines.append(line)

    # Append any keys from existing .env not in the example
    extra = {k: v for k, v in existing.items() if k not in written_keys}
    if extra:
        lines.append("")
        lines.append("# Additional keys (not in .env.example)")
        for k, v in extra.items():
            lines.append(f"{k}={v}")

    ENV_OUT.write_text("\n".join(lines) + "\n")
    ENV_OUT.chmod(0o600)
    print(f".env written: {ENV_OUT}")
    print(f"  Vault values applied: {', '.join(vault_applied) or 'none'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print what would be written without writing")
    args = parser.parse_args()

    print(f"Decrypting {VAULT_FILE}...")
    vault = decrypt_vault()

    print("Writing SSH keys...")
    write_ssh_keys(vault)

    print("Building .env...")
    build_env(vault, dry_run=args.dry_run)

    print("\nDone. Run `just check-auth` to verify credentials.")


if __name__ == "__main__":
    main()
