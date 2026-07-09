from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_password(username):
    from scripts.trial_audit_auth import prepare_trial_audit_passwords

    return prepare_trial_audit_passwords([username]).get(username, "")

def route_exists(app, rule_text, method="GET"):
    for rule in app.url_map.iter_rules():
        if rule.rule == rule_text and method in rule.methods:
            return True
    return False


def main():
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "inventory-return-report-audit")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")

    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    checks = []

    for rule, method in (
        ("/sales-returns/<int:return_id>/post", "POST"),
        ("/purchase-returns/<int:return_id>/post", "POST"),
        ("/inventory/reports/ledger", "GET"),
        ("/inventory/reports/inout-summary", "GET"),
        ("/inventory/reports/batch-trace", "GET"),
    ):
        checks.append((f"route:{method}:{rule}", route_exists(app, rule, method), "registered"))

    password = load_password("pilot_warehouse")
    checks.append(("pilot_warehouse_password", bool(password), "loaded" if password else "missing"))
    if password:
        client = app.test_client()
        login = client.post("/login", data={"username": "pilot_warehouse", "password": password}, follow_redirects=False)
        checks.append(("pilot_warehouse_login", login.status_code == 302, login.status_code))
        page_cases = [
            ("/inventory/inbound?return_type=sales_return", ("出库退货入库", "库位", "保存并过账")),
            ("/inventory/outbound?return_type=purchase_return", ("入库退货出库", "库位", "保存并过账")),
            ("/inventory/reports/ledger", ("标准库存明细账", "入库", "出库", "结存影响")),
            ("/inventory/reports/inout-summary", ("收发存汇总表", "期初", "入库", "出库", "期末")),
            ("/inventory/reports/batch-trace", ("批次追溯报表", "批号", "机号", "流水")),
        ]
        for path, markers in page_cases:
            response = client.get(path)
            body = response.get_data(as_text=True)
            checks.append((f"GET {path}", response.status_code == 200, response.status_code))
            for marker in markers:
                checks.append((f"{path}:marker:{marker}", marker in body, "present" if marker in body else "missing"))

    template_text = (ROOT / "templates" / "inventory_movement_form.html").read_text(encoding="utf-8")
    checks.append(("location_select_required", 'name="location_id" required' in template_text, "required attribute"))
    checks.append(("movement_template_clean_chinese", chr(0xFFFD) not in template_text and "???" not in template_text, "no replacement markers"))

    failures = [(name, detail) for name, ok, detail in checks if not ok]
    print("inventory_return_and_reports_audit=ok" if not failures else "inventory_return_and_reports_audit=failed")
    print(f"checked_items={len(checks)}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
