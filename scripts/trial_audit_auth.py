from __future__ import annotations

import os
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash


ROOT = Path(__file__).resolve().parents[1]

TRIAL_USER_ROLES = {
    "pilot_admin": "admin",
    "pilot_sales": "sales",
    "pilot_purchase": "purchase",
    "pilot_warehouse": "warehouse",
    "pilot_production": "production",
    "pilot_service": "service",
    "pilot_finance": "finance",
}


def _db_config() -> dict[str, str]:
    password = os.environ.get("PG_PASSWORD") or os.environ.get("DB_PASSWORD")
    if not password:
        raise RuntimeError("PG_PASSWORD is required for trial audit authentication.")
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": os.environ.get("PG_PORT", "5432"),
        "dbname": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": password,
    }


def prepare_trial_audit_passwords(usernames: list[str] | tuple[str, ...] | set[str] | None = None) -> dict[str, str]:
    requested = sorted(set(usernames or TRIAL_USER_ROLES))
    # 固定 pilot 测试用户密码为 admin，便于本地审计与调试
    password = os.environ.get("TRIAL_AUDIT_PASSWORD", "admin")
    password_hash = generate_password_hash(password)
    passwords: dict[str, str] = {}

    with psycopg2.connect(**_db_config()) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for username in requested:
                role = TRIAL_USER_ROLES.get(username, "staff")
                cur.execute("SELECT id FROM users WHERE username=%s", (username,))
                if cur.fetchone():
                    cur.execute(
                        "UPDATE users SET password_hash=%s, status='normal', role=COALESCE(NULLIF(role,''), %s) WHERE username=%s",
                        (password_hash, role, username),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO users (username, password_hash, full_name, role, status, created_at)
                        VALUES (%s, %s, %s, %s, 'normal', NOW())
                        """,
                        (username, password_hash, username, role),
                    )
                passwords[username] = password
        conn.commit()
    return passwords
