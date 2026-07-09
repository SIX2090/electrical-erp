from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


EXPECTED_MENUS = {
    "pilot_admin": {
        "required": ["工作台", "销售", "采购", "工程/BOM", "生产", "库存", "委外", "售后", "财务/成本", "基础资料", "系统"],
        "forbidden": [],
    },
    "pilot_sales": {
        "required": ["工作台", "销售", "售后"],
        "forbidden": ["采购", "工程/BOM", "生产", "库存", "委外", "财务/成本", "基础资料", "系统"],
    },
    "pilot_purchase": {
        "required": ["工作台", "工程/BOM", "采购", "委外"],
        "forbidden": ["销售", "生产", "库存", "售后", "财务/成本", "基础资料", "系统"],
    },
    "pilot_warehouse": {
        "required": ["工作台", "库存"],
        "forbidden": ["销售", "工程/BOM", "采购", "生产", "委外", "售后", "财务/成本", "基础资料", "系统"],
    },
    "pilot_production": {
        "required": ["工作台", "工程/BOM", "生产"],
        "forbidden": ["销售", "采购", "库存", "委外", "售后", "财务/成本", "基础资料", "系统"],
    },
    "pilot_service": {
        "required": ["工作台", "售后"],
        "forbidden": ["销售", "工程/BOM", "采购", "库存", "生产", "委外", "财务/成本", "基础资料", "系统"],
    },
    "pilot_finance": {
        "required": ["工作台", "财务/成本"],
        "forbidden": ["销售", "工程/BOM", "采购", "库存", "生产", "委外", "售后", "基础资料", "系统"],
    },
}


def load_passwords():
    from scripts.trial_audit_auth import prepare_trial_audit_passwords

    return prepare_trial_audit_passwords()

def main():
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("PG_PASSWORD", "admin")
    from app import create_app

    passwords = load_passwords()
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "LOGIN_RATE_LIMIT": 1000})
    failures = []
    with app.test_client() as client:
        for username, checks in EXPECTED_MENUS.items():
            password = passwords.get(username)
            if not password:
                failures.append(f"{username}: missing password handoff")
                continue
            client.get("/logout")
            response = client.post("/login", data={"username": username, "password": password}, follow_redirects=True)
            body = response.get_data(as_text=True)
            if response.status_code != 200:
                failures.append(f"{username}: login returned {response.status_code}")
                continue
            if '<aside class="sidebar">' in body and '</aside>' in body:
                body = body.split('<aside class="sidebar">', 1)[1].split("</aside>", 1)[0]
            menu_parent_text = "\n".join(
                part.split("</div>", 1)[0]
                for part in body.split('<div class="menu-parent">')[1:]
            )
            for label in checks["required"]:
                if label not in menu_parent_text:
                    failures.append(f"{username}: required menu missing: {label}")
            for label in checks["forbidden"]:
                if label in menu_parent_text:
                    failures.append(f"{username}: forbidden menu visible: {label}")

    if failures:
        print("trial_menu_audit=failed")
        for item in failures:
            print(item)
        return 1
    print("trial_menu_audit=ok")
    print(f"checked_users={len(EXPECTED_MENUS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
