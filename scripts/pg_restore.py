from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BACKUP_DIR = ROOT / "backups"
BACKUP_LOG = BACKUP_DIR / "backup_log.txt"


def load_cmd_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("@", "::")) or line.lower().startswith("rem "):
            continue
        if not line.lower().startswith("set "):
            continue
        payload = line[4:].strip()
        if payload.startswith('"') and payload.endswith('"'):
            payload = payload[1:-1]
        if "=" not in payload:
            continue
        key, value = payload.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def load_runtime_env() -> None:
    load_cmd_env(ROOT / "runtime_env.cmd")
    load_cmd_env(ROOT / "runtime_local_secrets.cmd")


def get_db_config() -> dict[str, str]:
    config_path = ROOT / "erp_auditor" / "config.py"
    DB_CONFIG = {}
    if config_path.exists():
        spec = importlib.util.spec_from_file_location("erp_auditor_config_for_restore", config_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load database config: {config_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        DB_CONFIG = getattr(module, "DB_CONFIG", {})

    return {
        "host": os.environ.get("PG_HOST") or os.environ.get("DB_HOST") or str(DB_CONFIG.get("host") or "127.0.0.1"),
        "port": os.environ.get("PG_PORT") or os.environ.get("DB_PORT") or str(DB_CONFIG.get("port") or "5432"),
        "dbname": os.environ.get("PG_DATABASE") or os.environ.get("DB_NAME") or str(DB_CONFIG.get("dbname") or "wms"),
        "user": os.environ.get("PG_USER") or os.environ.get("DB_USER") or str(DB_CONFIG.get("user") or "wms_user"),
        "password": os.environ.get("PG_PASSWORD") or os.environ.get("DB_PASSWORD") or str(DB_CONFIG.get("password") or ""),
    }


def find_pg_restore() -> str:
    candidates = [
        ROOT / "pgsql18" / "pgsql" / "bin" / "pg_restore.exe",
        ROOT / "pgsql" / "bin" / "pg_restore.exe",
    ]
    pg_bin = os.environ.get("PG_BIN")
    if pg_bin:
        candidates.insert(0, Path(pg_bin) / "pg_restore.exe")
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    found = shutil.which("pg_restore.exe" if os.name == "nt" else "pg_restore")
    if found:
        return found
    raise FileNotFoundError("pg_restore was not found; set PG_BIN or extract the bundled PostgreSQL runtime")


def log_restore(message: str) -> None:
    BACKUP_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with BACKUP_LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} {message}\n")


def run_restore(input_file: Path, force: bool = False) -> None:
    load_runtime_env()
    dump_file = input_file.resolve()
    if not dump_file.exists() or dump_file.stat().st_size <= 0:
        raise FileNotFoundError(f"dump file is missing or empty: {dump_file}")

    cfg = get_db_config()
    if not force:
        answer = input(
            f"Restore {dump_file} into {cfg['dbname']} at {cfg['host']}:{cfg['port']}? Type RESTORE to continue: "
        )
        if answer.strip() != "RESTORE":
            log_restore(f"RESTORE_CANCELLED db={cfg['dbname']} file={dump_file.name}")
            raise RuntimeError("restore cancelled")

    env = {**os.environ, "PGPASSWORD": cfg["password"]}
    command = [
        find_pg_restore(),
        "-h",
        cfg["host"],
        "-p",
        cfg["port"],
        "-U",
        cfg["user"],
        "-d",
        cfg["dbname"],
        "-c",
        "--if-exists",
        str(dump_file),
    ]
    result = subprocess.run(command, env=env, text=True, capture_output=True)
    if result.returncode != 0:
        error = (result.stderr or result.stdout or "pg_restore failed").strip()
        log_restore(f"RESTORE_FAIL db={cfg['dbname']} file={dump_file.name} error={error}")
        raise RuntimeError(error)
    log_restore(f"RESTORE_OK db={cfg['dbname']} file={dump_file.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore a PostgreSQL custom-format dump.")
    parser.add_argument("--input", required=True, type=Path, help="Input .dump file.")
    parser.add_argument("--force", action="store_true", help="Skip the interactive confirmation prompt.")
    args = parser.parse_args()
    try:
        run_restore(args.input, args.force)
    except Exception as exc:
        print(f"RESTORE_FAIL {exc}", file=sys.stderr)
        return 1
    print(f"RESTORE_OK {args.input}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
