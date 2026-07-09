from __future__ import annotations

import argparse
import os
from collections import defaultdict, deque
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor


ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.env_config import get_pg_password, is_production_env  # noqa: E402


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


def qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def existing_columns(cur, table: str) -> set[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s
        """,
        (table,),
    )
    return {row["column_name"] for row in cur.fetchall()}


def fetch_primary_keys(cur) -> dict[str, str]:
    cur.execute(
        """
        SELECT tc.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name=kcu.constraint_name
         AND tc.table_schema=kcu.table_schema
        WHERE tc.table_schema='public' AND tc.constraint_type='PRIMARY KEY'
        ORDER BY tc.table_name, kcu.ordinal_position
        """
    )
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in cur.fetchall():
        grouped[row["table_name"]].append(row["column_name"])
    return {table: cols[0] for table, cols in grouped.items() if len(cols) == 1}


def fetch_foreign_keys(cur) -> list[dict[str, str]]:
    cur.execute(
        """
        SELECT tc.table_name AS child_table,
               kcu.column_name AS child_column,
               ccu.table_name AS parent_table,
               ccu.column_name AS parent_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name=kcu.constraint_name
         AND tc.table_schema=kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name=tc.constraint_name
         AND ccu.table_schema=tc.table_schema
        WHERE tc.table_schema='public' AND tc.constraint_type='FOREIGN KEY'
        ORDER BY ccu.table_name, tc.table_name, kcu.column_name
        """
    )
    return [dict(row) for row in cur.fetchall()]


def find_dirty_master_rows(cur) -> dict[str, set[int]]:
    dirty: dict[str, set[int]] = defaultdict(set)
    for table, columns in SCAN_TARGETS.items():
        existing = existing_columns(cur, table)
        selected = ["id", *[column for column in columns if column in existing]]
        if len(selected) <= 1:
            continue
        cur.execute(f"SELECT {', '.join(qident(col) for col in selected)} FROM {qident(table)}")
        for row in cur.fetchall():
            for column in selected:
                if column != "id" and has_dirty_text(row.get(column)):
                    dirty[table].add(int(row["id"]))
                    break
    return dirty


def expand_referencing_rows(cur, marked: dict[str, set[int]], pks: dict[str, str], fks: list[dict[str, str]]):
    fks_by_parent: dict[str, list[dict[str, str]]] = defaultdict(list)
    for fk in fks:
        if fk["child_table"] in pks and fk["parent_table"] in pks:
            if fk["parent_column"] == pks[fk["parent_table"]]:
                fks_by_parent[fk["parent_table"]].append(fk)

    queue = deque(table for table, ids in marked.items() if ids)
    while queue:
        parent_table = queue.popleft()
        parent_ids = list(marked.get(parent_table, set()))
        if not parent_ids:
            continue
        for fk in fks_by_parent.get(parent_table, []):
            child_table = fk["child_table"]
            child_pk = pks[child_table]
            cur.execute(
                f"""
                SELECT {qident(child_pk)} AS id
                FROM {qident(child_table)}
                WHERE {qident(fk['child_column'])} = ANY(%s)
                """,
                (parent_ids,),
            )
            found = {int(row["id"]) for row in cur.fetchall() if row.get("id") is not None}
            new_ids = found - marked[child_table]
            if new_ids:
                marked[child_table].update(new_ids)
                queue.append(child_table)


def deletion_order(marked: dict[str, set[int]], fks: list[dict[str, str]]) -> list[str]:
    tables = {table for table, ids in marked.items() if ids}
    children: dict[str, set[str]] = defaultdict(set)
    for fk in fks:
        child = fk["child_table"]
        parent = fk["parent_table"]
        if child in tables and parent in tables and child != parent:
            children[parent].add(child)

    seen: set[str] = set()
    order: list[str] = []

    def visit(table: str):
        if table in seen:
            return
        seen.add(table)
        for child in sorted(children.get(table, ())):
            visit(child)
        order.append(table)

    for table in sorted(tables):
        visit(table)
    return order


def delete_marked_rows(cur, marked: dict[str, set[int]], pks: dict[str, str], order: list[str]) -> dict[str, int]:
    deleted: dict[str, int] = {}
    remaining = [table for table in order if marked.get(table)]
    last_remaining = None
    while remaining and remaining != last_remaining:
        last_remaining = list(remaining)
        next_remaining = []
        for table in remaining:
            ids = list(marked[table])
            pk = pks[table]
            cur.execute("SAVEPOINT mojibake_delete")
            try:
                cur.execute(
                    f"DELETE FROM {qident(table)} WHERE {qident(pk)} = ANY(%s)",
                    (ids,),
                )
                deleted[table] = deleted.get(table, 0) + cur.rowcount
                cur.execute("RELEASE SAVEPOINT mojibake_delete")
            except psycopg2.Error as exc:
                cur.execute("ROLLBACK TO SAVEPOINT mojibake_delete")
                cur.execute("RELEASE SAVEPOINT mojibake_delete")
                next_remaining.append(table)
                print(f"blocked_delete {table}: {exc.diag.message_primary or exc.pgerror.strip()}")
        remaining = next_remaining
    if remaining:
        raise RuntimeError(f"Could not delete all marked tables: {', '.join(sorted(remaining))}")
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(description="Delete test rows contaminated by mojibake master data.")
    parser.add_argument("--apply", action="store_true", help="Actually delete rows. Without this, only print a dry run.")
    args = parser.parse_args()

    if is_production_env():
        print("Refusing to clean mojibake data in production environment.")
        return 2

    with connect() as conn, conn.cursor() as cur:
        pks = fetch_primary_keys(cur)
        fks = fetch_foreign_keys(cur)
        marked = find_dirty_master_rows(cur)
        seed_counts = {table: len(ids) for table, ids in sorted(marked.items()) if ids}
        expand_referencing_rows(cur, marked, pks, fks)
        totals = {table: len(ids) for table, ids in sorted(marked.items()) if ids}
        order = deletion_order(marked, fks)

        print("dirty_master_seed_rows=" + str(sum(seed_counts.values())))
        for table, count in seed_counts.items():
            print(f"seed {table}={count}")
        print("delete_closure_rows=" + str(sum(totals.values())))
        for table, count in totals.items():
            print(f"marked {table}={count}")

        if not args.apply:
            conn.rollback()
            print("dry_run=1")
            return 0

        deleted = delete_marked_rows(cur, marked, pks, order)
        print("dry_run=0")
        print("deleted_rows=" + str(sum(deleted.values())))
        for table, count in sorted(deleted.items()):
            print(f"deleted {table}={count}")
        conn.commit()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
