from __future__ import annotations

import os
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor


ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.env_config import get_pg_password  # noqa: E402

DIRTY_CODEPOINTS = {
    0xFFFD,
    0x95C1,
    0x95BF,
    0x9359,
    0x934F,
    0x9351,
    0x9352,
    0x935B,
    0x9366,
    0x9368,
    0x937C,
    0x6434,
    0x9417,
    0x9422,
    0x93C2,
    0x95B2,
    0x7487,
    0xFE3D,
    0x510F,
    0x6E1A,
    0x7C32,
    0x30E5,
    0x7C31,
    0x6944,
    0x935F,
}

SCAN_TARGETS = {
    "products": ("code", "name", "specification", "unit", "category"),
    "suppliers": ("name", "contact_person", "phone"),
    "customers": ("name", "contact_person", "phone"),
    "warehouses": ("name", "code"),
    "locations": ("name", "code"),
}


def has_dirty_text(value) -> bool:
    text = "" if value is None else str(value)
    return "???" in text or any(ord(ch) in DIRTY_CODEPOINTS for ch in text)


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
        for table, columns in SCAN_TARGETS.items():
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema='public' AND table_name=%s
                """,
                (table,),
            )
            existing = {row["column_name"] for row in cur.fetchall()}
            selected = ["id", *[column for column in columns if column in existing]]
            if len(selected) <= 1:
                continue
            cur.execute(f"SELECT {', '.join(selected)} FROM {table} ORDER BY id DESC LIMIT 5000")
            for row in cur.fetchall():
                for column in selected:
                    if column == "id":
                        continue
                    if has_dirty_text(row.get(column)):
                        safe_value = str(row.get(column)).encode("ascii", "backslashreplace").decode("ascii")
                        findings.append((table, row.get("id"), column, safe_value[:180]))

    print(f"database_mojibake_findings={len(findings)}")
    for table, row_id, column, value in findings[:200]:
        print(f"{table}:{row_id}:{column}: {value}")
    if len(findings) > 200:
        print(f"... truncated {len(findings) - 200} findings")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
