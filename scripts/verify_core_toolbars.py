"""Verify detail and core document page toolbars."""
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


def get_first_id(session, api_path):
    """Get first document ID via list page or API."""
    try:
        r = session.get(f"{BASE}{api_path}", timeout=10)
        if r.status_code == 200:
            # Try to find first detail link like /path/<id>
            matches = re.findall(r'href="(/[^"]+/\d+)"', r.text)
            if matches:
                return matches[0]
    except Exception:
        pass
    return None


def check_page(session, url, checks):
    """Fetch page and check for toolbar elements."""
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


CHECKS_DETAIL = {
    "menu_bar": [r"document-menu-bar", r"document_menu_bar"],
    "print": [r"打印", r"bi-printer", r"global-print"],
    "copy": [r"复制", r"global-copy"],
    "delete": [r"删除", r"global-delete"],
    "void": [r"作废", r"global-void"],
    "nav": [r"doc-nav-config", r"首张|上一张|下一张|末张", r"doc-nav"],
    "back": [r"返回列表", r"返回", r"bi-arrow-left"],
}

CHECKS_FORM = {
    "menu_bar": [r"document-menu-bar", r"document_menu_bar", r"operation-toolbar"],
    "save": [r"保存", r"bi-save", r"submit", r"global-submit"],
    "back": [r"返回列表", r"返回", r"bi-arrow-left", r"新增"],
    "status_pill": [r"doc_status", r"status.*pill", r"document-menu-bar__status"],
}

CHECKS_LIST = {
    "menu_bar": [r"document-menu-bar", r"document_menu_bar"],
    "add": [r"新增", r"bi-plus", r"/new"],
    "home": [r"返回首页", r"bi-house"],
    "paginate": [r"client-paginate"],
}


def main():
    session = requests.Session()
    if not login(session):
        print("FAIL: Cannot login")
        sys.exit(1)
    print("OK: Logged in as admin")
    print()

    # Detail pages - need to find actual document IDs
    print("=== Detail Pages ===")
    detail_sources = [
        ("/purchase_order", "采购订单", "purchase_orders"),
        ("/purchase_request", "采购申请", "purchase_requests"),
        ("/sales", "销售订单", "sales_orders"),
        ("/quotations", "报价单", "quotations"),
        ("/work-orders", "工单", "work_orders"),
        ("/adjustments", "库存调整", "inventory_adjustments"),
        ("/transfers", "库存调拨", "transfer_orders"),
        ("/inventory_checks", "库存盘点", "inventory_check_orders"),
        ("/production-issues", "生产领料", "pick_lists"),
        ("/production-completions", "生产完工", "production_completion_orders"),
        ("/subcontract", "委外订单", "subcontract_orders"),
        ("/finance/vouchers", "凭证", "vouchers"),
    ]

    total = 0
    passed = 0
    failed = 0

    for list_url, name, table in detail_sources:
        detail_path = get_first_id(session, list_url)
        if not detail_path:
            print(f"  SKIP | {name} | No document found to test")
            continue
        total += 1
        res = check_page(session, detail_path, CHECKS_DETAIL)
        if res.get("status") != 200:
            print(f"  FAIL | {name} | {detail_path} | {res.get('error', res.get('status'))}")
            failed += 1
            continue
        required = ["menu_bar", "print", "back"]
        missing = [k for k in required if res.get(k) == "MISS"]
        if missing:
            print(f"  WARN | {name} | {detail_path} | missing:{','.join(missing)}")
            failed += 1
        else:
            print(f"  OK   | {name} | {detail_path}")
            passed += 1
    print()

    # Form pages (new mode)
    print("=== Form Pages (New) ===")
    form_pages = [
        ("/purchase_order/new", "采购订单录入"),
        ("/purchase_request/new", "采购申请录入"),
        ("/sales/new", "销售订单录入"),
        ("/quotations/new", "报价单录入"),
        ("/work-orders/new", "工单录入"),
        ("/adjustments/new", "库存调整录入"),
        ("/transfers/new", "库存调拨录入"),
        ("/inventory_checks/new", "库存盘点录入"),
        ("/production-issues/new", "生产领料录入"),
        ("/production-completions/new", "生产完工录入"),
        ("/subcontract/new", "委外订单录入"),
        ("/finance/vouchers/new", "凭证录入"),
    ]
    for url, name in form_pages:
        total += 1
        res = check_page(session, url, CHECKS_FORM)
        if res.get("status") != 200:
            print(f"  FAIL | {name} | {url} | {res.get('error', res.get('status'))}")
            failed += 1
            continue
        required = ["menu_bar", "save", "back"]
        missing = [k for k in required if res.get(k) == "MISS"]
        if missing:
            print(f"  WARN | {name} | {url} | missing:{','.join(missing)}")
            failed += 1
        else:
            status_info = f", status_pill={'OK' if res.get('status_pill') == 'OK' else 'N/A(new)'}"
            print(f"  OK   | {name} | {url}{status_info}")
            passed += 1
    print()

    # List pages
    print("=== List Pages ===")
    list_pages = [
        ("/purchase_order", "采购订单列表"),
        ("/purchase_request", "采购申请列表"),
        ("/sales", "销售订单列表"),
        ("/quotations", "报价单列表"),
        ("/work-orders", "工单列表"),
        ("/adjustments", "库存调整列表"),
        ("/transfers", "库存调拨列表"),
        ("/inventory_checks", "库存盘点列表"),
        ("/production-issues", "生产领料列表"),
        ("/production-completions", "生产完工列表"),
        ("/subcontract", "委外订单列表"),
        ("/finance/vouchers", "凭证列表"),
        ("/finance/payables", "应付列表"),
        ("/finance/receivables", "应收列表"),
        ("/transactions", "库存流水列表"),
    ]
    for url, name in list_pages:
        total += 1
        res = check_page(session, url, CHECKS_LIST)
        if res.get("status") != 200:
            print(f"  FAIL | {name} | {url} | {res.get('error', res.get('status'))}")
            failed += 1
            continue
        required = ["home"]
        missing = [k for k in required if res.get(k) == "MISS"]
        if missing:
            print(f"  WARN | {name} | {url} | missing:{','.join(missing)}")
            failed += 1
        else:
            print(f"  OK   | {name} | {url}")
            passed += 1
    print()

    print(f"=== Summary ===")
    print(f"Total: {total}, Passed: {passed}, Failed: {failed}")


if __name__ == "__main__":
    main()
