from pathlib import Path
import os
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


LIST_PATHS = (
    "/adjustments",
    "/transfers",
    "/inventory_checks",
    "/assembly-orders",
    "/disassembly-orders",
    "/sales-returns",
    "/purchase-returns",
)

NEW_PATHS = (
    "/adjustments/new",
    "/transfers/new",
    "/inventory_checks/new",
    "/assembly-orders/new",
    "/disassembly-orders/new",
)

DETAIL_ROUTE_CASES = (
    ("/adjustments/<int:id>", "GET"),
    ("/transfers/<int:transfer_id>", "GET"),
    ("/inventory_checks/<int:check_id>", "GET"),
    ("/assembly-orders/<int:order_id>", "GET"),
    ("/disassembly-orders/<int:order_id>", "GET"),
    ("/sales-returns/<int:id>", "GET"),
    ("/purchase-returns/<int:id>", "GET"),
)

ACTION_ROUTE_CASES = (
    ("/adjustments/<int:adjustment_id>/post", "POST"),
    ("/adjustments/<int:adjustment_id>/close", "POST"),
    ("/adjustments/<int:adjustment_id>/cancel", "POST"),
    ("/adjustments/<int:adjustment_id>/print", "GET"),
    ("/transfers/<int:transfer_id>/post", "POST"),
    ("/transfers/<int:transfer_id>/close", "POST"),
    ("/transfers/<int:transfer_id>/cancel", "POST"),
    ("/transfers/<int:transfer_id>/print", "GET"),
    ("/inventory_checks/<int:check_id>/post", "POST"),
    ("/inventory_checks/<int:check_id>/close", "POST"),
    ("/inventory_checks/<int:check_id>/cancel", "POST"),
    ("/inventory_checks/<int:check_id>/print", "GET"),
    ("/assembly-orders/<int:order_id>/post", "POST"),
    ("/assembly-orders/<int:order_id>/close", "POST"),
    ("/assembly-orders/<int:order_id>/cancel", "POST"),
    ("/disassembly-orders/<int:order_id>/post", "POST"),
    ("/disassembly-orders/<int:order_id>/close", "POST"),
    ("/disassembly-orders/<int:order_id>/cancel", "POST"),
    ("/sales-returns/<int:return_id>/post", "POST"),
    ("/sales-returns/<int:return_id>/close", "POST"),
    ("/sales-returns/<int:return_id>/cancel", "POST"),
    ("/purchase-returns/<int:return_id>/post", "POST"),
    ("/purchase-returns/<int:return_id>/close", "POST"),
    ("/purchase-returns/<int:return_id>/cancel", "POST"),
)

DETAIL_TEMPLATES = (
    "templates/inventory_document_detail.html",
    "templates/inventory_assembly_detail.html",
    "templates/inventory_return_detail.html",
)

LIST_TEMPLATES = (
    "templates/simple_list.html",
)

NAV_MARKERS = {
    "first": ('data-doc-nav="first"', "first-doc", "\u9996\u5f20"),
    "previous": ('data-doc-nav="previous"', "previous-doc", "\u4e0a\u4e00\u5f20"),
    "next": ('data-doc-nav="next"', "next-doc", "\u4e0b\u4e00\u5f20"),
    "last": ('data-doc-nav="last"', "last-doc", "\u672b\u5f20"),
}

TRACE_MARKERS = {
    "upstream": ('data-doc-trace="upstream"', "upstream-doc", "\u4e0a\u67e5"),
    "downstream": ('data-doc-trace="downstream"', "downstream-doc", "\u4e0b\u67e5"),
    "related": ('data-doc-trace="related"', "related-doc", "\u5173\u8054\u67e5\u8be2"),
}

LIST_BULK_MARKERS = {
    "bulk_post": ('data-bulk-action="post"', '"value": "post"', "bulk-post", '\u6279\u91cf\u786e\u8ba4\u8fc7\u8d26'),
    "bulk_close": ('data-bulk-action="close"', '"value": "close"', "bulk-close", "\u6279\u91cf\u5173\u95ed"),
    "bulk_cancel": ('data-bulk-action="cancel"', '"value": "cancel"', "bulk-cancel", "\u6279\u91cf\u53d6\u6d88"),
    "bulk_print": ('data-bulk-action="print"', '"value": "print"', "bulk-print", "\u6279\u91cf\u6253\u5370"),
}


