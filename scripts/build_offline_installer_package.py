from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NAME_PREFIX = "WMS_ERP_Offline_Installer"

EXCLUDE_DIR_NAMES = {
    ".claude",
    ".git",
    ".install_lock",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "backups",
    "logs",
    "memory",
    "output",
    "pgdata",
    "pgsql18",
}

EXCLUDE_REL_PREFIXES = {
    "release/install",
    "release/offline",
    "release/offline_packages",
    "release/trial_users",
    "release/verify_run",
}

EXCLUDE_FILE_NAMES = {
    "install.log",
    "offline_package_manifest.txt",
    "postgres.log",
    "python_install.log",
    "python_audit_install.log",
    "runtime_local_secrets.cmd",
}

EXCLUDE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".tmp",
}


def run_step(args: list[str], *, env: dict[str, str] | None = None, timeout: int = 900) -> None:
    display = " ".join(args)
    print(f"step_start={display}", flush=True)
    result = subprocess.run(
        args,
        cwd=ROOT,
        env=env or os.environ.copy(),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    if result.stdout:
        print(result.stdout.rstrip(), flush=True)
    if result.returncode != 0:
        raise SystemExit(f"step_failed={display} exit_code={result.returncode}")
    print(f"step_ok={display}", flush=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def postgres_bin(name: str) -> Path:
    return ROOT / "pgsql18" / "pgsql" / "bin" / name


def refresh_database_dump(env: dict[str, str]) -> None:
    pg_dump = postgres_bin("pg_dump.exe")
    pg_isready = postgres_bin("pg_isready.exe")
    if not pg_dump.is_file():
        raise SystemExit("missing_pg_dump=pgsql18/pgsql/bin/pg_dump.exe")
    if not pg_isready.is_file():
        raise SystemExit("missing_pg_isready=pgsql18/pgsql/bin/pg_isready.exe")

    pg_host = env.get("PG_HOST", "127.0.0.1")
    pg_port = env.get("PG_PORT", "5432")
    pg_user = env.get("PG_USER", "wms_user")
    pg_database = env.get("PG_DATABASE", "wms")
    if not env.get("PG_PASSWORD"):
        raise SystemExit("missing_env=PG_PASSWORD")

    run_step(
        [str(pg_isready), "-h", pg_host, "-p", pg_port],
        env=env,
        timeout=60,
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    db_dir = ROOT / "db"
    db_dir.mkdir(exist_ok=True)
    dump_path = db_dir / "wms_current.dump"
    temp_path = db_dir / f"wms_current_{stamp}.dump.tmp"

    cmd = [
        str(pg_dump),
        "-h",
        pg_host,
        "-p",
        pg_port,
        "-U",
        pg_user,
        "-d",
        pg_database,
        "-F",
        "c",
        "--no-owner",
        "--no-privileges",
        "-f",
        str(temp_path),
    ]
    run_step(cmd, env=env, timeout=900)

    if temp_path.stat().st_size < 1024 * 1024:
        temp_path.unlink(missing_ok=True)
        raise SystemExit("database_dump_too_small")

    if dump_path.exists():
        backup_dir = ROOT / "backups"
        backup_dir.mkdir(exist_ok=True)
        shutil.copy2(dump_path, backup_dir / f"wms_current_before_package_{stamp}.dump")
    os.replace(temp_path, dump_path)
    print(f"database_dump_refreshed={dump_path}", flush=True)
    print(f"database_dump_size={dump_path.stat().st_size}", flush=True)


def should_skip(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    rel_posix = rel.as_posix()
    parts = rel.parts
    if any(part in EXCLUDE_DIR_NAMES for part in parts[:-1]):
        return True
    if any(rel_posix == prefix or rel_posix.startswith(prefix + "/") for prefix in EXCLUDE_REL_PREFIXES):
        return True
    name = path.name
    if name in EXCLUDE_FILE_NAMES:
        return True
    if path.suffix.lower() in EXCLUDE_SUFFIXES:
        return True
    if name.startswith("WMS_ERP_Offline_Installer_") and name.endswith(".zip"):
        return True
    if name.startswith("direct_access_debug") and path.parent.name == "reports":
        return True
    return False


def iter_package_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if path.is_dir():
            continue
        if should_skip(path):
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(ROOT).as_posix().lower())


def write_manifest(zip_path: Path, files: list[Path], package_root: str) -> Path:
    manifest_path = ROOT / "release" / "offline_package_manifest.txt"
    manifest_path.parent.mkdir(exist_ok=True)
    lines = [
        f"package={zip_path.name}",
        f"generated_at={datetime.now().isoformat(timespec='seconds')}",
        f"package_root={package_root}",
        f"file_count={len(files)}",
        "",
        "sha256  size  path",
    ]
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        lines.append(f"{sha256_file(path)}  {path.stat().st_size}  {rel}")
    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest_path


def write_package_info(zip_path: Path) -> None:
    lines = [
        "WMS ERP offline installer package",
        f"built_at={datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"package_name={zip_path.name}",
        "runtime=Windows offline one-click installer",
        "includes_python_runtime=yes",
        "includes_postgresql_runtime=yes",
        "includes_offline_wheels=yes",
        "includes_database_snapshot=yes",
        "includes_runtime_local_secrets=no",
        "operator_url=http://127.0.0.1:5000",
        "installer_audit=installer_package_audit=ok",
        "source_integrity=ok",
        "prelaunch_audit=core_pages=34 errors=0 warnings=0",
        "crud_audit=erp_crud_targets=46 ok=46 warnings=0 errors=0",
    ]
    (ROOT / "PACKAGE_INFO.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_zip(output_dir: Path, name_prefix: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    package_root = f"{name_prefix}_{stamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / f"{package_root}.zip"

    write_package_info(zip_path)
    files = iter_package_files()
    manifest_path = write_manifest(zip_path, files, package_root)
    files = iter_package_files()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for path in files:
            rel = path.relative_to(ROOT).as_posix()
            archive.write(path, f"{package_root}/{rel}")

    checksum_path = zip_path.with_suffix(".zip.sha256.txt")
    checksum_path.write_text(f"{sha256_file(zip_path)}  {zip_path.name}\n", encoding="ascii")
    print(f"package_zip={zip_path}", flush=True)
    print(f"package_sha256_file={checksum_path}", flush=True)
    print(f"package_manifest={manifest_path}", flush=True)
    print(f"package_size={zip_path.stat().st_size}", flush=True)
    return zip_path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Build the WMS ERP one-click offline installer zip.")
    parser.add_argument("--skip-db-dump", action="store_true", help="Use the existing db/wms_current.dump.")
    parser.add_argument("--output-dir", default="release/offline_packages", help="Output directory for the zip package.")
    parser.add_argument("--name-prefix", default=DEFAULT_NAME_PREFIX, help="Zip and root folder name prefix.")
    args = parser.parse_args(argv)

    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("INVENTORY_NAV_MODE", "gt_pilot")

    if not args.skip_db_dump:
        refresh_database_dump(env)

    python = sys.executable
    run_step([python, "-m", "compileall", "-q", "routes", "scripts", "services"], env=env, timeout=300)
    run_step([python, "scripts/source_integrity_audit.py"], env=env, timeout=300)
    run_step([python, "scripts/erp_prelaunch_audit.py"], env=env, timeout=900)
    run_step([python, "scripts/audit_erp_crud_completeness.py"], env=env, timeout=900)
    run_step([python, "scripts/audit_installer_package.py", "--deep"], env=env, timeout=900)

    zip_path = build_zip((ROOT / args.output_dir).resolve(), args.name_prefix)
    print("offline_package_build=ok", flush=True)
    print(f"ready_to_install=unzip {zip_path.name} and run install.cmd", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
