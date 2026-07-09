from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_database_mojibake import main as audit_database_mojibake_main  # noqa: E402
from scripts.audit_trial_release_documents import audit_release_documents  # noqa: E402
from scripts.audit_production_completion_source import audit_production_completion_source  # noqa: E402
from scripts.source_integrity_audit import (  # noqa: E402
    audit_quarantine,
    audit_cross_file_contamination,
    audit_mojibake_sources,
    audit_sources,
    audit_warnings,
)
from services.env_config import get_pg_password  # noqa: E402


LOCAL_ENV = ROOT / "runtime_local_secrets.cmd"
if LOCAL_ENV.exists():
    for line in LOCAL_ENV.read_text(encoding="utf-8", errors="ignore").splitlines():
        item = line.strip()
        if not item.lower().startswith("set "):
            continue
        payload = item[4:].strip()
        if payload.startswith('"') and payload.endswith('"'):
            payload = payload[1:-1]
        if "=" in payload:
            key, value = payload.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())

os.environ.setdefault("PG_PASSWORD", "admin")
os.environ.setdefault("INVENTORY_SECRET_KEY", "audit-secret")
os.environ.setdefault("WTF_CSRF_ENABLED", "0")


CORE_PAGES = [
    "/",
    "/master-data",
    "/material",
    "/customer",
    "/supplier",
    "/warehouse",
    "/purchase_request/new",
    "/purchase_request",
    "/purchase-orders",
    "/purchase_receipts",
    "/sales/new",
    "/sales-orders",
    "/shipments",
    "/work-orders/new",
    "/work-orders",
    "/subcontract/new",
    "/subcontract",
    "/subcontract_issue/new",
    "/subcontract_receive/new",
    "/inventory",
    "/transactions",
    "/adjustments/new",
    "/transfers/new",
    "/inventory_checks/new",
    "/assembly-orders/new",
    "/service-orders/new",
    "/service-orders",
    "/receivables",
    "/payables",
    "/finance",
    "/api/health",
    "/api/v1/materials",
    "/api/v1/suppliers",
    "/api/v1/customers",
]

REQUIRED_TABLES = [
    "products",
    "customers",
    "suppliers",
    "warehouses",
    "locations",
    "units",
    "users",
    "sales_orders",
    "purchase_orders",
    "purchase_requisitions",
    "purchase_receipts",
    "stock_transactions",
    "inventory_balances",
    "work_orders",
    "subcontract_orders",
    "customer_receivables",
    "supplier_payables",
]

MINIMUM_MASTER_COUNTS = {
    "products": 1,
    "suppliers": 1,
    "warehouses": 1,
    "units": 1,
    "users": 1,
}


@dataclass
class AuditResult:
    kind: str
    source: str
    detail: str
    severity: str = "error"


def qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def connect():
    return psycopg2.connect(
        host=os.environ.get("PG_HOST", "127.0.0.1"),
        port=int(os.environ.get("PG_PORT", "5432")),
        dbname=os.environ.get("PG_DATABASE", "wms"),
        user=os.environ.get("PG_USER", "wms_user"),
        password=get_pg_password(),
        cursor_factory=RealDictCursor,
    )


def table_count(cur, table: str):
    try:
        cur.execute(f"SELECT COUNT(*) AS count FROM {qident(table)}")
        return int(cur.fetchone()["count"])
    except Exception as exc:
        return exc


def audit_pages(client):
    pages = {}
    findings: list[AuditResult] = []
    for path in CORE_PAGES:
        response = client.get(path)
        pages[path] = response.status_code
        if response.status_code >= 400:
            findings.append(AuditResult("core_page", path, f"returns HTTP {response.status_code}"))
            continue
        body = response.get_data(as_text=True)
        if "???" in body or "\ufffd" in body:
            findings.append(AuditResult("visible_text", path, "contains dirty text marker"))
    return pages, findings


def audit_database_schema():
    findings: list[AuditResult] = []
    with connect() as conn, conn.cursor() as cur:
        for table in REQUIRED_TABLES:
            count = table_count(cur, table)
            if isinstance(count, Exception):
                findings.append(AuditResult("database_schema", table, f"table check failed: {count}"))
        for table, minimum in MINIMUM_MASTER_COUNTS.items():
            count = table_count(cur, table)
            if isinstance(count, Exception):
                findings.append(AuditResult("master_data", table, f"count check failed: {count}"))
            elif count < minimum:
                findings.append(AuditResult("master_data", table, f"requires at least {minimum} row(s), found {count}"))
    return findings


def audit_source_integrity():
    findings = [AuditResult("source_integrity", "python_sources", item) for item in audit_sources()]
    findings.extend(
        AuditResult("source_integrity", "source_tree", item)
        for item in audit_cross_file_contamination()
    )
    findings.extend(
        AuditResult("source_integrity", "source_mojibake", item)
        for item in audit_mojibake_sources()
    )
    findings.extend(
        AuditResult("source_integrity", "script_quarantine", item)
        for item in audit_quarantine()
    )
    findings.extend(AuditResult("source_integrity", "python_sources", item, "warning") for item in audit_warnings())
    return findings


def audit_production_completion_closure_source():
    return [
        AuditResult("production_completion", "completion_source", item)
        for item in audit_production_completion_source()
    ]


