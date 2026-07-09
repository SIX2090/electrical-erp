"""Verify 4 special detail pages modified for navigation."""
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


def get_first_id(session, list_url, detail_base=None):
    """Get first document ID via list page."""
    try:
        r = session.get(f"{BASE}{list_url}", timeout=10)
        if r.status_code == 200:
            base = detail_base or list_url
            # Match detail links like /path/<id>
            pattern = re.compile(rf'href="({re.escape(base)}/\d+)"')
            matches = pattern.findall(r.text)
            if matches:
                return matches[0]
            # Fallback: any /id pattern
            matches = re.findall(r'href="(/[^"]+/\d+)"', r.text)
            if matches:
                for m in matches:
                    if base in m:
                        return m
    except Exception as e:
        print(f"  Error fetching {list_url}: {e}")
    return None


def check_page(session, url):
    """Fetch page and check for toolbar elements."""
    checks = {
        "menu_bar": [r"document-menu-bar", r"document_menu_bar"],
        "nav_config": [r"doc-nav-config"],
        "nav_buttons": [r"首张|上一张|下一张|末张", r"doc-nav"],
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
    print()

    # 4 special detail pages
    print("=== Special Detail Pages (Navigation Modified) ===")
    special_pages = [
        # (list_url, name, detail_base, template_note)
        ("/work-orders", "工单快照", "/work-orders", "bom/work_order_snapshots.html - needs work_order_id"),
        ("/ecn", "ECN影响分析", "/ecn", "engineering/ecn_impact.html - needs ecn_id"),
        ("/assembly-orders", "库存组装单详情", "/assembly-orders", "inventory_assembly_detail.html"),
        ("/sales-returns", "销售退货单详情", "/sales-returns", "inventory_return_detail.html"),
    ]

    total = 0
    passed = 0
    failed = 0

    for list_url, name, detail_base, note in special_pages:
        total += 1
        # First try to find a detail link from list page
        detail_path = get_first_id(session, list_url, detail_base)
        if not detail_path:
            print(f"  SKIP | {name} | No document found in {list_url} ({note})")
            total -= 1
            continue

        res = check_page(session, detail_path)
        if res.get("status") != 200:
            print(f"  FAIL | {name} | {detail_path} | {res.get('error', res.get('status'))}")
            failed += 1
            continue

        # For these pages, check menu_bar and back at minimum
        required = ["menu_bar", "back"]
        missing = [k for k in required if res.get(k) == "MISS"]
        details = " | ".join(f"{k}={v}" for k, v in res.items() if k != "status")
        if missing:
            print(f"  WARN | {name} | {detail_path} | missing:{','.join(missing)} | {details}")
            failed += 1
        else:
            print(f"  OK   | {name} | {detail_path} | {details}")
            passed += 1

    # Also test work_order_snapshots and ecn_impact directly (they need special IDs)
    print()
    print("=== Direct Special Page Tests ===")

    # Work order snapshots: /work-orders/<id>/snapshots
    # Need a work order ID - try from work-orders list
    wo_detail = get_first_id(session, "/work-orders", "/work-orders")
    if wo_detail:
        # Extract ID
        m = re.search(r'/work-orders/(\d+)', wo_detail)
        if m:
            wo_id = m.group(1)
            snapshots_url = f"/work-orders/{wo_id}/snapshots"
            total += 1
            res = check_page(session, snapshots_url)
            if res.get("status") != 200:
                print(f"  FAIL | 工单BOM快照 | {snapshots_url} | {res.get('error', res.get('status'))}")
                failed += 1
            else:
                required = ["menu_bar", "nav_config", "back"]
                missing = [k for k in required if res.get(k) == "MISS"]
                details = " | ".join(f"{k}={v}" for k, v in res.items() if k != "status")
                if missing:
                    print(f"  WARN | 工单BOM快照 | {snapshots_url} | missing:{','.join(missing)} | {details}")
                    failed += 1
                else:
                    print(f"  OK   | 工单BOM快照 | {snapshots_url} | {details}")
                    passed += 1

    # ECN impact: /ecn/<id>/impact
    # Need an ECN ID - try from /ecn list
    ecn_detail = get_first_id(session, "/ecn", "/ecn")
    if ecn_detail:
        m = re.search(r'/ecn/(\d+)', ecn_detail)
        if m:
            ecn_id = m.group(1)
            impact_url = f"/ecn/{ecn_id}/impact"
            total += 1
            res = check_page(session, impact_url)
            if res.get("status") != 200:
                print(f"  FAIL | ECN影响分析 | {impact_url} | {res.get('error', res.get('status'))}")
                failed += 1
            else:
                required = ["menu_bar", "nav_config", "back"]
                missing = [k for k in required if res.get(k) == "MISS"]
                details = " | ".join(f"{k}={v}" for k, v in res.items() if k != "status")
                if missing:
                    print(f"  WARN | ECN影响分析 | {impact_url} | missing:{','.join(missing)} | {details}")
                    failed += 1
                else:
                    print(f"  OK   | ECN影响分析 | {impact_url} | {details}")
                    passed += 1
    else:
        print("  SKIP | ECN影响分析 | No ECN document found")

    print()
    print(f"=== Summary ===")
    print(f"Total: {total}, Passed: {passed}, Failed: {failed}")


if __name__ == "__main__":
    main()
