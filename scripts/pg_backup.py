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
        spec = importlib.util.spec_from_file_location("erp_auditor_config_for_backup", config_path)
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


def find_pg_dump() -> str:
    candidates = [
        ROOT / "pgsql18" / "pgsql" / "bin" / "pg_dump.exe",
        ROOT / "pgsql" / "bin" / "pg_dump.exe",
    ]
    pg_bin = os.environ.get("PG_BIN")
    if pg_bin:
        candidates.insert(0, Path(pg_bin) / "pg_dump.exe")
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    found = shutil.which("pg_dump.exe" if os.name == "nt" else "pg_dump")
    if found:
        return found
    raise FileNotFoundError("pg_dump was not found; set PG_BIN or extract the bundled PostgreSQL runtime")


def log_backup(message: str) -> None:
    BACKUP_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with BACKUP_LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} {message}\n")


def prune_old_backups(keep: int = 7) -> None:
    dumps = sorted(BACKUP_DIR.glob("db_dump_*.dump"), key=lambda path: path.stat().st_mtime, reverse=True)
    for old_dump in dumps[keep:]:
        try:
            old_dump.unlink()
            log_backup(f"PRUNE_OK file={old_dump.name}")
        except OSError as exc:
            log_backup(f"PRUNE_FAIL file={old_dump.name} error={exc}")


def run_backup(output: Path | None = None) -> Path:
    load_runtime_env()
    BACKUP_DIR.mkdir(exist_ok=True)
    cfg = get_db_config()
    output_file = output or BACKUP_DIR / f"db_dump_{datetime.now().strftime('%Y%m%d_%H%M%S')}.dump"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    env = {**os.environ, "PGPASSWORD": cfg["password"]}
    command = [
        find_pg_dump(),
        "-h",
        cfg["host"],
        "-p",
        cfg["port"],
        "-U",
        cfg["user"],
        "-F",
        "c",
        "-f",
        str(output_file),
        cfg["dbname"],
    ]
    result = subprocess.run(command, env=env, text=True, capture_output=True)
    if result.returncode != 0:
        error = (result.stderr or result.stdout or "pg_dump failed").strip()
        if output_file.exists() and output_file.stat().st_size <= 0:
            output_file.unlink()
        log_backup(f"BACKUP_FAIL db={cfg['dbname']} file={output_file.name} error={error}")
        raise RuntimeError(error)
    if not output_file.exists() or output_file.stat().st_size <= 0:
        log_backup(f"BACKUP_FAIL db={cfg['dbname']} file={output_file.name} error=empty_dump")
        raise RuntimeError("pg_dump produced an empty dump file")

    prune_old_backups(keep=7)
    log_backup(f"BACKUP_OK db={cfg['dbname']} file={output_file.name} size={output_file.stat().st_size}")
    return output_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a PostgreSQL custom-format dump.")
    parser.add_argument("--output", type=Path, help="Optional output .dump path.")
    args = parser.parse_args()
    try:
        dump_path = run_backup(args.output)
    except Exception as exc:
        print(f"BACKUP_FAIL {exc}", file=sys.stderr)
        return 1
    print(f"BACKUP_OK {dump_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