def audit_database_cleanliness():
    try:
        result = audit_database_mojibake_main()
    except Exception as exc:
        return [AuditResult("database_mojibake", "master_data", f"audit failed: {exc}")]
    if result:
        return [AuditResult("database_mojibake", "master_data", "dirty master data remains")]
    return []


def audit_release_outputs():
    findings: list[AuditResult] = []
    severity = "warning" if os.environ.get("INSTALLER_PRELAUNCH") == "1" else "error"
    for source, name, ok, detail in audit_release_documents():
        if not ok:
            findings.append(AuditResult("release_document", source, f"{name}: {detail}", severity))
    return findings


def audit_security_and_backup():
    findings: list[AuditResult] = []
    if os.environ.get("PG_PASSWORD") in {"", "admin", None}:
        findings.append(AuditResult("go_live_secret", "PG_PASSWORD", "default local password is still used", "warning"))
    if os.environ.get("INVENTORY_SECRET_KEY") in {"", "audit-secret", "test-secret", None}:
        findings.append(AuditResult("go_live_secret", "INVENTORY_SECRET_KEY", "production secret key is not set", "warning"))
    backup_dir = ROOT / "backups"
    db_dumps = [path for path in backup_dir.glob("*.dump") if path.is_file() and path.stat().st_size > 0] if backup_dir.exists() else []
    source_zips = [path for path in backup_dir.glob("*.zip") if path.is_file() and path.stat().st_size > 0] if backup_dir.exists() else []
    if not db_dumps:
        findings.append(AuditResult("backup", "database", "no PostgreSQL dump found", "warning"))
    if not source_zips:
        findings.append(AuditResult("backup", "source", "no source zip backup found", "warning"))
    return findings


def write_report(pages, findings):
    report_path = ROOT / "logs" / "erp_prelaunch_audit.md"
    report_path.parent.mkdir(exist_ok=True)
    error_count = sum(1 for item in findings if item.severity == "error")
    warning_count = sum(1 for item in findings if item.severity == "warning")
    lines = [
        "# ERP Prelaunch Audit",
        "",
        "## Scope",
        "",
        "- Core ERP pages, document entry routes, master data, business APIs, source integrity, and data cleanliness.",
        "- HTTP status is checked together with visible dirty-text markers.",
        "- Detailed workflow posting is covered by `scripts/audit_full_system_operator_simulation.py`.",
        "",
        "## Summary",
        "",
        f"- Core pages checked: `{len(pages)}`",
        f"- Blocking errors: `{error_count}`",
        f"- Warnings: `{warning_count}`",
        "",
        "## Core Pages",
        "",
    ]
    for path, status in pages.items():
        lines.append(f"- `{path}`: `{status}`")
    lines.extend(["", "## Findings", ""])
    if findings:
        for item in findings:
            lines.append(f"- `{item.severity}` `{item.kind}` `{item.source}`: {item.detail}")
    else:
        lines.append("- No findings from automated checks.")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def write_go_live_checklist(findings):
    checklist_path = ROOT / "logs" / "go_live_checklist.md"
    checklist_path.parent.mkdir(exist_ok=True)
    errors = [item for item in findings if item.severity == "error"]
    warnings = [item for item in findings if item.severity == "warning"]
    lines = [
        "# ERP Go-Live Checklist",
        "",
        "## Automated Result",
        "",
        f"- Blocking errors: `{len(errors)}`",
        f"- Warnings: `{len(warnings)}`",
        "",
        "## Manual Confirmation Items",
        "",
        "- [ ] Confirm go-live module scope and hide out-of-scope modules.",
        "- [ ] Confirm cutover time, data-freeze time, and rollback owner.",
        "- [ ] Confirm material opening, subcontract opening, AR/AP, and open orders are reconciled.",
        "- [ ] Confirm role matrix for purchase, warehouse, production, sales, finance, and admin.",
        "- [ ] Confirm the latest database and source backups can be restored.",
        "",
        "## Automated Findings",
        "",
    ]
    if findings:
        for item in findings:
            lines.append(f"- `{item.severity}` `{item.kind}` `{item.source}`: {item.detail}")
    else:
        lines.append("- No automated findings.")
    checklist_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return checklist_path


def main():
    from app import create_app

    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "LOGIN_RATE_LIMIT": 1000})
    with app.test_client() as client:
        client.post("/login", data={"username": "admin", "password": "admin"})
        pages, findings = audit_pages(client)
    findings.extend(audit_database_schema())
    findings.extend(audit_source_integrity())
    findings.extend(audit_production_completion_closure_source())
    findings.extend(audit_database_cleanliness())
    findings.extend(audit_release_outputs())
    findings.extend(audit_security_and_backup())

    report_path = write_report(pages, findings)
    checklist_path = write_go_live_checklist(findings)
    errors = [item for item in findings if item.severity == "error"]
    warnings = [item for item in findings if item.severity == "warning"]
    print(f"report={report_path}")
    print(f"checklist={checklist_path}")
    print(f"core_pages={len(pages)} errors={len(errors)} warnings={len(warnings)}")
    for item in findings[:40]:
        print(" | ".join([item.severity, item.kind, item.source, item.detail]))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
