from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
RUNNER_LOG = LOG_DIR / "homepage_bug_runner_latest.log"
STDERR_LOG = LOG_DIR / "homepage_bug_audit_stderr_latest.log"
AUDIT_SCRIPT = ROOT / "scripts" / "audit_homepage_bug_candidates.py"


def log(message: str) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    with RUNNER_LOG.open("a", encoding="utf-8", errors="replace") as fh:
        fh.write(message + "\n")
    print(message, flush=True)


def load_cmd_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line.lower().startswith("set "):
            continue
        body = line[4:].strip()
        if body.startswith('"') and body.endswith('"'):
            body = body[1:-1]
        if "=" not in body:
            continue
        key, value = body.split("=", 1)
        key = key.strip()
        if key and not os.environ.get(key):
            os.environ[key] = value


def run(args: list[str], timeout: int = 20, check: bool = False) -> subprocess.CompletedProcess[str]:
    log("[CMD] " + " ".join(args))
    try:
        cp = subprocess.run(
            args,
            cwd=str(ROOT),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        log(f"[TIMEOUT] after {timeout}s")
        if output:
            log(output.rstrip())
        raise
    if cp.stdout:
        log(cp.stdout.rstrip())
    log(f"[RC] {cp.returncode}")
    if check and cp.returncode != 0:
        raise SystemExit(cp.returncode)
    return cp


def pg_ready(pg_isready: Path, host: str, port: str, user: str, database: str) -> bool:
    try:
        cp = run([str(pg_isready), "-h", host, "-p", port, "-U", user, "-d", database], timeout=5)
    except subprocess.TimeoutExpired:
        return False
    return cp.returncode == 0


def ensure_postgres() -> int:
    host = os.environ.setdefault("PG_HOST", "127.0.0.1")
    port = os.environ.setdefault("PG_PORT", "5432")
    database = os.environ.setdefault("PG_DATABASE", "wms")
    user = os.environ.setdefault("PG_USER", "wms_user")
    os.environ.setdefault("PG_PASSWORD", "admin")

    pg_isready = ROOT / "pgsql18" / "pgsql" / "bin" / "pg_isready.exe"
    pg_ctl = ROOT / "pgsql18" / "pgsql" / "bin" / "pg_ctl.exe"
    pgdata = ROOT / "pgdata"

    log(f"[PG] target={host}:{port}/{database} user={user}")
    if pg_isready.exists() and pg_ready(pg_isready, host, port, user, database):
        log("[PG] ready")
        return 0

    if host.lower() not in {"127.0.0.1", "localhost"}:
        log(f"[FATAL] PostgreSQL is not ready on non-local host {host}:{port}")
        return 1
    if not pg_ctl.exists():
        log("[FATAL] PostgreSQL runtime is missing. Run offline_one_click_install.cmd first.")
        return 1
    if not (pgdata / "PG_VERSION").exists():
        log("[FATAL] PostgreSQL data directory is missing. Run offline_one_click_install.cmd first.")
        return 1

    log(f"[PG] starting local PostgreSQL on {host}:{port}")
    run([str(pg_ctl), "-D", str(pgdata), "-l", str(ROOT / "postgres.log"), "-o", f"-p {port}", "start"], timeout=30)

    for i in range(1, 21):
        log(f"[PG] readiness check {i}/20")
        if pg_isready.exists() and pg_ready(pg_isready, host, port, user, database):
            log("[PG] ready")
            return 0
        time.sleep(1)
    log("[FATAL] PostgreSQL did not become ready")
    return 1


def main() -> int:
    LOG_DIR.mkdir(exist_ok=True)
    RUNNER_LOG.write_text(
        f"Homepage bug audit runner started at {datetime.now().isoformat(timespec='seconds')}\n"
        f"Project: {ROOT}\n",
        encoding="utf-8",
    )
    STDERR_LOG.write_text("", encoding="utf-8")

    load_cmd_env(ROOT / "runtime_env.cmd")
    load_cmd_env(ROOT / "runtime_local_secrets.cmd")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "homepage-audit-secret")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    python = ROOT / ".venv" / "Scripts" / "python.exe"
    py = str(python if python.exists() else Path(sys.executable))
    log(f"[PY] {py}")

    rc = ensure_postgres()
    if rc != 0:
        return rc

    log("[AUDIT] running homepage bug audit")
    try:
        cp = subprocess.run(
            [py, str(AUDIT_SCRIPT)],
            cwd=str(ROOT),
            env=os.environ.copy(),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=300,
        )
    except subprocess.TimeoutExpired as exc:
        log("[AUDIT] timeout after 300s")
        STDERR_LOG.write_text(str(exc), encoding="utf-8", errors="replace")
        return 124

    if cp.stdout:
        log(cp.stdout.rstrip())
    STDERR_LOG.write_text(cp.stderr or "", encoding="utf-8", errors="replace")
    if cp.stderr:
        log("[AUDIT STDERR]")
        log(cp.stderr.rstrip())
    log(f"[AUDIT RC] {cp.returncode}")
    return cp.returncode


if __name__ == "__main__":
    raise SystemExit(main())
