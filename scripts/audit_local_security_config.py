from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCAL_ENV_CMD = ROOT / "runtime_local_secrets.cmd"
DEFAULT_PG_PASSWORDS = {"", "admin"}
DEFAULT_SECRET_KEYS = {"", "local-installed-secret-change-before-production", "wms-local-5625-10855-10145", "audit-secret", "test-secret"}


def _read_cmd_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    text = path.read_text(encoding="utf-8", errors="ignore")
    for line in text.splitlines():
        item = line.strip()
        if not item.lower().startswith("set "):
            continue
        payload = item[4:].strip()
        if payload.startswith('"') and payload.endswith('"'):
            payload = payload[1:-1]
        if "=" in payload:
            key, value = payload.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def _contains_forbidden_default(path: Path) -> list[str]:
    findings: list[str] = []
    if not path.exists():
        return findings
    text = path.read_text(encoding="utf-8", errors="ignore")
    for line_no, line in enumerate(text.splitlines(), 1):
        normalized = line.strip().lower()
        if re.search(r"set\s+\"?pg_password=admin\"?", normalized):
            findings.append(f"{path.name}:{line_no}: sets PG_PASSWORD to admin")
        if "local-installed-secret-change-before-production" in normalized:
            findings.append(f"{path.name}:{line_no}: sets placeholder INVENTORY_SECRET_KEY")
        if "wms-local-5625-10855-10145" in normalized:
            findings.append(f"{path.name}:{line_no}: sets fixed INVENTORY_SECRET_KEY")
    return findings


def main() -> int:
    findings: list[str] = []
    warnings: list[str] = []
    values = _read_cmd_env(LOCAL_ENV_CMD)
    if not LOCAL_ENV_CMD.exists():
        findings.append("runtime_local_secrets.cmd is missing; run python scripts\\ensure_local_security_env.py")
    pg_password = values.get("PG_PASSWORD", "")
    if not pg_password:
        findings.append("PG_PASSWORD is missing in runtime_local_secrets.cmd")
    elif pg_password in DEFAULT_PG_PASSWORDS:
        warnings.append("PG_PASSWORD is still the local trial/default database password; save the real database password before formal go-live")
    if values.get("INVENTORY_SECRET_KEY", "") in DEFAULT_SECRET_KEYS:
        findings.append("INVENTORY_SECRET_KEY is missing or still a placeholder in runtime_local_secrets.cmd")
    if len(values.get("INVENTORY_SECRET_KEY", "")) < 32:
        findings.append("INVENTORY_SECRET_KEY is shorter than 32 characters")

    for rel in ("runtime_env.cmd", "start.cmd", "install.cmd", "restart_erp.cmd"):
        findings.extend(_contains_forbidden_default(ROOT / rel))

    if findings:
        print("local_security_config=failed")
        for item in findings:
            print(item)
        return 1
    print("local_security_config=ok")
    for item in warnings:
        print(f"warning | {item}")
    print("values=hidden")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
