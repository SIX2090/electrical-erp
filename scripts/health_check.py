#!/usr/bin/env python
from __future__ import annotations

import os
import shutil
import subprocess
import sys


def check_database() -> tuple[bool, str]:
    if not os.environ.get("PG_PASSWORD"):
        return False, "Database password is not configured in PG_PASSWORD"
    try:
        import psycopg2

        conn = psycopg2.connect(
            host=os.environ.get("PG_HOST", "127.0.0.1"),
            port=int(os.environ.get("PG_PORT", "5432")),
            database=os.environ.get("PG_DATABASE", "wms"),
            user=os.environ.get("PG_USER", "wms_user"),
            password=os.environ["PG_PASSWORD"],
            connect_timeout=5,
        )
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM pg_tables WHERE schemaname='public'")
        table_count = cur.fetchone()[0]
        conn.close()
        return True, f"Database OK: {table_count} tables"
    except Exception as exc:
        return False, f"Database connection failed: {exc}"


def check_task(task_name: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["schtasks", "/Query", "/TN", task_name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return True, f"Task '{task_name}' configured"
        return False, f"Task '{task_name}' is missing"
    except Exception as exc:
        return False, f"Task '{task_name}' check failed: {exc}"


def check_disk_space(min_gb: int = 5) -> tuple[bool, str]:
    try:
        stats = shutil.disk_usage(".")
        free_gb = stats.free / (1024**3)
        if free_gb >= min_gb:
            return True, f"Disk space OK: {free_gb:.1f} GB free"
        return False, f"Low disk space: {free_gb:.1f} GB free (minimum: {min_gb} GB)"
    except Exception as exc:
        return False, f"Disk check failed: {exc}"


def main() -> int:
    print()
    print("=" * 50)
    print("    ERP System Health Check")
    print("=" * 50)
    print()

    checks = [
        ("Database Connection", check_database),
        ("Auto Backup Task", lambda: check_task("ERP_Daily_Backup")),
        ("Database Monitor Task", lambda: check_task("ERP_Monitor_Database")),
        ("Disk Monitor Task", lambda: check_task("ERP_Monitor_Disk")),
        ("Disk Space", check_disk_space),
    ]

    passed = 0
    failed = 0
    for index, (name, check_func) in enumerate(checks, 1):
        print(f"[{index}/{len(checks)}] Checking {name}...")
        try:
            success, message = check_func()
        except Exception as exc:
            success, message = False, f"Error: {exc}"
        if success:
            print(f"    OK: {message}")
            passed += 1
        else:
            print(f"    FAIL: {message}")
            failed += 1
        print()

    print("=" * 50)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 50)
    print()

    if failed == 0:
        print("System health is GOOD.")
        return 0

    print(f"Found {failed} issue(s).")
    print("Recommendations:")
    print("- Run scripts\\setup_all_operations.cmd as Administrator if scheduled tasks are missing.")
    print("- Confirm PostgreSQL is running and PG_PASSWORD is configured.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
