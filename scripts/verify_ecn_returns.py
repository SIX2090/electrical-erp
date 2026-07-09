"""Find ECN and sales-return documents directly from DB."""
import os
import sys
import re
sys.path.insert(0, r"c:\erp")
os.environ.setdefault("PG_PASSWORD", "admin")
import requests

BASE = "http://127.0.0.1:5000"


def login(session):
    from scripts.trial_audit_auth import prepare_trial_audit_passwords
    pwd = prepare_trial_audit_passwords(["admin"]).get("admin", "admin")
    r_get = session.get(f"{BASE}/login", timeout=10)
    csrf_match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r_get.text)
    csrf_token = csrf_match.group(1) if csrf_match else None
    data = {"username": "admin", "password": pwd}
    if csrf_token:
        data["csrf_token"] = csrf_token
    r = session.post(f"{BASE}/login", data=data, allow_redirects=False)
    return r.status_code in (302, 303)


def check_page(session, url):
    checks = {
        "menu_bar": [r"document-menu-bar", r"document_menu_bar"],
        "nav_config": [r"doc-nav-config"],
        "back": [r"返回列表", r"返回", r"bi-arrow-left"],
        "print": [r"打印", r"bi-printer", r"global-print"],
        "home": [r"返回首页", r"bi-house"],
    }
    try:
        r = session.get(f"{BASE}{url}", timeout=15, allow_redirects=True)
        if r.status_code != 200:
            return {"status": r.status_code, "error": f"HTTP {r.status_code}"}
        html = r.text
        result = {"status": 200}
        for key, patterns in checks.items():
            found = False
            for pat in patterns:
                if re.search(pat, html, re.IGNORECASE):
                    found = True
                    break
            result[key] = "OK" if found else "MISS"
        return result
    except Exception as e:
        return {"status": "error", "error": str(e)[:100]}


def main():
    session = requests.Session()
    if not login(session):
        print("FAIL: Cannot login")
        sys.exit(1)
    print("OK: Logged in as admin")

    # Query DB directly for ECN and sales_returns IDs
    from services.app_runtime import create_db_helpers
    from app import get_db_config
    import psycopg2

    db_config = get_db_config()
    conn = psycopg2.connect(**db_config)
    cur = conn.cursor()

    # Find ECN IDs
    try:
        cur.execute("SELECT id FROM bom_engineering_changes ORDER BY id DESC LIMIT 5")
        ecn_ids = [r[0] for r in cur.fetchall()]
        print(f"ECN IDs found: {ecn_ids}")
    except Exception as e:
        print(f"ECN query error: {e}")
        ecn_ids = []

    # Find sales_returns IDs
    try:
        cur.execute("SELECT id FROM sales_returns ORDER BY id DESC LIMIT 5")
        sr_ids = [r[0] for r in cur.fetchall()]
        print(f"sales_returns IDs found: {sr_ids}")
    except Exception as e:
        print(f"sales_returns query error: {e}")
        sr_ids = []

    # Find purchase_returns IDs
    try:
        cur.execute("SELECT id FROM purchase_returns ORDER BY id DESC LIMIT 5")
        pr_ids = [r[0] for r in cur.fetchall()]
        print(f"purchase_returns IDs found: {pr_ids}")
    except Exception as e:
        print(f"purchase_returns query error: {e}")
        pr_ids = []

    cur.close()
    conn.close()

    print()
    print("=== ECN Impact Pages ===")
    for ecn_id in ecn_ids[:2]:
        url = f"/ecn/{ecn_id}/impact"
        res = check_page(session, url)
        if res.get("status") != 200:
            print(f"  FAIL | ECN影响 {ecn_id} | {url} | {res.get('error', res.get('status'))}")
        else:
            required = ["menu_bar", "nav_config", "back"]
            missing = [k for k in required if res.get(k) == "MISS"]
            details = " | ".join(f"{k}={v}" for k, v in res.items() if k != "status")
            if missing:
                print(f"  WARN | ECN影响 {ecn_id} | {url} | missing:{','.join(missing)} | {details}")
            else:
                print(f"  OK   | ECN影响 {ecn_id} | {url} | {details}")

    print()
    print("=== Sales Return Detail Pages ===")
    for sr_id in sr_ids[:2]:
        url = f"/sales-returns/{sr_id}"
        res = check_page(session, url)
        if res.get("status") != 200:
            print(f"  FAIL | 销售退货 {sr_id} | {url} | {res.get('error', res.get('status'))}")
        else:
            required = ["menu_bar", "back"]
            missing = [k for k in required if res.get(k) == "MISS"]
            details = " | ".join(f"{k}={v}" for k, v in res.items() if k != "status")
            if missing:
                print(f"  WARN | 销售退货 {sr_id} | {url} | missing:{','.join(missing)} | {details}")
            else:
                print(f"  OK   | 销售退货 {sr_id} | {url} | {details}")

    print()
    print("=== Purchase Return Detail Pages ===")
    for pr_id in pr_ids[:2]:
        url = f"/purchase-returns/{pr_id}"
        res = check_page(session, url)
        if res.get("status") != 200:
            print(f"  FAIL | 采购退货 {pr_id} | {url} | {res.get('error', res.get('status'))}")
        else:
            required = ["menu_bar", "back"]
            missing = [k for k in required if res.get(k) == "MISS"]
            details = " | ".join(f"{k}={v}" for k, v in res.items() if k != "status")
            if missing:
                print(f"  WARN | 采购退货 {pr_id} | {url} | missing:{','.join(missing)} | {details}")
            else:
                print(f"  OK   | 采购退货 {pr_id} | {url} | {details}")


if __name__ == "__main__":
    main()
