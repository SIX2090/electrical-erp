from html.parser import HTMLParser
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.pilot_permissions import default_groups_for_role, pilot_paths_for_groups


DELETED_WORKBENCH_ROOTS = {
    "/sales",
    "/master-data",
    "/purchase_order",
    "/inventory",
    "/finance",
    "/after-sale",
    "/system_settings",
}

SALES_PATHS = {
    "/sales",
    "/sales/new",
    "/sales-orders",
    "/shipments",
    "/quotations",
    "/sales-returns",
    "/sales-invoices",
    "/receivables",
    "/customer-receipts",
    "/sales/reports/pending",
    "/sales/reports/customer-ranking",
    "/sales/reports/execution",
}

TECH_PATHS = {
    "/engineering/technical-confirmations",
    "/engineering/technical-confirmations/new",
    "/engineering/drawings",
    "/bom/new",
    "/bom",
    "/production-routings",
    "/work-centers",
}

PURCHASE_PATHS = {
    "/purchase_request/new",
    "/purchase_request",
    "/purchase_order/new",
    "/purchase-orders",
    "/purchase_receipts",
    "/purchase-returns",
    "/subcontract",
    "/subcontract_issue",
    "/subcontract_receive",
    "/payables",
}

INVENTORY_PATHS = {
    "/inventory/detail",
    "/transactions",
    "/inventory/inbound",
    "/inventory/outbound",
    "/adjustments",
    "/assembly-orders",
    "/assembly-orders/new",
    "/disassembly-orders",
    "/disassembly-orders/new",
    "/transfers",
    "/transfers/new",
    "/inventory_checks",
    "/inventory_checks/new",
    "/batch/tracking",
}

WAREHOUSE_HIGH_RISK_PATHS = {
    "/adjustments/new",
}

PRODUCTION_PATHS = {
    "/work-orders",
    "/work-orders/new",
    "/engineering/kitting",
    "/production-enhance/mrp-requirements",
    "/procurement/suggestions",
    "/requisition",
    "/production-schedules",
    "/production-enhance/quality-inspections",
    "/production/reports/shortage",
    "/production/reports/work-order-detail",
}

SERVICE_PATHS = {
    "/service-cards",
    "/service-acceptance",
    "/service-orders",
    "/service-rmas",
    "/service/reports/service-detail",
    "/service/reports/cost",
}

FINANCE_PATHS = {
    "/receivables",
    "/payables",
    "/finance/period-close",
    "/finance/financial-statements",
    "/finance/reports/aging",
    "/finance/reports/balance",
}

MASTER_PATHS = {
    "/material",
    "/customer",
    "/supplier",
    "/warehouse",
    "/locations",
    "/unit",
    "/department",
    "/employees",
    "/categories/product",
}

SYSTEM_PATHS = {
    "/users",
    "/permissions/roles",
    "/operation_logs",
    "/system_settings/form",
    "/system/print-templates",
    "/system/database-backups",
    "/system/data-health",
}

ROLE_NAMES = {
    "pilot_admin": "admin",
    "pilot_sales": "sales",
    "pilot_purchase": "purchase",
    "pilot_warehouse": "warehouse",
    "pilot_production": "production",
    "pilot_service": "service",
    "pilot_finance": "finance",
}


def normalize_visible_path(path):
    return (path or "").split("?", 1)[0].rstrip("/") or "/"


def path_allowed(path, allowed_paths):
    path = normalize_visible_path(path)
    for allowed in allowed_paths:
        allowed = allowed.rstrip("/") or "/"
        if allowed == "/":
            if path == "/":
                return True
            continue
        if path == allowed or path.startswith(allowed + "/"):
            return True
    return False


class SidebarLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_sidebar = False
        self.sidebar_depth = 0
        self.links = []

    def handle_starttag(self, tag, attrs):
        attr_map = dict(attrs)
        if tag == "aside" and "sidebar" in attr_map.get("class", "").split():
            self.in_sidebar = True
            self.sidebar_depth = 1
            return
        if not self.in_sidebar:
            return
        self.sidebar_depth += 1
        if tag != "a":
            return
        href = (attr_map.get("href") or "").strip()
        if href.startswith("/"):
            self.links.append(href)

    def handle_endtag(self, tag):
        if not self.in_sidebar:
            return
        self.sidebar_depth -= 1
        if tag == "aside" and self.sidebar_depth <= 0:
            self.in_sidebar = False


def load_passwords():
    from scripts.trial_audit_auth import prepare_trial_audit_passwords

    return prepare_trial_audit_passwords()

def sidebar_links(body):
    parser = SidebarLinkParser()
    parser.feed(body)
    return sorted(set(parser.links))


def main():
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "trial-visible-navigation")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")

    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    passwords = load_passwords()
    checks = []

    for username, role_name in ROLE_NAMES.items():
        allowed_paths = pilot_paths_for_groups(default_groups_for_role(role_name))
        password = passwords.get(username)
        if not password:
            checks.append((username, "password handoff", False, "missing"))
            continue

        client = app.test_client()
        login = client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
        checks.append((username, "login", login.status_code == 302, login.status_code))
        if login.status_code != 302:
            continue

        response = client.get("/")
        body = response.get_data(as_text=True)
        links = sidebar_links(body)
        checks.append((username, "home visible", response.status_code == 200, response.status_code))
        checks.append((username, "sidebar has links", bool(links), len(links)))

        for path in links:
            clean_path = normalize_visible_path(path)
            checks.append((username, f"deleted workbench hidden {path}", clean_path not in DELETED_WORKBENCH_ROOTS, "hidden" if clean_path not in DELETED_WORKBENCH_ROOTS else "unexpected"))
            if clean_path in DELETED_WORKBENCH_ROOTS:
                continue
            is_allowed = path_allowed(path, allowed_paths)
            checks.append((username, f"visible nav allowed {path}", is_allowed, "allowed" if is_allowed else "unexpected"))
            if not is_allowed:
                continue
            target = client.get(path)
            checks.append((username, f"visible nav reachable {path}", target.status_code < 400, target.status_code))

    failures = [(user, name, detail) for user, name, ok, detail in checks if not ok]
    print("trial_visible_navigation_audit=ok" if not failures else "trial_visible_navigation_audit=failed")
    print(f"checked_items={len(checks)}")
    print(f"checked_users={len(ROLE_NAMES)}")
    for user, name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {user} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
