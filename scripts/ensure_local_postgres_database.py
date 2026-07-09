from __future__ import annotations

import os
import sys

import psycopg2
from psycopg2 import sql


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def main() -> int:
    host = _env("PG_HOST", "127.0.0.1")
    port = int(_env("PG_PORT", "5432"))
    database = _env("PG_DATABASE", "wms")
    user = _env("PG_USER", "wms_user")
    password = _env("PG_PASSWORD")

    if not password:
        print("error=PG_PASSWORD is empty")
        return 1

    admin_user = _env("PG_ADMIN_USER", "postgres")
    admin_password = _env("PG_ADMIN_PASSWORD", password)
    conn = psycopg2.connect(host=host, port=port, user=admin_user, password=admin_password, dbname="postgres")
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (user,))
            if cur.fetchone():
                cur.execute(
                    sql.SQL("ALTER ROLE {} WITH PASSWORD %s CREATEDB").format(sql.Identifier(user)),
                    (password,),
                )
                print(f"postgres_role=updated:{user}")
            else:
                cur.execute(
                    sql.SQL("CREATE USER {} WITH PASSWORD %s CREATEDB").format(sql.Identifier(user)),
                    (password,),
                )
                print(f"postgres_role=created:{user}")

            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,))
            if cur.fetchone():
                print(f"postgres_database=exists:{database}")
            else:
                cur.execute(
                    sql.SQL("CREATE DATABASE {} OWNER {}").format(
                        sql.Identifier(database),
                        sql.Identifier(user),
                    )
                )
                print(f"postgres_database=created:{database}")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
