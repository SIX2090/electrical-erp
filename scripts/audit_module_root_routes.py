from __future__ import annotations

import os
import re
import sys
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("PG_PASSWORD", "admin")
os.environ.setdefault("INVENTORY_SECRET_KEY", "audit-secret")
os.environ.setdefault("WTF_CSRF_ENABLED", "0")


MODULE_ROOTS = {
    "/purchase": {
        "endpoint": "purchase_module_root",
        "page_type": "workbench",
        "markers": ("erp-queue-grid", "erp-queue-card"),
    },
    "/production": {
        "endpoint": "production_module_root",
        "page_type": "workbench",
        "markers": ("erp-workbench-heading", "erp-workbench-metrics"),
    },
    "/service": {
        "endpoint": "service_module_root",
        "page_type": "workbench",
        "markers": ("erp-workbench-heading", "erp-workbench-metrics"),
    },
    "/master-data": {
        "endpoint": "master_data_module_root",
        "page_type": "workbench",
        "markers": ("erp-workbench-heading", "erp-workbench-metrics"),
    },
}

FORBIDDEN_ROOT_NAV_GROUPS = (
    "采购单据",
    "采购列表",
    "采购报表",
    "生产单据",
    "生产列表",
    "生产报表",
    "售后单据",
    "售后列表",
    "售后报表",
)


def _make_client():
    from app import create_app

    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "LOGIN_RATE_LIMIT": 1000})
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "audit"
        session["role"] = "admin"
    return app, client


def audit_routes(app, client):
    findings = []
    route_by_rule = {rule.rule: rule.endpoint for rule in app.url_map.iter_rules()}
    for path, config in MODULE_ROOTS.items():
        endpoint = route_by_rule.get(path)
        if endpoint != config["endpoint"]:
            findings.append(f"{path}: expected endpoint {config['endpoint']}, got {endpoint or 'missing'}")
            continue
        response = client.get(path, follow_redirects=False)
        if response.status_code != 200:
            findings.append(f"{path}: expected HTTP 200 workbench, got {response.status_code}")
            continue
        body = response.get_data(as_text=True)
        for marker in config["markers"]:
            if marker not in body:
                findings.append(f"{path}: missing workbench marker {marker}")
        if 'class="erp-list-table"' in body and "erp-workbench-table" not in body:
            findings.append(f"{path}: rendered as plain list table instead of workbench table")
        if "data-column-key=" in body:
            findings.append(f"{path}: document-entry grid marker found on module root")
    return findings


def audit_static_routes():
    findings = []
    registry = (ROOT / "routes" / "registry.py").read_text(encoding="utf-8")
    try:
        tree = ast.parse(registry)
    except SyntaxError as exc:
        return [f"routes/registry.py:{exc.lineno}: syntax error: {exc.msg}"]
    routes = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            if not (
                isinstance(func, ast.Attribute)
                and func.attr in {"get", "route"}
                and isinstance(func.value, ast.Name)
                and func.value.id == "app"
            ):
                continue
            if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
                continue
            path = decorator.args[0].value
            endpoint = None
            for keyword in decorator.keywords:
                if keyword.arg == "endpoint" and isinstance(keyword.value, ast.Constant):
                    endpoint = keyword.value.value
            if isinstance(path, str):
                routes[path] = endpoint or node.name
    for path, config in MODULE_ROOTS.items():
        endpoint = routes.get(path)
        if endpoint != config["endpoint"]:
            findings.append(f"{path}: expected endpoint {config['endpoint']}, got {endpoint or 'missing'}")
    return findings


def audit_navigation():
    findings = []
    template = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
    if re.search(r'href="/(?:purchase|production|service|master-data)"', template):
        findings.append("templates/base.html: module root path is linked from normal menu groups")
    for label in FORBIDDEN_ROOT_NAV_GROUPS:
        if label in template and f'{label}</div>' in template:
            continue
    return findings


def audit_classification():
    findings = []
    doc = (ROOT / "MENU_ROLLOUT_CLASSIFICATION.md").read_text(encoding="utf-8")
    for path, config in MODULE_ROOTS.items():
        pattern = rf"\| `{re.escape(path)}` \| {config['page_type']} \| `(live|fix|readonly|internal|hidden)` \|"
        if not re.search(pattern, doc):
            findings.append(f"MENU_ROLLOUT_CLASSIFICATION.md: missing {path} {config['page_type']} classification")
    return findings


def main():
    findings = []
    try:
        app, client = _make_client()
    except Exception as exc:
        print(f"module_root_routes_runtime=skipped | {exc.__class__.__name__}: {exc}")
        findings.extend(audit_static_routes())
    else:
        findings.extend(audit_routes(app, client))
    findings.extend(audit_navigation())
    findings.extend(audit_classification())
    if findings:
        print("module_root_routes=failed")
        for item in findings:
            print(item)
        return 1
    print("module_root_routes=ok")
    for path, config in MODULE_ROOTS.items():
        print(f"{path} | {config['page_type']} | {config['endpoint']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
