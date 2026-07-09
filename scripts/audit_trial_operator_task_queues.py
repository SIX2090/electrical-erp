from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


QUEUE_CASES = {
    "pilot_admin": {
        "required": [
            "待技术确认",
            "待BOM/齐套",
            "待采购",
            "待到货",
            "待委外发料",
            "待委外收货",
            "待领料",
            "待调试/终检",
            "待发货",
            "待回款",
            "待付款",
            "待售后处理",
        ],
        "forbidden": [],
    },
    "pilot_sales": {
        "required": ["项目/机号台账", "待技术确认", "待发货"],
        "forbidden": ["待采购", "待到货", "待委外发料", "待委外收货", "待领料", "待调试/终检", "待回款", "待付款", "待售后处理"],
    },
    "pilot_purchase": {
        "required": ["MRP缺料", "委外跟进", "待技术确认", "待BOM/齐套", "待采购", "待到货", "待委外发料", "待委外收货"],
        "forbidden": ["待领料", "待调试/终检", "待发货", "待回款", "待付款", "待售后处理"],
    },
    "pilot_warehouse": {
        "required": ["待到货", "待委外发料", "待委外收货", "待领料", "待发货"],
        "forbidden": ["MRP缺料", "委外跟进", "待技术确认", "待BOM/齐套", "待采购", "待调试/终检", "待回款", "待付款", "待售后处理"],
    },
    "pilot_production": {
        "required": ["MRP缺料", "待技术确认", "待BOM/齐套", "待领料", "待调试/终检"],
        "forbidden": ["委外跟进", "待采购", "待到货", "待委外发料", "待委外收货", "待发货", "待回款", "待付款", "待售后处理"],
    },
    "pilot_service": {
        "required": ["待售后处理"],
        "forbidden": ["MRP缺料", "委外跟进", "待技术确认", "待BOM/齐套", "待采购", "待到货", "待委外发料", "待委外收货", "待领料", "待调试/终检", "待发货", "待回款", "待付款"],
    },
    "pilot_finance": {
        "required": ["待回款", "待付款"],
        "forbidden": ["MRP缺料", "委外跟进", "待技术确认", "待BOM/齐套", "待采购", "待到货", "待委外发料", "待委外收货", "待领料", "待调试/终检", "待发货", "待售后处理"],
    },
}

QUEUE_PAGE_MARKERS = {
    "/projects": ("项目号", "机号", "下一步", "责任"),
    "/sales-orders": ("项目/机号", "状态", "下一步"),
    "/engineering/kitting": ("项目", "物料", "下一步", "责任"),
    "/purchase_request": ("采购申请", "状态", "详情"),
    "/purchase_receipts": ("采购入库", "供应商", "状态"),
    "/subcontract_issue": ("委外发料", "下一步"),
    "/subcontract_receive": ("委外收货", "下一步"),
    "/requisition": ("待领", "下一步"),
    "/shipments": ("销售发货", "服务档案", "下一步"),
    "/receivables": ("应收", "状态", "详情"),
    "/payables": ("应付", "状态", "详情"),
    "/service-orders": ("服务", "状态", "详情"),
}


def load_passwords():
    from scripts.trial_audit_auth import prepare_trial_audit_passwords

    return prepare_trial_audit_passwords()

def main():
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "trial-operator-task-queues")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")

    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    passwords = load_passwords()
    checks = []

    for username, case in QUEUE_CASES.items():
        password = passwords.get(username)
        if not password:
            checks.append((username, "/", False, "missing password handoff"))
            continue
        client = app.test_client()
        login = client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
        checks.append((username, "login", login.status_code == 302, login.status_code))
        if login.status_code != 302:
            continue

        response = client.get("/")
        body = response.get_data(as_text=True)
        checks.append((username, "/", response.status_code == 200, response.status_code))
        for label in case["required"]:
            checks.append((username, f"queue visible {label}", label in body, "missing" if label not in body else "ok"))
        for label in case["forbidden"]:
            checks.append((username, f"queue hidden {label}", label not in body, "visible" if label in body else "ok"))

    admin_password = passwords.get("pilot_admin")
    if admin_password:
        client = app.test_client()
        login = client.post("/login", data={"username": "pilot_admin", "password": admin_password}, follow_redirects=False)
        checks.append(("pilot_admin", "queue-page login", login.status_code == 302, login.status_code))
        if login.status_code == 302:
            for path, markers in QUEUE_PAGE_MARKERS.items():
                response = client.get(path)
                body = response.get_data(as_text=True)
                checks.append(("pilot_admin", f"queue page {path}", response.status_code == 200, response.status_code))
                for marker in markers:
                    checks.append(("pilot_admin", f"{path} marker {marker}", marker in body, "missing" if marker not in body else "ok"))

    failures = [(user, name, detail) for user, name, ok, detail in checks if not ok]
    print("trial_operator_task_queue_audit=ok" if not failures else "trial_operator_task_queue_audit=failed")
    print(f"checked_items={len(checks)}")
    print(f"checked_users={len(QUEUE_CASES)}")
    for user, name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {user} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
