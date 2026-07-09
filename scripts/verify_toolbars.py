"""Verify toolbar rendering on ERP pages by fetching each page and checking for toolbar elements."""
import re
import sys
import requests

BASE = "http://127.0.0.1:5000"

# Pages to verify, grouped by category
PAGES = {
    "finance_reports": [
        ("/finance/inventory-costing/cost-ledger", "库存成本明细账"),
        ("/finance/inventory-costing/reconciliation", "库存对账"),
        ("/finance/reports/project-cost-summary", "项目成本汇总"),
        ("/finance/project-cost/detail", "项目成本明细"),
        ("/finance/serial-cost/summary", "机号成本汇总"),
        ("/finance/serial-cost/variance", "机号成本差异"),
        ("/cost/variance", "成本差异"),
        ("/finance/reports/account-balance", "科目余额表"),
        ("/finance/reports/balance-sheet", "资产负债表"),
        ("/finance/reports/cash-flow-statement", "现金流量表"),
        ("/finance/reports/income-statement", "利润表"),
        ("/finance/trial-balance", "试算平衡表"),
        ("/finance/period-closing/check", "期末结账检查"),
        ("/finance/period-closing/history", "结账历史"),
        ("/finance/period-closing/", "期末结账"),
        ("/finance/reports/purchase-invoice-reconciliation", "采购发票对账"),
        ("/finance/reports/sales-invoice-reconciliation", "销售发票对账"),
        ("/finance/reports/purchase-three-way-match", "采购三单匹配"),
        ("/finance/reports/sales-three-way-match", "销售三单匹配"),
        ("/finance/reports/uninvoiced-sales", "未开票销售"),
        ("/finance/reports/unreceived-purchase-invoice", "未到票采购"),
    ],
    "forms": [
        ("/finance/bank-statements/import", "银行流水导入"),
        ("/finance/vouchers/generate-batch", "凭证批量生成"),
        ("/security/data-permissions/new", "数据权限规则"),
        ("/security/export-approvals/new", "导出审批"),
    ],
    "lists": [
        ("/bom/substitute-list", "BOM替代料"),
        ("/bom/versions", "BOM版本"),
        ("/cost", "成本首页"),
        ("/cost/reconciliation", "成本对账"),
        ("/cost/runs", "成本运行"),
        ("/ecn/action-tasks", "ECN执行任务"),
        ("/ecn/impact-tasks", "ECN影响任务"),
        ("/finance/fx-adjustments", "汇率调整"),
        ("/finance/fx-rates", "汇率"),
        ("/security/data-access-logs", "访问日志"),
        ("/security/data-permissions", "数据权限"),
        ("/security/export-approvals", "导出审批"),
        ("/security/locked-accounts", "锁定账户"),
        ("/security/sessions", "会话管理"),
        ("/notifications", "通知"),
        ("/mrp", "MRP首页"),
        ("/mrp/kitting", "MRP齐套"),
        ("/mrp/runs", "MRP运行"),
        ("/mrp/suggestions", "MRP建议"),
    ],
}

# Toolbar elements to check
CHECKS = {
    "back": [r"history\.back", r"返回", r"bi-arrow-left"],
    "export": [r"导出", r"export", r"bi-download"],
    "print": [r"打印", r"print", r"bi-printer"],
    "menu_bar": [r"document-menu-bar", r"document_menu_bar"],
    "home": [r"返回首页", r"bi-house", r"href=[\"']/[\"']"],
}


def login(session):
    """Login as admin. Reset password first via trial audit auth."""
    import os
    import re
    os.environ.setdefault("PG_PASSWORD", "admin")
    try:
        from scripts.trial_audit_auth import prepare_trial_audit_passwords
        pwd = prepare_trial_audit_passwords(["admin"]).get("admin", "admin")
    except Exception:
        pwd = "admin"
    # GET login page to obtain CSRF token
    r_get = session.get(f"{BASE}/login", timeout=10)
    csrf_match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r_get.text)
    csrf_token = csrf_match.group(1) if csrf_match else None
    data = {"username": "admin", "password": pwd}
    if csrf_token:
        data["csrf_token"] = csrf_token
    r = session.post(f"{BASE}/login", data=data, allow_redirects=False)
    if r.status_code in (302, 303):
        return True, pwd
    return False, None


def check_page(session, url):
    """Fetch page and check toolbar elements."""
    try:
        r = session.get(f"{BASE}{url}", timeout=15, allow_redirects=True)
        if r.status_code != 200:
            return {"status": r.status_code, "error": f"HTTP {r.status_code}"}
        html = r.text
        result = {"status": 200}
        for key, patterns in CHECKS.items():
            found = False
            for pat in patterns:
                if re.search(pat, html, re.IGNORECASE):
                    found = True
                    break
            result[key] = "OK" if found else "MISS"
        # Check for stub export
        if "开发中" in html or "alert('Excel" in html:
            result["stub_export"] = "STUB"
        else:
            result["stub_export"] = "OK"
        return result
    except requests.exceptions.Timeout:
        return {"status": "timeout", "error": "Request timed out"}
    except Exception as e:
        return {"status": "error", "error": str(e)[:100]}


def main():
    session = requests.Session()
    ok, pwd = login(session)
    if not ok:
        print("FAIL: Cannot login as admin")
        sys.exit(1)
    print(f"OK: Logged in as admin (password={pwd})")
    print()

    total = 0
    passed = 0
    failed = 0

    for category, pages in PAGES.items():
        print(f"=== {category} ===")
        for url, name in pages:
            total += 1
            res = check_page(session, url)
            if res.get("status") != 200:
                print(f"  FAIL | {name} | {url} | {res.get('error', res.get('status'))}")
                failed += 1
                continue

            # Determine required checks based on category
            if category == "finance_reports":
                required = ["back", "export", "print"]
            elif category == "forms":
                required = ["menu_bar"]
            elif category == "lists":
                required = ["home"]
            else:
                required = []

            missing = [k for k in required if res.get(k) == "MISS"]
            stub = res.get("stub_export") == "STUB"

            if missing or stub:
                issues = []
                if missing:
                    issues.append(f"missing:{','.join(missing)}")
                if stub:
                    issues.append("stub_export")
                print(f"  WARN | {name} | {url} | {';'.join(issues)}")
                failed += 1
            else:
                print(f"  OK   | {name} | {url}")
                passed += 1
        print()

    print(f"=== Summary ===")
    print(f"Total: {total}, Passed: {passed}, Failed: {failed}")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
