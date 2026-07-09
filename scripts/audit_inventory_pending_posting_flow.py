from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


PENDING_LABEL = "保存待过账"

NEW_PAGE_CASES = [
    ("adjustment_new", "/adjustments/new"),
    ("transfer_new", "/transfers/new"),
    ("assembly_new", "/assembly-orders/new"),
    ("disassembly_new", "/disassembly-orders/new"),
]

POST_ROUTE_CASES = [
    (
        "adjustment_post",
        "/adjustments/<int:adjustment_id>/post",
        ROOT / "templates" / "inventory_document_detail.html",
        ["/adjustments/", "/post"],
    ),
    (
        "transfer_post",
        "/transfers/<int:transfer_id>/post",
        ROOT / "templates" / "inventory_document_detail.html",
        ["/transfers/", "/post"],
    ),
    (
        "assembly_post",
        "/assembly-orders/<int:order_id>/post",
        ROOT / "templates" / "inventory_assembly_detail.html",
        ["meta.detail_base", "/post"],
    ),
    (
        "disassembly_post",
        "/disassembly-orders/<int:order_id>/post",
        ROOT / "templates" / "inventory_assembly_detail.html",
        ["meta.detail_base", "/post"],
    ),
]


def load_password(username):
    from scripts.trial_audit_auth import prepare_trial_audit_passwords

    return prepare_trial_audit_passwords([username]).get(username, "")

def route_exists(app, rule_text):
    for rule in app.url_map.iter_rules():
        if rule.rule == rule_text and "POST" in rule.methods:
            return True
    return False


def template_has_post_hook(template_path, tokens):
    if not template_path.exists():
        return False, "missing template"
    text = template_path.read_text(encoding="utf-8")
    missing = [token for token in tokens if token not in text]
    if missing:
        return False, f"missing template tokens: {', '.join(missing)}"
    return True, "template hook found"


def main():
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "inventory-pending-posting-flow-audit")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")

    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    checks = []

    password = load_password("pilot_warehouse")
    checks.append(("pilot_warehouse_password", bool(password), "loaded" if password else "missing"))
    if not password:
        print("inventory_pending_posting_flow_audit=failed")
        print(f"checked_items={len(checks)}")
        for name, ok, detail in checks:
            print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
        return 1

    client = app.test_client()
    login = client.post(
        "/login",
        data={"username": "pilot_warehouse", "password": password},
        follow_redirects=False,
    )
    checks.append(("pilot_warehouse_login", login.status_code == 302, login.status_code))

    if login.status_code == 302:
        for name, path in NEW_PAGE_CASES:
            response = client.get(path, follow_redirects=False)
            text = response.get_data(as_text=True)
            checks.append((f"{name}:GET {path}", response.status_code == 200, response.status_code))
            checks.append((f"{name}:pending_label", PENDING_LABEL in text, PENDING_LABEL if PENDING_LABEL in text else "missing"))

    for name, rule_text, template_path, template_tokens in POST_ROUTE_CASES:
        has_route = route_exists(app, rule_text)
        has_template_hook, template_detail = template_has_post_hook(template_path, template_tokens)
        checks.append((f"{name}:post_route_or_template", has_route or has_template_hook, f"route={has_route}; {template_detail}"))

    failures = [(name, detail) for name, ok, detail in checks if not ok]
    print("inventory_pending_posting_flow_audit=ok" if not failures else "inventory_pending_posting_flow_audit=failed")
    print(f"checked_items={len(checks)}")
    print("business_data_created=no")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
