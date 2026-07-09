from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("WTF_CSRF_ENABLED", "0")

from app import create_app  # noqa: E402


REPORT_JSON = ROOT / "logs" / "erp_crud_completeness_audit.json"
REPORT_MD = ROOT / "logs" / "erp_crud_completeness_audit.md"


@dataclass(frozen=True)
class CrudTarget:
    module: str
    name: str
    page_type: str
    classification: str
    list_path: str | None
    new_paths: tuple[str, ...] = ()
    detail_patterns: tuple[str, ...] = ()
    edit_patterns: tuple[str, ...] = ()
    delete_patterns: tuple[str, ...] = ()
    action_patterns: tuple[str, ...] = ()
    require_create: bool = True
    require_edit: bool = True
    require_delete_or_lifecycle: bool = True


TARGETS = [
    CrudTarget("master", "material", "master_data", "live", "/material", ("/material/new",), ("/material/<int:product_id>", "/material/<int:id>"), ("/material/<int:product_id>/edit",), ("/material/<int:product_id>/delete",), ("/material/<int:product_id>/disable", "/material/<int:product_id>/enable")),
    CrudTarget("master", "customer", "master_data", "live", "/customer", ("/customer/new",), ("/customer/<int:customer_id>", "/customer/<int:id>"), ("/customer/<int:customer_id>/edit",), ("/customer/<int:customer_id>/delete",)),
    CrudTarget("master", "supplier", "master_data", "live", "/supplier", ("/supplier/new",), ("/supplier/<int:supplier_id>", "/supplier/<int:id>"), ("/supplier/<int:supplier_id>/edit",), ("/supplier/<int:supplier_id>/delete",)),
    CrudTarget("master", "warehouse", "master_data", "live", "/warehouse", ("/warehouse/new",), ("/warehouse/<int:warehouse_id>", "/warehouse/<int:id>"), ("/warehouse/<int:warehouse_id>/edit",), ("/warehouse/<int:warehouse_id>/delete",)),
    CrudTarget("master", "location", "master_data", "live", "/locations", ("/location/new", "/locations/new"), ("/locations/<int:id>",), ("/location/<int:location_id>/edit", "/locations/<int:location_id>/edit"), ("/location/<int:location_id>/delete",)),
    CrudTarget("master", "unit", "master_data", "live", "/unit", ("/unit/new", "/units/new"), ("/unit/<int:id>", "/units/<int:id>"), ("/unit/<int:unit_id>/edit", "/units/<int:unit_id>/edit"), ("/unit/<int:unit_id>/delete",)),
    CrudTarget("master", "department", "master_data", "live", "/department", ("/department/new", "/departments/new"), ("/department/<int:id>", "/departments/<int:id>"), ("/department/<int:department_id>/edit", "/departments/<int:department_id>/edit"), ("/department/<int:department_id>/delete",)),
    CrudTarget("master", "employee", "master_data", "live", "/employee", ("/employee/new", "/employees/new"), ("/employee/<int:id>", "/employees/<int:id>"), ("/employee/<int:employee_id>/edit", "/employees/<int:employee_id>/edit"), ("/employee/<int:employee_id>/delete",)),
    CrudTarget("master", "product_category", "master_data", "live", "/categories/product", ("/categories/<string:kind>/new",), ("/categories/product/<int:id>",), ("/categories/<string:kind>/<int:category_id>/edit",), (), (), True, True, False),
    CrudTarget("master", "customer_category", "master_data", "live", "/categories/customer", ("/categories/<string:kind>/new",), ("/categories/customer/<int:id>",), ("/categories/<string:kind>/<int:category_id>/edit",), (), (), True, True, False),
    CrudTarget("master", "supplier_category", "master_data", "live", "/categories/supplier", ("/categories/<string:kind>/new",), ("/categories/supplier/<int:id>",), ("/categories/<string:kind>/<int:category_id>/edit",), (), (), True, True, False),
    CrudTarget("master", "warehouse_category", "master_data", "live", "/categories/warehouse", ("/categories/<string:kind>/new",), ("/categories/warehouse/<int:id>",), ("/categories/<string:kind>/<int:category_id>/edit",), (), (), True, True, False),
    CrudTarget("master", "work_center", "master_data", "live", "/work-centers", (), ("/work-centers/<int:id>",), (), (), (), False, False, False),
    CrudTarget("master", "production_routing", "technical_master", "live", "/production-routings", ("/production-routings/new",), ("/production-routings/<int:id>",), ("/production-routings/<int:routing_id>/edit",), ("/production-routings/<int:routing_id>/delete",)),
    CrudTarget("master", "bom", "technical_master", "live", "/bom", ("/bom/new",), ("/bom/<path:bom_key>",), ("/bom/<path:bom_key>/edit",), (), ("/bom/<path:bom_key>/obsolete", "/bom/<path:bom_key>/freeze"), True, True, True),
    CrudTarget("purchase", "purchase_request", "document", "live", "/purchase_request", ("/purchase_request/new",), ("/purchase_request/<int:id>",), (), (), ("/purchase_request/<int:req_id>/submit", "/purchase_request/<int:req_id>/approve", "/purchase_request/<int:req_id>/void"), True, False, True),
    CrudTarget("purchase", "purchase_order", "document", "live", "/purchase-orders", ("/purchase_order/new",), ("/purchase_order/<int:order_id>", "/purchase-orders/<int:id>"), ("/purchase_order/<int:order_id>/edit",), (), ("/purchase_order/<int:order_id>/submit", "/purchase_order/<int:order_id>/audit", "/purchase_order/<int:order_id>/void")),
    CrudTarget("purchase", "purchase_receipt", "document", "live", "/purchase_receipts", ("/purchase_receipts/new",), ("/purchase_receipts/<int:id>",), (), (), ("/purchase_receipts/<int:receipt_id>/print",), True, False, True),
    CrudTarget("purchase", "purchase_return", "document", "live", "/purchase-returns", ("/purchase-returns/new",), ("/purchase-returns/<int:id>",), (), (), ("/purchase-returns/<int:return_id>/post", "/purchase-returns/<int:return_id>/cancel"), True, False, True),
    CrudTarget("purchase", "supplier_quote", "document", "live", "/supplier-quotes", ("/supplier-quotes/new",), ("/supplier-quotes/<int:id>",), (), (), ("/supplier-quotes/<int:quote_id>/<action>",), True, False, True),
    CrudTarget("sales", "quotation", "document", "live", "/quotations", ("/quotations/new",), ("/quotations/<int:id>",), ("/quotations/<int:quote_id>/edit",), (), ("/quotations/<int:quote_id>/submit", "/quotations/<int:quote_id>/audit", "/quotations/<int:quote_id>/void")),
    CrudTarget("sales", "sales_order", "document", "live", "/sales-orders", ("/sales/new",), ("/sales/<int:order_id>", "/sales-orders/<int:id>"), ("/sales/<int:order_id>/edit",), (), ("/sales/<int:order_id>/submit", "/sales/<int:order_id>/audit", "/sales/<int:order_id>/void")),
    CrudTarget("sales", "shipment", "document", "live", "/shipments", ("/shipments/new",), ("/shipments/<int:shipment_id>", "/shipments/<int:id>"), (), (), ("/shipments/<int:shipment_id>/<action>",), True, False, False),
    CrudTarget("sales", "sales_return", "document", "live", "/sales-returns", ("/sales-returns/new",), ("/sales-returns/<int:id>",), (), (), ("/sales-returns/<int:return_id>/post", "/sales-returns/<int:return_id>/cancel"), True, False, True),
    CrudTarget("inventory", "inventory_adjustment", "document", "live", "/adjustments", ("/adjustments/new",), ("/adjustments/<int:id>",), (), (), ("/adjustments/<int:adjustment_id>/post",), True, False, True),
    CrudTarget("inventory", "inventory_transfer", "document", "live", "/transfers", ("/transfers/new",), ("/transfers/<int:transfer_id>", "/transfers/<int:id>"), (), (), ("/transfers/<int:transfer_id>/post",), True, False, True),
    CrudTarget("inventory", "inventory_check", "document", "live", "/inventory_checks", ("/inventory_checks/new",), ("/inventory_checks/<int:check_id>",), (), (), ("/inventory_checks/<int:check_id>/post", "/inventory_checks/<int:check_id>/close", "/inventory_checks/<int:check_id>/cancel"), True, False, True),
    CrudTarget("inventory", "assembly_order", "document", "live", "/assembly-orders", ("/assembly-orders/new",), ("/assembly-orders/<int:order_id>", "/assembly-orders/<int:id>"), (), (), ("/assembly-orders/<int:order_id>/post",), True, False, True),
    CrudTarget("production", "work_order", "document", "live", "/work-orders", ("/work-orders/new",), ("/work-orders/<int:id>",), (), (), ("/work-orders/<int:work_order_id>/status", "/work-orders/<int:work_order_id>/issue-materials", "/work-orders/<int:work_order_id>/complete"), True, False, True),
    CrudTarget("production", "production_issue", "document", "live", "/production-issues", ("/production-issues/new",), ("/production-issues/<int:doc_id>",), (), (), ("/production-issues/<int:doc_id>/<action_name>",), True, False, False),
    CrudTarget("production", "production_return", "document", "live", "/production-returns", ("/production-returns/new",), ("/production-returns/<int:doc_id>",), (), (), ("/production-returns/<int:doc_id>/<action_name>",), True, False, False),
    CrudTarget("production", "production_completion", "document", "live", "/production-completions", ("/production-completions/new",), ("/production-completions/<int:doc_id>", "/production-completions/<int:id>"), (), (), ("/production-completions/<int:doc_id>/<action>",), True, False, False),
    CrudTarget("production", "operation_report", "document", "live", "/production/operation-reports", ("/production/operation-reports/new",), ("/production/operation-reports/<int:report_id>",), (), (), ("/production/operation-reports/<int:report_id>/<action_name>",), True, False, False),
    CrudTarget("production", "quality_inspection", "document", "live", "/production-enhance/quality-inspections", ("/production-enhance/quality-inspections/new",), ("/production-enhance/quality-inspections/<int:inspection_id>", "/production-enhance/quality-inspections/<int:id>"), (), (), ("/production-enhance/quality-inspections/<int:inspection_id>/<action>",), True, False, False),
    CrudTarget("subcontract", "subcontract_order", "document", "live", "/subcontract", ("/subcontract/new",), ("/subcontract/<int:id>",), (), (), ("/subcontract/<int:order_id>/<action>",), True, False, True),
    CrudTarget("subcontract", "subcontract_issue", "document", "live", "/subcontract_issue", ("/subcontract_issue/new",), ("/subcontract_issue/<int:id>",), (), (), ("/subcontract_issue/<int:issue_id>/<action>",), True, False, True),
    CrudTarget("subcontract", "subcontract_receive", "document", "live", "/subcontract_receive", ("/subcontract_receive/new",), ("/subcontract_receive/<int:id>",), (), (), ("/subcontract_receive/<int:receive_id>/<action>",), True, False, True),
    CrudTarget("service", "service_order", "document", "live", "/service-orders", ("/service-orders/new",), ("/service-orders/<int:id>",), (), (), ("/service-orders/<int:order_id>/dispatch", "/service-orders/<int:order_id>/handle", "/service-orders/<int:order_id>/close"), True, False, True),
    CrudTarget("service", "service_acceptance", "document", "live", "/service-acceptance", ("/service-acceptance/new",), ("/service-acceptance/<int:id>",), (), (), (), True, False, False),
    CrudTarget("service", "service_rma", "document", "live", "/service-rmas", ("/service-rmas/new",), ("/service-rmas/<int:id>",), (), (), ("/service-rmas/<int:rma_id>/diagnose", "/service-rmas/<int:rma_id>/recover", "/service-rmas/<int:rma_id>/close"), True, False, True),
    CrudTarget("finance", "sales_invoice", "document", "live", "/sales-invoices", ("/sales-invoices/new",), ("/sales-invoices/<int:invoice_id>", "/sales-invoices/<int:id>"), (), (), ("/sales-invoices/<int:invoice_id>/confirm", "/sales-invoices/<int:invoice_id>/void"), True, False, True),
    CrudTarget("finance", "purchase_invoice", "document", "live", "/purchase-invoices", ("/purchase-invoices/new",), ("/purchase-invoices/<int:invoice_id>", "/purchase-invoices/<int:id>"), (), (), ("/purchase-invoices/<int:invoice_id>/confirm", "/purchase-invoices/<int:invoice_id>/void"), True, False, True),
    CrudTarget("finance", "customer_receipt", "document", "live", "/customer-receipts", ("/customer-receipts/new",), ("/customer-receipts/<int:receipt_id>",), (), (), ("/customer-receipts/<int:receipt_id>/void",), True, False, True),
    CrudTarget("finance", "supplier_payment", "document", "live", "/payments", ("/payments/new",), ("/payments/<int:payment_id>",), (), (), ("/payments/<int:payment_id>/void",), True, False, True),
    CrudTarget("finance", "receivable", "query", "readonly", "/receivables", (), (), (), (), (), False, False, False),
    CrudTarget("finance", "payable", "query", "readonly", "/payables", (), (), (), (), (), False, False, False),
]


