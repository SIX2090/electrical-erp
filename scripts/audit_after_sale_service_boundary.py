import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.app_runtime import connect_db
from app import get_db_config


REQUIRED_COLUMNS = {
    "machine_service_cards": [
        "warranty_policy",
        "warranty_basis",
        "warranty_owner",
        "blocked_reason",
        "next_action",
        "downstream_impact",
    ],
    "machine_service_acceptance_checks": [
        "customer_acceptance_by",
        "customer_acceptance_date",
        "corrective_action",
        "owner",
        "blocked_reason",
        "next_action",
        "downstream_impact",
    ],
    "machine_service_orders": [
        "warranty_policy",
        "warranty_decision_basis",
        "customer_acceptance_by",
        "customer_acceptance_date",
        "owner",
        "blocked_reason",
        "next_action",
        "downstream_impact",
    ],
    "machine_service_dispatches": [
        "owner",
        "blocked_reason",
        "next_action",
        "downstream_impact",
    ],
    "machine_service_order_items": [
        "issue_reason",
        "warranty_scope",
        "owner",
        "downstream_impact",
    ],
    "machine_service_return_visits": [
        "owner",
        "blocked_reason",
        "downstream_impact",
    ],
    "machine_service_rmas": [
        "claim_owner",
        "claim_settlement_basis",
        "recovery_date",
        "closed_reason",
        "owner",
        "blocked_reason",
        "next_action",
        "downstream_impact",
    ],
}


REQUIRED_ROUTES = [
    "/service-cards",
    "/service-orders",
    "/service-orders/new",
    "/service-acceptance",
    "/service-acceptance/new",
    "/service-rmas",
    "/service-rmas/new",
    "/service/reports/cost",
    "/service/reports/rma-claim",
]


def table_exists(cur, table_name):
    cur.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema='public' AND table_name=%s
        """,
        (table_name,),
    )
    return bool(cur.fetchone())


def columns(cur, table_name):
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s
        """,
        (table_name,),
    )
    return {row["column_name"] for row in cur.fetchall()}


def scalar(cur, sql, params=()):
    cur.execute(sql, params)
    row = cur.fetchone() or {}
    return next(iter(row.values()), 0) if row else 0


def audit_schema(cur):
    findings = []
    for table_name, required in REQUIRED_COLUMNS.items():
        if not table_exists(cur, table_name):
            findings.append(("error", "SVC-TABLE-MISSING", table_name))
            continue
        existing = columns(cur, table_name)
        for column in required:
            if column not in existing:
                findings.append(("error", "SVC-COLUMN-MISSING", f"{table_name}.{column}"))
    return findings


def audit_route_source():
    registry = (ROOT / "routes" / "registry.py").read_text(encoding="utf-8")
    templates = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in [
            "templates/service_order_form.html",
            "templates/service_order_trace_detail.html",
            "templates/service_acceptance_form.html",
            "templates/service_rma_form.html",
            "templates/service_rma_trace_detail.html",
        ]
        if (ROOT / path).exists()
    )
    findings = []
    for route in REQUIRED_ROUTES:
        if route not in registry and route not in templates:
            findings.append(("error", "SVC-ROUTE-MISSING", route))
    for token in [
        "warranty_policy",
        "warranty_decision_basis",
        "customer_acceptance_by",
        "claim_settlement_basis",
        "service_order_flow_fields",
        "rma_flow_fields",
    ]:
        if token not in registry and token not in templates:
            findings.append(("error", "SVC-CLOSURE-TOKEN-MISSING", token))
    return findings


def audit_data_quality(cur):
    findings = []
    if table_exists(cur, "machine_service_orders"):
        open_without_axis = scalar(
            cur,
            """
            SELECT COUNT(*)
            FROM machine_service_orders
            WHERE COALESCE(status,'') NOT IN ('已关闭','已完成','已作废','closed','completed','cancelled')
              AND (COALESCE(project_code,'')='' OR COALESCE(serial_no,'')='')
            """,
        )
        if open_without_axis:
            findings.append(("warning", "SVC-TRACE-MISSING", f"open service orders missing project/serial: {open_without_axis}"))
        open_without_next_action = scalar(
            cur,
            """
            SELECT COUNT(*)
            FROM machine_service_orders
            WHERE COALESCE(status,'') NOT IN ('已关闭','已完成','已作废','closed','completed','cancelled')
              AND COALESCE(next_action,'')=''
            """,
        )
        if open_without_next_action:
            findings.append(("warning", "SVC-NEXT-ACTION-MISSING", f"open service orders missing next_action: {open_without_next_action}"))
    if table_exists(cur, "machine_service_rmas"):
        open_rma_without_claim_owner = scalar(
            cur,
            """
            SELECT COUNT(*)
            FROM machine_service_rmas
            WHERE COALESCE(status,'') NOT IN ('已关闭','已完成','closed','completed','cancelled')
              AND COALESCE(owner, claim_owner, '')=''
            """,
        )
        if open_rma_without_claim_owner:
            findings.append(("warning", "RMA-OWNER-MISSING", f"open RMAs missing owner: {open_rma_without_claim_owner}"))
    return findings


def main():
    findings = []
    with connect_db(get_db_config()) as conn:
        with conn.cursor() as cur:
            findings.extend(audit_schema(cur))
            findings.extend(audit_data_quality(cur))
    findings.extend(audit_route_source())
    errors = [item for item in findings if item[0] == "error"]
    warnings = [item for item in findings if item[0] == "warning"]
    for level, code, message in findings:
        print(f"{level} | {code} | {message}")
    print(f"after_sale_service_boundary_audit: errors={len(errors)} warnings={len(warnings)}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
