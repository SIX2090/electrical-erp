from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


REQUIRED_MARKERS = (
    "用户权限",
    "功能与字段权限设置",
    "公共数据权限设置",
    "财务数据权限设置",
    "产品功能",
    "功能点名称",
    "pilot_admin",
    "pilot_sales",
    "pilot_purchase",
    "pilot_warehouse",
    "pilot_production",
    "pilot_service",
    "pilot_finance",
    "新增",
    "审核",
    "删除",
    "修改",
    "操作",
    "查看",
    "打印",
    "导出",
    "保存",
    "采购/委外",
    "库存",
    "销售订单",
    "采购入库",
    "生产工单",
    "售后服务单",
)

DIRTY_CODEPOINTS = {0xFFFD, 0x6434, 0x9417, 0x95C1}


def has_dirty_text(text):
    return "???" in text or any(ord(ch) in DIRTY_CODEPOINTS for ch in text)


def load_password(username):
    from scripts.trial_audit_auth import prepare_trial_audit_passwords

    return prepare_trial_audit_passwords([username]).get(username, "")

def safe_print_value(value):
    return str(value).encode("ascii", "backslashreplace").decode("ascii")


def main():
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "trial-role-permissions-page")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")

    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    checks = []

    admin_client = app.test_client()
    admin_login = admin_client.post(
        "/login",
        data={"username": "pilot_admin", "password": load_password("pilot_admin")},
        follow_redirects=False,
    )
    checks.append(("pilot_admin_login", admin_login.status_code == 302, admin_login.status_code))
    if admin_login.status_code == 302:
        response = admin_client.get("/permissions/roles")
        body = response.get_data(as_text=True)
        checks.append(("role_permissions_status", response.status_code == 200, response.status_code))
        checks.append(("role_permissions_not_empty_table", "暂无数据" not in body, "not empty" if "暂无数据" not in body else "empty"))
        for marker in REQUIRED_MARKERS:
            checks.append((f"required:{marker}", marker in body, "present" if marker in body else "missing"))
        checks.append(("dirty_markers", not has_dirty_text(body), "clean" if not has_dirty_text(body) else "dirty"))

        deny_response = admin_client.post(
            "/permissions/roles",
            data={
                "groups_sales": ["sales"],
                "actions_sales_sales_order": ["view", "create", "edit", "audit", "operate", "print", "export"],
                "actions_sales_receivable": ["view", "operate", "export"],
                "groups_purchase": ["tech", "purchase", "inventory"],
                "groups_warehouse": ["inventory"],
                "groups_production": ["tech", "inventory", "production"],
                "groups_service": ["service"],
                "groups_finance": ["finance"],
            },
            follow_redirects=False,
        )
        checks.append(("save_without_sales_service", deny_response.status_code in {302, 303}, deny_response.status_code))

        sales_after_save = app.test_client()
        sales_after_save.post(
            "/login",
            data={"username": "pilot_sales", "password": load_password("pilot_sales")},
            follow_redirects=False,
        )
        service_response = sales_after_save.get("/service-orders", follow_redirects=False)
        checks.append(("custom_permission_denies_sales_service", service_response.status_code == 403, service_response.status_code))

        restore_response = admin_client.post(
            "/permissions/roles",
            data={
                "groups_sales": ["sales", "service"],
                "actions_sales_sales_order": ["view", "create", "edit", "audit", "operate", "print", "export"],
                "actions_sales_shipment": ["view", "operate", "print", "export"],
                "actions_sales_receivable": ["view", "operate", "export"],
                "actions_sales_service_order": ["view", "operate"],
                "groups_purchase": ["tech", "purchase", "inventory"],
                "groups_warehouse": ["inventory"],
                "groups_production": ["tech", "inventory", "production"],
                "groups_service": ["service"],
                "groups_finance": ["finance"],
            },
            follow_redirects=False,
        )
        checks.append(("restore_default_permissions", restore_response.status_code in {302, 303}, restore_response.status_code))

    sales_client = app.test_client()
    sales_login = sales_client.post(
        "/login",
        data={"username": "pilot_sales", "password": load_password("pilot_sales")},
        follow_redirects=False,
    )
    checks.append(("pilot_sales_login", sales_login.status_code == 302, sales_login.status_code))
    if sales_login.status_code == 302:
        response = sales_client.get("/permissions/roles", follow_redirects=False)
        checks.append(("pilot_sales_forbidden", response.status_code == 403, response.status_code))

    failures = [(name, detail) for name, ok, detail in checks if not ok]
    print("trial_role_permissions_page_audit=ok" if not failures else "trial_role_permissions_page_audit=failed")
    print(f"checked_items={len(checks)}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {safe_print_value(name)} | {safe_print_value(detail)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
