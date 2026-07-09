from __future__ import annotations

import os
import secrets
import string
import sys
from pathlib import Path

from werkzeug.security import generate_password_hash


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.app_runtime import connect_db  # noqa: E402
from services.env_config import get_pg_password  # noqa: E402


TRIAL_USERS = [
    ("pilot_admin", "Trial Admin", "admin"),
    ("pilot_sales", "Trial Sales", "sales"),
    ("pilot_purchase", "Trial Purchase", "purchase"),
    ("pilot_warehouse", "Trial Warehouse", "warehouse"),
    ("pilot_production", "Trial Production", "production"),
    ("pilot_service", "Trial Service", "service"),
    ("pilot_finance", "Trial Finance", "finance"),
]


def load_local_env() -> None:
    env_file = ROOT / "runtime_local_secrets.cmd"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line.lower().startswith("set "):
            continue
        payload = line[4:].strip()
        if payload.startswith('"') and payload.endswith('"'):
            payload = payload[1:-1]
        if "=" in payload:
            key, value = payload.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def get_db_config() -> dict[str, object]:
    load_local_env()
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "database": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }


def make_password(length: int = 24) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%+-_"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(ch.islower() for ch in password)
            and any(ch.isupper() for ch in password)
            and any(ch.isdigit() for ch in password)
            and any(ch in "!@#$%+-_" for ch in password)
        ):
            return password


def main() -> int:
    rows = []
    usernames = [username for username, _full_name, _role in TRIAL_USERS]
    conn = connect_db(get_db_config())
    try:
        with conn.cursor() as cur:
            for username, full_name, role in TRIAL_USERS:
                cur.execute("SELECT id FROM users WHERE username=%s", (username,))
                existing = cur.fetchone()
                password_hash = generate_password_hash(make_password())
                if existing:
                    cur.execute(
                        """
                        UPDATE users
                        SET password_hash=%s,
                            full_name=%s,
                            role=%s,
                            status='inactive'
                        WHERE username=%s
                        """,
                        (password_hash, full_name, role, username),
                    )
                    action = "updated_inactive"
                else:
                    cur.execute(
                        """
                        INSERT INTO users (username, password_hash, full_name, role, status)
                        VALUES (%s, %s, %s, %s, 'inactive')
                        """,
                        (username, password_hash, full_name, role),
                    )
                    action = "created_inactive"
                rows.append((username, full_name, role, action))
            cur.execute("DELETE FROM login_attempts WHERE username = ANY(%s)", (usernames,))
        conn.commit()
    finally:
        conn.close()

    print(f"trial_users={len(rows)}")
    print(f"login_attempts_cleared={len(usernames)}")
    print("password_handoff_file=disabled")
    print("trial_users_status=inactive")
    print("next_step=admin must reset each trial user password and enable the account before use")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
