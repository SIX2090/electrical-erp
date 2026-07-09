from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_password(username):
    from scripts.trial_audit_auth import prepare_trial_audit_passwords

    return prepare_trial_audit_passwords([username]).get(username, "")

def route_exists(app, rule_text, method="GET"):
    return any(rule.rule == rule_text and method in rule.methods for rule in app.url_map.iter_rules())


def main():
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "inventory-12-issue-closure")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")

    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    checks = []

    registry = (ROOT / "routes" / "registry.py").read_text(encoding="utf-8")
    report_data = (ROOT / "routes" / "module_report_data.py").read_text(encoding="utf-8")
    movement_tpl = (ROOT / "templates" / "inventory_movement_form.html").read_text(encoding="utf-8")
    doc_tpl = (ROOT / "templates" / "inventory_document_detail.html").read_text(encoding="utf-8")
    assembly_tpl = (ROOT / "templates" / "inventory_assembly_detail.html").read_text(encoding="utf-8")
    return_tpl = (ROOT / "templates" / "inventory_return_detail.html").read_text(encoding="utf-8")

    checks.append(("approval_flow_switch", "_inventory_approval_flow_enabled" in registry and "_inventory_initial_status" in registry, "status follows approval switch"))
    checks.append(("lot_serial_trace_fields", all(token in registry for token in ("lot_no", "serial_no", "_sync_batch_tracking")), "lot/serial tracked"))
    checks.append(("inout_summary_report", all(token in report_data for token in ("收发存汇总表", "opening_qty", "inbound_qty", "outbound_qty", "closing_qty")), "in/out/balance fields"))
    checks.append(("purchase_return_outbound", "采购退货出库" in registry and "purchase_return" in registry, "purchase return issues stock"))
    checks.append(("sales_return_inbound", "销售退货入库" in registry and "sales_return" in registry, "sales return receives stock"))
    checks.append(("cancelled_status", all(token in registry for token in ("已取消", "_cancel_inventory_adjustment", "_cancel_inventory_transfer", "_cancel_inventory_check", "_cancel_inventory_assembly_document", "_cancel_inventory_return")), "cancel routes implemented"))
    checks.append(("close_after_post", all(token in registry for token in ("_close_inventory_adjustment", "_close_inventory_transfer", "_close_inventory_check", "_close_inventory_assembly_document", "_close_inventory_return")), "close routes implemented"))
    checks.append(("detail_actions_visible", all(token in doc_tpl + assembly_tpl + return_tpl for token in ("确认过账", "取消单据", "关闭")), "post/cancel/close visible"))
    checks.append(("location_required", 'name="location_id" required' in movement_tpl, "movement location required"))
    checks.append(("pending_qty_reports", "purchase_pending_qty" in report_data and "sales_pending_qty" in report_data, "purchase pending and sales pending quantities"))
    checks.append(("ledger_balance_amount", "stock_amount" in report_data and "closing_amount" in report_data, "ledger amount fields"))
    checks.append(("stagnant_and_fund_report", "呆滞料分析" in report_data and "stagnant_days" in report_data and "库存资金占用表" in report_data, "stagnant/fund reports"))

    for rule in (
        "/adjustments/<int:adjustment_id>/cancel",
        "/transfers/<int:transfer_id>/cancel",
        "/inventory_checks/<int:check_id>/cancel",
        "/assembly-orders/<int:order_id>/cancel",
        "/disassembly-orders/<int:order_id>/cancel",
        "/sales-returns/<int:return_id>/cancel",
        "/purchase-returns/<int:return_id>/cancel",
        "/sales-returns/<int:return_id>/close",
        "/purchase-returns/<int:return_id>/close",
    ):
        checks.append((f"route:POST:{rule}", route_exists(app, rule, "POST"), "registered"))

    password = load_password("pilot_warehouse")
    checks.append(("pilot_warehouse_password", bool(password), "loaded" if password else "missing"))
    if password:
        client = app.test_client()
        login = client.post("/login", data={"username": "pilot_warehouse", "password": password}, follow_redirects=False)
        checks.append(("pilot_warehouse_login", login.status_code == 302, login.status_code))
        for path, markers in (
            ("/inventory/reports/inout-summary", ("收发存汇总表", "采购未入", "销售未出")),
            ("/inventory/reports/fund-occupation", ("库存资金占用表", "呆滞天数", "呆滞料分析")),
            ("/inventory/inbound?return_type=sales_return", ("出库退货入库", "库位")),
            ("/inventory/outbound?return_type=purchase_return", ("入库退货出库", "库位")),
        ):
            response = client.get(path)
            body = response.get_data(as_text=True)
            checks.append((f"GET {path}", response.status_code == 200, response.status_code))
            for marker in markers:
                checks.append((f"{path}:marker:{marker}", marker in body, "present" if marker in body else "missing"))

    clean_templates = movement_tpl + doc_tpl + assembly_tpl + return_tpl
    checks.append(("visible_inventory_templates_clean", chr(0xFFFD) not in clean_templates and "???" not in clean_templates, "no replacement markers"))

    failures = [(name, detail) for name, ok, detail in checks if not ok]
    print("inventory_12_issue_closure_audit=ok" if not failures else "inventory_12_issue_closure_audit=failed")
    print(f"checked_items={len(checks)}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
