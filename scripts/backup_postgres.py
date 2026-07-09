from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKUPS_DIR = ROOT / "backups"
LOG_FILE = BACKUPS_DIR / "backup_log.txt"
EXCLUDE_DIRS = {".venv", "payload", "backups", "__pycache__", ".pytest_cache"}


def load_cmd_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("@", "rem ", "REM ", "::")):
            continue
        lower_line = line.lower()
        if lower_line.startswith("if ") and " set " in lower_line:
            payload = line[lower_line.index(" set ") + 5 :].strip()
        elif lower_line.startswith("set "):
            payload = line[4:].strip()
        else:
            continue
        if payload.startswith('"') and payload.endswith('"'):
            payload = payload[1:-1]
        if "=" in payload:
            key, value = payload.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def load_runtime_env() -> None:
    load_cmd_env(ROOT / "runtime_env.cmd")
    load_cmd_env(ROOT / "runtime_local_secrets.cmd")


def db_config() -> dict[str, str]:
    try:
        from erp_auditor.config import DB_CONFIG
    except Exception:
        DB_CONFIG = {}
    return {
        "host": os.environ.get("PG_HOST") or os.environ.get("DB_HOST") or str(DB_CONFIG.get("host") or "127.0.0.1"),
        "port": os.environ.get("PG_PORT") or os.environ.get("DB_PORT") or str(DB_CONFIG.get("port") or "5432"),
        "dbname": os.environ.get("PG_DATABASE") or os.environ.get("DB_NAME") or str(DB_CONFIG.get("dbname") or "wms"),
        "user": os.environ.get("PG_USER") or os.environ.get("DB_USER") or str(DB_CONFIG.get("user") or "wms_user"),
        "password": os.environ.get("PG_PASSWORD") or os.environ.get("DB_PASSWORD") or str(DB_CONFIG.get("password") or ""),
    }


def find_pg_tool(name: str) -> str:
    candidates = []
    pg_bin = os.environ.get("PG_BIN")
    if pg_bin:
        candidates.append(Path(pg_bin) / name)
    candidates.append(ROOT / "pgsql18" / "pgsql" / "bin" / name)
    candidates.append(ROOT / "pgsql" / "bin" / name)
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    raise FileNotFoundError(f"{name} not found; set PG_BIN or extract bundled PostgreSQL runtime")


def append_log(message: str) -> None:
    BACKUPS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LOG_FILE.write_text("", encoding="utf-8") if not LOG_FILE.exists() else None
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} {message}\n")


def prune_old_dumps(keep: int) -> None:
    if keep <= 0:
        return
    dumps = sorted(BACKUPS_DIR.glob("db_dump_*.dump"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in dumps[keep:]:
        try:
            path.unlink()
            append_log(f"PRUNE_OK file={path.name}")
        except OSError as exc:
            append_log(f"PRUNE_FAIL file={path.name} error={exc}")


def create_source_zip(output: Path) -> None:
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for pattern in ("*.py", "*.html", "*.css", "*.js", "*.md", "*.cmd", "*.txt"):
            for path in ROOT.rglob(pattern):
                if any(part in EXCLUDE_DIRS for part in path.relative_to(ROOT).parts):
                    continue
                archive.write(path, path.relative_to(ROOT))


def run_backup(output: Path | None, include_source: bool, keep: int) -> tuple[Path, Path | None]:
    load_runtime_env()
    BACKUPS_DIR.mkdir(exist_ok=True)
    cfg = db_config()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dump_file = output or (BACKUPS_DIR / f"db_dump_{timestamp}.dump")
    dump_file.parent.mkdir(parents=True, exist_ok=True)
    pg_dump = find_pg_tool("pg_dump.exe" if os.name == "nt" else "pg_dump")
    env = {**os.environ, "PGPASSWORD": cfg["password"]}
    command = [
        pg_dump,
        "-h",
        cfg["host"],
        "-p",
        cfg["port"],
        "-U",
        cfg["user"],
        "-F",
        "c",
        "-f",
        str(dump_file),
        cfg["dbname"],
    ]
    result = subprocess.run(command, env=env, text=True, capture_output=True)
    if result.returncode != 0:
        append_log(f"BACKUP_FAIL db={cfg['dbname']} file={dump_file.name} error={(result.stderr or result.stdout).strip()}")
        raise RuntimeError(result.stderr or result.stdout or "pg_dump failed")
    if not dump_file.exists() or dump_file.stat().st_size <= 0:
        append_log(f"BACKUP_FAIL db={cfg['dbname']} file={dump_file.name} error=empty dump")
        raise RuntimeError("pg_dump produced an empty dump")

    source_zip = None
    if include_source:
        source_zip = BACKUPS_DIR / f"source_{timestamp}.zip"
        create_source_zip(source_zip)

    prune_old_dumps(keep)
    size = dump_file.stat().st_size
    append_log(f"BACKUP_OK db={cfg['dbname']} file={dump_file.name} size={size}")
    return dump_file, source_zip


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a PostgreSQL custom-format dump for the ERP database.")
    parser.add_argument("--output", type=Path, help="Override the dump output path.")
    parser.add_argument("--no-source", action="store_true", help="Skip the companion source zip backup.")
    parser.add_argument("--keep", type=int, default=7, help="Keep the newest N db_dump_*.dump files.")
    args = parser.parse_args()
    try:
        dump_file, source_zip = run_backup(args.output, not args.no_source, args.keep)
    except Exception as exc:
        print(f"BACKUP_FAIL {exc}", file=sys.stderr)
        return 1
    print(f"BACKUP_OK dump={dump_file}")
    if source_zip:
        print(f"SOURCE_BACKUP_OK zip={source_zip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
