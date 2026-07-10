from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import psycopg2
from psycopg2.extras import RealDictCursor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "erp_auditor"))

from config import DB_CONFIG


TRACE_TABLE_CANDIDATES = [
    "sales_orders",
    "purchase_orders",
    "work_orders",
    "subcontract_orders",
    "inventory_adjustment_orders",
    "inventory_adjustments",
    "transfer_orders",
    "inventory_check_orders",
    "inventory_assembly_orders",
    "production_completion_orders",
    "machine_service_cards",
    "machine_service_orders",
    "machine_service_acceptance_checks",
    "machine_service_rmas",
]

DOWNSTREAM_TABLES = [
    ("bom", "boms", None),
    ("purchase_orders", "purchase_orders", "project_code"),
    ("work_orders", "work_orders", "project_code"),
    ("production_completion_orders", "production_completion_orders", "project_code"),
    ("sales_shipments", "sales_shipments", "project_code"),
    ("service_cards", "machine_service_cards", "project_code"),
]


@dataclass
class Finding:
    code: str
    detail: str


def db_config() -> dict:
    return {
        "host": os.environ.get("PG_HOST") or os.environ.get("DB_HOST") or DB_CONFIG.get("host", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT") or os.environ.get("DB_PORT") or DB_CONFIG.get("port", 5432)),
        "dbname": os.environ.get("PG_DATABASE") or os.environ.get("DB_NAME") or DB_CONFIG.get("dbname", "wms"),
        "user": os.environ.get("PG_USER") or os.environ.get("DB_USER") or DB_CONFIG.get("user", "wms_user"),
        "password": os.environ.get("PG_PASSWORD") or os.environ.get("DB_PASSWORD") or DB_CONFIG.get("password", ""),
    }


def connect():
    return psycopg2.connect(**db_config())


def table_exists(cur, table: str) -> bool:
    cur.execute("SELECT to_regclass(%s) IS NOT NULL AS exists", (f"public.{table}",))
    return bool(cur.fetchone()["exists"])


def columns_for(cur, table: str) -> set[str]:
    cur.execute(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_schema='public' AND table_name=%s
        """,
        (table,),
    )
    return {row["column_name"] for row in cur.fetchall()}


def system_option_enabled(cur, key: str) -> bool:
    if not table_exists(cur, "system_options"):
        return False
    cols = columns_for(cur, "system_options")
    value_col = "value" if "value" in cols else "option_value" if "option_value" in cols else None
    key_col = "key" if "key" in cols else "option_key" if "option_key" in cols else None
    if not value_col or not key_col:
        return False
    cur.execute(f"SELECT {value_col} AS value FROM system_options WHERE {key_col}=%s LIMIT 1", (key,))
    row = cur.fetchone()
    if not row:
        return False
    return str(row["value"]).strip().lower() in {"1", "true", "yes", "on", "enabled", "是", "启用"}


def reference_sources(cur) -> tuple[set[str], set[str]]:
    projects: set[str] = set()
    cabinets: set[str] = set()
    if table_exists(cur, "project_masters"):
        cols = columns_for(cur, "project_masters")
        for col in [c for c in ("project_code", "project_no", "code") if c in cols]:
            cur.execute(f"SELECT DISTINCT NULLIF(TRIM({col}), '') AS value FROM project_masters WHERE NULLIF(TRIM({col}), '') IS NOT NULL")
            projects.update(row["value"] for row in cur.fetchall())
    if table_exists(cur, "cabinet_masters"):
        cols = columns_for(cur, "cabinet_masters")
        for col in [c for c in ("project_code", "project_no") if c in cols]:
            cur.execute(f"SELECT DISTINCT NULLIF(TRIM({col}), '') AS value FROM cabinet_masters WHERE NULLIF(TRIM({col}), '') IS NOT NULL")
            projects.update(row["value"] for row in cur.fetchall())
        for col in [c for c in ("cabinet_no", "cabinet_no") if c in cols]:
            cur.execute(f"SELECT DISTINCT NULLIF(TRIM({col}), '') AS value FROM cabinet_masters WHERE NULLIF(TRIM({col}), '') IS NOT NULL")
            cabinets.update(row["value"] for row in cur.fetchall())
    if table_exists(cur, "projects"):
        cols = columns_for(cur, "projects")
        project_cols = [c for c in ("project_code", "project_no", "code") if c in cols]
        cabinet_cols = [c for c in ("cabinet_no", "cabinet_no") if c in cols]
        for col in project_cols:
            cur.execute(f"SELECT DISTINCT NULLIF(TRIM({col}), '') AS value FROM projects WHERE NULLIF(TRIM({col}), '') IS NOT NULL")
            projects.update(row["value"] for row in cur.fetchall())
        for col in cabinet_cols:
            cur.execute(f"SELECT DISTINCT NULLIF(TRIM({col}), '') AS value FROM projects WHERE NULLIF(TRIM({col}), '') IS NOT NULL")
            cabinets.update(row["value"] for row in cur.fetchall())
    if table_exists(cur, "machine_service_cards"):
        cur.execute("SELECT DISTINCT NULLIF(TRIM(project_code), '') AS value FROM machine_service_cards WHERE NULLIF(TRIM(project_code), '') IS NOT NULL")
        projects.update(row["value"] for row in cur.fetchall())
        cur.execute("SELECT DISTINCT NULLIF(TRIM(cabinet_no), '') AS value FROM machine_service_cards WHERE NULLIF(TRIM(cabinet_no), '') IS NOT NULL")
        cabinets.update(row["value"] for row in cur.fetchall())
    if table_exists(cur, "sales_orders"):
        cur.execute("SELECT DISTINCT NULLIF(TRIM(project_code), '') AS value FROM sales_orders WHERE NULLIF(TRIM(project_code), '') IS NOT NULL")
        projects.update(row["value"] for row in cur.fetchall())
        cur.execute("SELECT DISTINCT NULLIF(TRIM(cabinet_no), '') AS value FROM sales_orders WHERE NULLIF(TRIM(cabinet_no), '') IS NOT NULL")
        cabinets.update(row["value"] for row in cur.fetchall())
    return projects, cabinets


def count_missing_required(cur, table: str, cols: set[str], require_project_cabinet: bool, findings: list[Finding]) -> None:
    if not require_project_cabinet:
        return
    missing_conditions = []
    if "project_code" in cols:
        missing_conditions.append("COALESCE(project_code, '')=''")
    if "cabinet_no" in cols:
        missing_conditions.append("COALESCE(cabinet_no, '')=''")
    for col, code in (("project_code", "project_code"), ("cabinet_no", "cabinet_no")):
        if col not in cols:
            continue
        cur.execute(f"SELECT COUNT(*) AS c FROM {table} WHERE COALESCE({col}, '')=''", ())
        count = int(cur.fetchone()["c"])
        if count:
            findings.append(Finding("PS-MISSING-REQUIRED", f"table={table} column={col} count={count} require_project_cabinet=1"))


def collect_orphans(cur, table: str, cols: set[str], project_refs: set[str], cabinet_refs: set[str], findings: list[Finding]) -> None:
    if "project_code" in cols and project_refs:
        cur.execute(f"SELECT DISTINCT project_code FROM {table} WHERE COALESCE(project_code, '')<>'' LIMIT 500")
        orphan_values = sorted({row["project_code"] for row in cur.fetchall()} - project_refs)
        if orphan_values:
            findings.append(Finding("PS-ORPHAN-PROJECT", f"table={table} count={len(orphan_values)} sample={','.join(orphan_values[:5])}"))
    if "cabinet_no" in cols and cabinet_refs:
        cur.execute(f"SELECT DISTINCT cabinet_no FROM {table} WHERE COALESCE(cabinet_no, '')<>'' LIMIT 500")
        orphan_values = sorted({row["cabinet_no"] for row in cur.fetchall()} - cabinet_refs)
        if orphan_values:
            findings.append(Finding("PS-ORPHAN-SERIAL", f"table={table} count={len(orphan_values)} sample={','.join(orphan_values[:5])}"))


def table_has_project(cur, table: str, col: str | None, project_code: str, sales_order_id: int | None) -> bool:
    if not table_exists(cur, table):
        return False
    cols = columns_for(cur, table)
    if table == "boms":
        if not sales_order_id or not table_exists(cur, "sales_order_items"):
            return True
        cur.execute(
            """
            SELECT 1
              FROM sales_order_items soi
              JOIN boms b ON b.product_id=soi.product_id
             WHERE soi.order_id=%s
             LIMIT 1
            """,
            (sales_order_id,),
        )
        return cur.fetchone() is not None
    if col and col in cols:
        cur.execute(f"SELECT 1 FROM {table} WHERE {col}=%s LIMIT 1", (project_code,))
        return cur.fetchone() is not None
    return True


def collect_trace_gap(cur, findings: list[Finding], require_project_cabinet: bool) -> None:
    if not table_exists(cur, "sales_orders"):
        return
    cur.execute(
        """
        SELECT so.id, so.project_code
          FROM sales_orders so
         WHERE COALESCE(so.project_code, '')<>''
           AND EXISTS (SELECT 1 FROM sales_shipments sh WHERE sh.order_id=so.id)
         ORDER BY so.id DESC
         LIMIT 200
        """
    )
    candidates = cur.fetchall()
    if not candidates:
        return
    complete_candidate = None
    first_gaps = None
    for row in candidates:
        gaps = []
        for label, table, col in DOWNSTREAM_TABLES:
            if not table_has_project(cur, table, col, row["project_code"], row["id"]):
                gaps.append(label)
        if not gaps:
            complete_candidate = row
            break
        if first_gaps is None:
            first_gaps = (row, gaps)
    if complete_candidate:
        return
    if first_gaps:
        row, gaps = first_gaps
        code = "PS-TRACE-GAP" if require_project_cabinet else "PS-TRACE-GAP-INFO"
        findings.append(Finding(code, f"sales_order_id={row['id']} project_code={row['project_code']} missing={','.join(gaps)}"))


def collect_findings(cur) -> tuple[bool, list[Finding]]:
    require_project_cabinet = system_option_enabled(cur, "require_project_cabinet")
    project_refs, cabinet_refs = reference_sources(cur)
    findings: list[Finding] = []

    for table in TRACE_TABLE_CANDIDATES:
        if not table_exists(cur, table):
            continue
        cols = columns_for(cur, table)
        if not ({"project_code", "cabinet_no"} & cols):
            continue
        count_missing_required(cur, table, cols, require_project_cabinet, findings)
        collect_orphans(cur, table, cols, project_refs, cabinet_refs, findings)

    collect_trace_gap(cur, findings, require_project_cabinet)
    return require_project_cabinet, findings


def main() -> int:
    os.environ.setdefault("PG_PASSWORD", "admin")
    with connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            require_project_cabinet, findings = collect_findings(cur)

    blocking = [f for f in findings if f.code in {"PS-MISSING-REQUIRED", "PS-TRACE-GAP"}]
    print("project_cabinet_traceability=ok" if not blocking else "project_cabinet_traceability=failed")
    print(f"require_project_cabinet={1 if require_project_cabinet else 0}")
    print(f"findings={len(findings)} blocking={len(blocking)}")
    for finding in findings:
        print(f"{finding.code} | {finding.detail}")
    return 0 if not blocking else 1


if __name__ == "__main__":
    raise SystemExit(main())