def load_password(username):
    from scripts.trial_audit_auth import prepare_trial_audit_passwords

    return prepare_trial_audit_passwords([username]).get(username, "")

def route_exists(app, rule_text, method):
    return any(rule.rule == rule_text and method in rule.methods for rule in app.url_map.iter_rules())


def read_text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def has_any_marker(text, markers):
    return any(marker in text for marker in markers)


def ids_from_list_html(html, base_path):
    pattern = re.compile(r'href="' + re.escape(base_path.rstrip("/")) + r"/(\d+)")
    seen = []
    for match in pattern.finditer(html):
        value = match.group(1)
        if value not in seen:
            seen.append(value)
    return seen


def main():
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "inventory-operation-gap-audit")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")

    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    checks = []

    for rule, method in DETAIL_ROUTE_CASES + ACTION_ROUTE_CASES:
        checks.append((f"route:{method}:{rule}", route_exists(app, rule, method), "registered"))

    detail_text_by_path = {}
    for template_path in DETAIL_TEMPLATES:
        text = read_text(template_path)
        detail_text_by_path[template_path] = text
        for name, markers in NAV_MARKERS.items():
            checks.append((f"{template_path}:nav:{name}", has_any_marker(text, markers), "document navigation marker"))
        for name, markers in TRACE_MARKERS.items():
            checks.append((f"{template_path}:trace:{name}", has_any_marker(text, markers), "document trace marker"))
        checks.append((f"{template_path}:post_action", "/post" in text or "post_url" in text, "post action"))
        checks.append((f"{template_path}:close_action", "/close" in text, "close action"))
        checks.append((f"{template_path}:cancel_action", "/cancel" in text, "cancel action"))

    list_text = "\n".join(read_text(path) for path in LIST_TEMPLATES)
    config_text = read_text("routes/special_list_routes.py")
    static_bulk_text = list_text + config_text
    for name, markers in LIST_BULK_MARKERS.items():
        checks.append((f"list:marker:{name}", has_any_marker(static_bulk_text, markers), "bulk list action marker"))
    checks.append(("list:row_selection", 'name="ids"' in list_text or 'data-row-select' in list_text, "row selection marker"))

    username = "pilot_admin"
    password = load_password(username)
    checks.append((f"{username}_password", bool(password), "loaded" if password else "missing"))
    if password:
        client = app.test_client()
        login = client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
        checks.append((f"{username}_login", login.status_code == 302, login.status_code))
        if login.status_code == 302:
            discovered_detail_paths = []
            for path in LIST_PATHS + NEW_PATHS:
                response = client.get(path, follow_redirects=False)
                body = response.get_data(as_text=True)
                checks.append((f"GET {path}", response.status_code == 200, response.status_code))
                if path in LIST_PATHS and response.status_code == 200:
                    for row_id in ids_from_list_html(body, path)[:1]:
                        discovered_detail_paths.append(f"{path.rstrip('/')}/{row_id}")
                    for name, markers in LIST_BULK_MARKERS.items():
                        checks.append((f"{path}:bulk:{name}", has_any_marker(body, markers), "bulk action visible"))
                    row_selection_ready = (
                        'name="ids"' in body
                        or 'data-row-select' in body
                        or ('id="bulkActionForm"' in body and "\u6682\u65e0\u6570\u636e" in body)
                    )
                    checks.append((f"{path}:row_selection", row_selection_ready, "row selection visible"))

            for detail_path in discovered_detail_paths:
                response = client.get(detail_path, follow_redirects=False)
                body = response.get_data(as_text=True)
                checks.append((f"GET {detail_path}", response.status_code == 200, response.status_code))
                if response.status_code == 200:
                    for name, markers in NAV_MARKERS.items():
                        checks.append((f"{detail_path}:nav:{name}", has_any_marker(body, markers), "document navigation visible"))
                    for name, markers in TRACE_MARKERS.items():
                        checks.append((f"{detail_path}:trace:{name}", has_any_marker(body, markers), "document trace visible"))

    clean_text = list_text + "\n".join(detail_text_by_path.values())
    checks.append(("audit_scope_templates_no_replacement_char", chr(0xFFFD) not in clean_text, "no replacement char"))

    failures = [(name, detail) for name, ok, detail in checks if not ok]
    print("inventory_operation_gap_audit=ok" if not failures else "inventory_operation_gap_audit=failed")
    print(f"checked_items={len(checks)}")
    print("business_data_created=no")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
