from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.env_config import get_pg_password


def connect():
    return psycopg2.connect(
        host=os.environ.get("PG_HOST", "127.0.0.1"),
        port=int(os.environ.get("PG_PORT", "5432")),
        dbname=os.environ.get("PG_DATABASE", "wms"),
        user=os.environ.get("PG_USER", "wms_user"),
        password=get_pg_password(),
        cursor_factory=RealDictCursor,
    )


def main() -> int:
    findings = []
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='system_options'
            ORDER BY ordinal_position
            """
        )
        columns = {row["column_name"] for row in cur.fetchall()}
        legacy_ok = {"key", "value"}.issubset(columns)
        modern_ok = {"option_key", "option_value"}.issubset(columns)
        if not (legacy_ok or modern_ok):
            findings.append("system_options has neither key/value nor option_key/option_value columns")
        if legacy_ok:
            cur.execute("SELECT value FROM system_options WHERE key=%s LIMIT 1", ("require_project_cabinet",))
            row = cur.fetchone()
            legacy_value = (row or {}).get("value")
        else:
            legacy_value = None
        if modern_ok:
            cur.execute(
                "SELECT option_value FROM system_options WHERE option_key=%s LIMIT 1",
                ("require_project_cabinet",),
            )
            row = cur.fetchone()
            modern_value = (row or {}).get("option_value")
        else:
            modern_value = None
    value = modern_value if modern_value not in (None, "") else legacy_value
    enabled = str(value or "").strip().lower() in {"1", "true", "yes", "on", "启用", "强制"}
    print(f"system_options_columns={','.join(sorted(columns))}")
    print(f"require_project_cabinet_value={value if value not in (None, '') else 'unset'}")
    print(f"require_project_cabinet_enabled={str(enabled).lower()}")
    print(f"findings={len(findings)}")
    for finding in findings:
        print(f"finding | {finding}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
