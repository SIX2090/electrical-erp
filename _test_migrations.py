#!/usr/bin/env python3
"""Test all schema migrations from a fresh database."""
import sys
import psycopg2
from services.schema_migrations import MIGRATIONS, ensure_schema_migrations

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "dbname": "electrical_erp",
    "user": "electrical_user",
    "password": "admin",
}


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    ensure_schema_migrations(cur)
    conn.commit()

    sorted_migrations = sorted(MIGRATIONS, key=lambda m: m[0])
    print(f"Total migrations to apply: {len(sorted_migrations)}")

    applied = 0
    failed = None
    for version, sql in sorted_migrations:
        cur.execute("SELECT 1 FROM schema_migrations WHERE version=%s", (version,))
        if cur.fetchone():
            continue
        try:
            cur.execute(sql)
            cur.execute(
                "INSERT INTO schema_migrations (version) VALUES (%s) ON CONFLICT (version) DO NOTHING",
                (version,),
            )
            conn.commit()
            applied += 1
        except Exception as e:
            conn.rollback()
            failed = (version, str(e))
            print(f"\nFAILED at {version}:")
            print(f"  {e}")
            print(f"  SQL (first 6 lines):")
            for line in sql.strip().splitlines()[:6]:
                print(f"    {line}")
            break

    if failed:
        print(f"\nStopped after {applied} migrations applied.")
        sys.exit(1)
    else:
        print(f"\nSUCCESS: All {applied} migrations applied.")
        # Count tables
        cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'")
        table_count = cur.fetchone()[0]
        print(f"Tables in database: {table_count}")
        cur.close()
        conn.close()
        sys.exit(0)


if __name__ == "__main__":
    main()