def route_map(app):
    return {rule.rule: {"endpoint": rule.endpoint, "methods": sorted(rule.methods - {"HEAD", "OPTIONS"})} for rule in app.url_map.iter_rules()}


def login(client):
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "audit"
        session["role"] = "admin"


def has_any(routes, patterns):
    return any(pattern in routes for pattern in patterns)


def page_status(client, path):
    if not path:
        return None
    response = client.get(path, follow_redirects=False)
    return response.status_code


def audit_target(target, routes, client):
    checks = {
        "list_route": bool(target.list_path and target.list_path in routes),
        "new_route": (not target.require_create) or has_any(routes, target.new_paths),
        "detail_route": target.page_type in {"query", "report"} or has_any(routes, target.detail_patterns),
        "edit_route": (not target.require_edit) or has_any(routes, target.edit_patterns),
        "delete_or_lifecycle": (not target.require_delete_or_lifecycle) or has_any(routes, target.delete_patterns) or has_any(routes, target.action_patterns),
    }
    status = page_status(client, target.list_path) if target.list_path else None
    new_statuses = {path: page_status(client, path) for path in target.new_paths if path in routes}
    checks["list_page_runtime"] = status in {200, 302}
    checks["new_page_runtime"] = (not target.require_create) or any(code in {200, 302} for code in new_statuses.values())
    missing = [name for name, ok in checks.items() if not ok]
    severity = "ok"
    if missing:
        severity = "error" if target.classification == "live" and target.page_type in {"document", "master_data", "technical_master"} else "warning"
    return {
        "module": target.module,
        "name": target.name,
        "page_type": target.page_type,
        "classification": target.classification,
        "list_path": target.list_path,
        "checks": checks,
        "missing": missing,
        "severity": severity,
        "list_status": status,
        "new_statuses": new_statuses,
    }


