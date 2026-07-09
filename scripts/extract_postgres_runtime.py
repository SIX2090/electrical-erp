from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PREFIXES = (
    "pgsql/pgAdmin 4/",
    "pgsql/doc/",
    "pgsql/symbols/",
)
REQUIRED_MEMBERS = (
    "pgsql/bin/initdb.exe",
    "pgsql/bin/pg_ctl.exe",
    "pgsql/bin/pg_restore.exe",
    "pgsql/bin/psql.exe",
)


def is_excluded(member: str) -> bool:
    normalized = member.replace("\\", "/")
    return any(normalized.startswith(prefix) for prefix in EXCLUDED_PREFIXES)


def safe_clean_destination(destination: Path) -> None:
    resolved_root = ROOT.resolve()
    resolved_destination = destination.resolve()
    if resolved_destination == resolved_root or resolved_root not in resolved_destination.parents:
        raise RuntimeError(f"refusing to remove unsafe destination: {destination}")
    if destination.exists():
        shutil.rmtree(destination)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: extract_postgres_runtime.py <postgres-zip> <destination>")
        return 2

    archive_path = (ROOT / argv[1]).resolve() if not Path(argv[1]).is_absolute() else Path(argv[1])
    destination = (ROOT / argv[2]).resolve() if not Path(argv[2]).is_absolute() else Path(argv[2])
    if not archive_path.is_file():
        print(f"error: PostgreSQL archive not found: {archive_path}")
        return 1

    safe_clean_destination(destination)
    destination.mkdir(parents=True, exist_ok=True)

    extracted = 0
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        missing = [member for member in REQUIRED_MEMBERS if member not in names]
        if missing:
            print(f"error: PostgreSQL archive missing required members: {', '.join(missing)}")
            return 1
        for member in archive.infolist():
            if is_excluded(member.filename):
                continue
            archive.extract(member, destination)
            extracted += 1

    missing_after_extract = [member for member in REQUIRED_MEMBERS if not (destination / member).is_file()]
    if missing_after_extract:
        print(f"error: PostgreSQL runtime extraction incomplete: {', '.join(missing_after_extract)}")
        return 1
    print(f"postgres_runtime_extracted={extracted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
