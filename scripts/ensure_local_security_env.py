from __future__ import annotations

import os
import secrets
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCAL_ENV_CMD = ROOT / "runtime_local_secrets.cmd"
LEGACY_PG_PASSWORD = ROOT / "pg_password.txt"
DEFAULT_PG_PASSWORDS = {"", "admin"}
DEFAULT_SECRET_KEYS = {"", "local-installed-secret-change-before-production", "wms-local-5625-10855-10145"}


def _read_cmd_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line.lower().startswith("set "):
            continue
        payload = line[4:].strip()
        if payload.startswith('"') and payload.endswith('"'):
            payload = payload[1:-1]
        if "=" not in payload:
            continue
        key, value = payload.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _read_legacy_pg_password() -> str:
    if not LEGACY_PG_PASSWORD.exists():
        return ""
    try:
        return LEGACY_PG_PASSWORD.read_text(encoding="utf-8").strip()
    except UnicodeDecodeError:
        return LEGACY_PG_PASSWORD.read_text(encoding="mbcs", errors="ignore").strip()


def _choose_pg_password(existing: dict[str, str]) -> tuple[str, str]:
    env_value = os.environ.get("PG_PASSWORD", "").strip()
    if env_value and env_value not in DEFAULT_PG_PASSWORDS:
        return env_value, "environment"
    current = existing.get("PG_PASSWORD", "").strip()
    if current:
        return current, "runtime_local_secrets.cmd"
    legacy = _read_legacy_pg_password()
    if legacy:
        return legacy, "pg_password.txt"
    return secrets.token_urlsafe(24), "generated"


def _choose_secret_key(existing: dict[str, str]) -> tuple[str, str]:
    env_value = os.environ.get("INVENTORY_SECRET_KEY", "").strip()
    if env_value and env_value not in DEFAULT_SECRET_KEYS:
        return env_value, "environment"
    current = existing.get("INVENTORY_SECRET_KEY", "").strip()
    if current and current not in DEFAULT_SECRET_KEYS:
        return current, "runtime_local_secrets.cmd"
    return secrets.token_urlsafe(48), "generated"


def _write_runtime_cmd(pg_password: str, secret_key: str) -> None:
    content = "\n".join(
        [
            "@echo off",
            "rem Local private runtime secrets. Do not commit or share this file.",
            f'set "PG_PASSWORD={pg_password}"',
            f'set "INVENTORY_SECRET_KEY={secret_key}"',
            'set "INVENTORY_LOCAL_SECURITY_BOOTSTRAPPED=1"',
            "",
        ]
    )
    LOCAL_ENV_CMD.write_text(content, encoding="utf-8")


def main() -> int:
    existing = _read_cmd_env(LOCAL_ENV_CMD)
    pg_password, pg_source = _choose_pg_password(existing)
    secret_key, secret_source = _choose_secret_key(existing)
    _write_runtime_cmd(pg_password, secret_key)
    print(f"local_security_env={LOCAL_ENV_CMD.name}")
    print(f"pg_password_source={pg_source}")
    print(f"secret_key_source={secret_source}")
    if pg_password in DEFAULT_PG_PASSWORDS:
        print("warning=PG_PASSWORD is still the local trial/default database password; replace it before formal go-live.")
    print("values=hidden")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
