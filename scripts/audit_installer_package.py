from __future__ import annotations

import argparse
import hashlib
import re
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "offline_one_click_install.cmd",
    "install.cmd",
    "start.cmd",
    "restart_erp.cmd",
    "runtime_env.cmd",
    "requirements.txt",
    "app.py",
    "waitress_server.py",
    "scripts/source_integrity_audit.py",
    "scripts/erp_prelaunch_audit.py",
    "scripts/ensure_local_security_env.py",
    "db/wms_current.dump",
    "postgresql-18.4-1-windows-x64-binaries.zip",
)

REQUIRED_DIRS = (
    "routes",
    "services",
    "templates",
    "static",
    "vendor/python-wheels",
)

REQUIRED_CMD_MARKERS = (
    "scripts\\source_integrity_audit.py",
    "scripts\\erp_prelaunch_audit.py",
    "scripts\\ensure_local_security_env.py",
    "pg_restore.exe",
    "waitress_server.py",
)

START_CMD_MARKERS = (
    "pg_isready.exe",
    "pg_ctl.exe",
    "pgdata\\PG_VERSION",
    "waitress_server.py",
)

EXTRACTED_POSTGRES_FILES = (
    "pgsql18/pgsql/bin/initdb.exe",
    "pgsql18/pgsql/bin/pg_ctl.exe",
    "pgsql18/pgsql/bin/pg_isready.exe",
    "pgsql18/pgsql/bin/pg_restore.exe",
    "pgsql18/pgsql/bin/psql.exe",
)

WHEEL_NAME_RE = re.compile(r"^(?P<name>[^=<>!~;\[]+)")


def normalize_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def read_requirements() -> list[str]:
    requirements: list[str] = []
    for raw_line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = WHEEL_NAME_RE.match(line)
        if match:
            requirements.append(normalize_name(match.group("name").strip()))
    return requirements


def wheel_packages() -> set[str]:
    packages: set[str] = set()
    for wheel in (ROOT / "vendor" / "python-wheels").glob("*.whl"):
        packages.add(normalize_name(wheel.name.split("-", 1)[0]))
    return packages


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_package(deep: bool = False) -> tuple[list[str], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []

    for rel in REQUIRED_FILES:
        path = ROOT / rel
        if not path.is_file():
            errors.append(f"missing required file: {rel}")
        elif path.stat().st_size == 0:
            errors.append(f"empty required file: {rel}")

    for rel in REQUIRED_DIRS:
        path = ROOT / rel
        if not path.is_dir():
            errors.append(f"missing required directory: {rel}")
        elif not any(path.iterdir()):
            errors.append(f"empty required directory: {rel}")

    installer = ROOT / "offline_one_click_install.cmd"
    if installer.exists():
        text = installer.read_text(encoding="utf-8", errors="ignore")
        for marker in REQUIRED_CMD_MARKERS:
            if marker not in text:
                errors.append(f"installer does not call required step: {marker}")
        if "pause" not in text.lower():
            warnings.append("installer has no visible pause for operator error review")
        if "%DATE%" in text or "%TIME%" in text:
            warnings.append("installer log uses locale-dependent DATE/TIME variables")

    start_cmd = ROOT / "start.cmd"
    if start_cmd.exists():
        text = start_cmd.read_text(encoding="utf-8", errors="ignore")
        for marker in START_CMD_MARKERS:
            if marker not in text:
                errors.append(f"start script missing runtime guard: {marker}")

    if (ROOT / "requirements.txt").exists() and (ROOT / "vendor" / "python-wheels").is_dir():
        wheels = wheel_packages()
        for requirement in read_requirements():
            if requirement not in wheels:
                errors.append(f"offline wheel missing for requirement: {requirement}")

    if (ROOT / "pgsql18").exists():
        for rel in EXTRACTED_POSTGRES_FILES:
            path = ROOT / rel
            if not path.is_file():
                errors.append(f"extracted PostgreSQL runtime missing: {rel}")

    pg_zip = ROOT / "postgresql-18.4-1-windows-x64-binaries.zip"
    if pg_zip.exists():
        try:
            with zipfile.ZipFile(pg_zip) as archive:
                names = set(archive.namelist())
                for member in ("pgsql/bin/initdb.exe", "pgsql/bin/pg_ctl.exe", "pgsql/bin/pg_restore.exe", "pgsql/bin/psql.exe"):
                    if member not in names:
                        errors.append(f"PostgreSQL archive missing: {member}")
                if deep:
                    bad_member = archive.testzip()
                    if bad_member:
                        errors.append(f"PostgreSQL archive corrupt at: {bad_member}")
        except zipfile.BadZipFile as exc:
            errors.append(f"PostgreSQL archive is not a valid zip: {exc}")

    py_runtime = ROOT / "payload" / "python" / "runtime" / "python.exe"
    py_installer = ROOT / "payload" / "python" / "python-3.11.9-amd64.exe"
    if not py_runtime.exists() and not py_installer.exists():
        errors.append("missing bundled Python runtime and Python installer")

    db_dump = ROOT / "db" / "wms_current.dump"
    if db_dump.exists():
        size_mb = db_dump.stat().st_size / (1024 * 1024)
        notes.append(f"database dump size: {size_mb:.1f} MB")
        if size_mb < 1:
            errors.append("database dump is unexpectedly small")

    if deep:
        for rel in ("db/wms_current.dump", "postgresql-18.4-1-windows-x64-binaries.zip"):
            path = ROOT / rel
            if path.exists():
                notes.append(f"{rel} sha256: {file_sha256(path)}")

    return errors, warnings, notes


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the WMS ERP offline installer package.")
    parser.add_argument("--deep", action="store_true", help="Run zip integrity checks and print package checksums.")
    args = parser.parse_args()

    errors, warnings, notes = audit_package(deep=args.deep)
    print("installer_package_audit=ok" if not errors else "installer_package_audit=failed")
    for item in notes:
        print(f"note: {item}")
    for item in warnings:
        print(f"warning: {item}")
    for item in errors:
        print(f"error: {item}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