def write_reports(rows, routes):
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "target_count": len(rows),
        "ok": sum(1 for row in rows if row["severity"] == "ok"),
        "warnings": sum(1 for row in rows if row["severity"] == "warning"),
        "errors": sum(1 for row in rows if row["severity"] == "error"),
        "rows": rows,
    }
    REPORT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# ERP CRUD Completeness Audit",
        "",
        f"Generated at: {summary['generated_at']}",
        "",
        f"Targets: {summary['target_count']}; OK: {summary['ok']}; Warnings: {summary['warnings']}; Errors: {summary['errors']}",
        "",
        "Boundary: master data requires list/create/detail/edit/delete-or-disable; documents require list/create/detail and lifecycle actions; readonly query/report pages are not expected to create or edit records.",
        "",
        "## Findings",
        "",
        "| Severity | Module | Target | Page Type | List | Missing | Runtime |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        if row["severity"] == "ok":
            continue
        missing = ", ".join(row["missing"]) or "-"
        runtime = f"list={row['list_status']}; new={row['new_statuses'] or '-'}"
        lines.append(f"| {row['severity']} | {row['module']} | {row['name']} | {row['page_type']} | {row['list_path']} | {missing} | {runtime} |")
    if all(row["severity"] == "ok" for row in rows):
        lines.append("| ok | all | all targets | - | - | - | - |")
    lines.extend(["", "## Route Inventory", "", f"Flask route count: {len(routes)}"])
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def main():
    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    routes = route_map(app)
    with app.test_client() as client:
        login(client)
        rows = [audit_target(target, routes, client) for target in TARGETS]
    summary = write_reports(rows, routes)
    print(f"erp_crud_targets={summary['target_count']} ok={summary['ok']} warnings={summary['warnings']} errors={summary['errors']}")
    print(f"report={REPORT_MD}")
    for row in summary["rows"]:
        if row["severity"] != "ok":
            print(f"{row['severity']} | {row['module']} | {row['name']} | missing={','.join(row['missing'])}")
    if summary["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
