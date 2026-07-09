from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def main() -> int:
    findings: list[str] = []

    api_routes = _read_text(ROOT / "routes" / "api_routes.py")
    if "def require_api_login" not in api_routes or "authentication required" not in api_routes:
        findings.append("api login guard is missing")

    data_routes = _read_text(ROOT / "routes" / "data_route_registration.py")
    if "if has_document_list_config(path):" not in data_routes or "add_url = None" not in data_routes:
        findings.append("document list add_url suppression is missing")

    registry = _read_text(ROOT / "routes" / "registry.py")
    if "_safe_sql_identifier" not in registry:
        findings.append("registry SQL identifier guard is missing")
    if "ALLOWED_ATTACHMENT_EXTENSIONS" not in registry:
        findings.append("attachment upload extension allow-list is missing")
    for name in (
        "_post_inventory_adjustment_impl",
        "_post_inventory_transfer_impl",
        "_post_inventory_check_impl",
        "_post_inventory_assembly_document_impl",
        "_post_inventory_return_impl",
    ):
        if name not in registry:
            findings.append(f"inventory posting transaction wrapper is missing: {name}")
    if "_run_registry_transaction" not in registry:
        findings.append("registry transaction runner is missing")

    inventory_service = _read_text(ROOT / "services" / "inventory_service.py")
    if "_safe_identifier" not in inventory_service:
        findings.append("inventory service SQL identifier guard is missing")

    transaction_utils = ROOT / "services" / "transaction_utils.py"
    if not transaction_utils.exists():
        findings.append("transaction utility service is missing")
    else:
        transaction_text = _read_text(transaction_utils)
        if "cursor_db_helpers" not in transaction_text:
            findings.append("cursor-backed transaction helper is missing")

    attachment_routes = _read_text(ROOT / "routes" / "attachment_routes.py")
    if "send_file" not in attachment_routes or "as_attachment=True" not in attachment_routes:
        findings.append("secure attachment download route is missing")
    if "@login_required" not in attachment_routes:
        findings.append("attachment download route is not login protected")

    app_text = _read_text(ROOT / "app.py")
    if "register_attachment_routes" not in app_text:
        findings.append("attachment routes are not registered")

    finance_routes = _read_text(ROOT / "routes" / "finance_routes.py")
    if "_run_finance_funds_transaction" not in finance_routes:
        findings.append("finance receipt/payment transaction wrapper is missing")

    freeze_manifest = ROOT / "logs" / "module_freeze_manifest.csv"
    if not freeze_manifest.exists():
        findings.append("module freeze manifest is missing")
    else:
        with freeze_manifest.open("r", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        if len(rows) < 7:
            findings.append("module freeze manifest does not cover expected advanced modules")

    test_report = ROOT / "logs" / "erp_automatic_rectification_test_report.md"
    if not test_report.exists():
        findings.append("automatic rectification test report is missing")

    fk_report = ROOT / "logs" / "core_fk_validation_report.csv"
    if not fk_report.exists():
        findings.append("core FK validation report is missing")

    if findings:
        print("rectification_closure=failed")
        for finding in findings:
            print(f"finding | {finding}")
        return 1
    print("rectification_closure=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
