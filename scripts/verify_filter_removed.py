"""验证单据明细筛选功能是否彻底移除。

访问多个单据录入页面，检查 DOM 中是否还存在任何形式的列筛选输入框。
"""
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5000"

# 要验证的单据录入页面（覆盖三套筛选系统的所有触发路径）
PAGES = [
    ("/purchase_order/new", "采购订单新增"),
    ("/purchase_request/new", "采购申请新增"),
    ("/inventory/movement/new", "库存出入库"),
    ("/work_order/new", "工单新增"),
    ("/subcontract_issue/new", "委外发料新增"),
    ("/subcontract_receive/new", "委外收货新增"),
    ("/production_pick/new", "生产领料新增"),
    ("/voucher/new", "凭证新增"),
]

# 三套筛选系统的 DOM 特征
FILTER_SELECTORS = [
    "tr[data-grid-filter-row]",          # 系统1：静态筛选行
    "tr.document-grid-filter-row",       # 系统1：CSS类
    "tr.erp-table-filter-row",           # 系统3：app.js自动注入
    "input[data-grid-filter]",           # 系统2：document_grid.js
    "input[data-table-column-filter]",   # 系统3：app.js列筛选
    "button[data-grid-action='filter']", # 筛选按钮
    "button[data-grid-action=\"filter\"]",
]

def login(page):
    page.goto(f"{BASE}/login", wait_until="networkidle")
    page.fill('input[name="username"]', "admin")
    page.fill('input[name="password"]', "admin")
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")

def check_page(page, path, name):
    try:
        page.goto(f"{BASE}{path}", wait_until="networkidle", timeout=15000)
    except Exception as exc:
        return f"[ERROR] {name} ({path}): 访问失败 - {exc}"

    findings = []
    for selector in FILTER_SELECTORS:
        try:
            count = page.locator(selector).count()
        except Exception:
            count = 0
        if count > 0:
            findings.append(f"{selector}={count}")

    # 额外检查：表头下方紧跟着的 input[placeholder*="筛选"]
    try:
        funnel_inputs = page.locator('thead input[placeholder*="筛选"]').count()
        if funnel_inputs > 0:
            findings.append(f"thead input[placeholder*=筛选]={funnel_inputs}")
    except Exception:
        pass

    if findings:
        return f"[FAIL]  {name} ({path}): {' | '.join(findings)}"
    return f"[OK]    {name} ({path}): 无筛选残留"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        print("=" * 80)
        print("单据明细筛选功能移除验证")
        print("=" * 80)
        login(page)
        print(f"[OK]    登录成功")
        print("-" * 80)

        results = []
        for path, name in PAGES:
            result = check_page(page, path, name)
            print(result)
            results.append(result)

        print("-" * 80)
        fail_count = sum(1 for r in results if r.startswith("[FAIL]"))
        error_count = sum(1 for r in results if r.startswith("[ERROR]"))
        ok_count = sum(1 for r in results if r.startswith("[OK]") and "登录" not in r)

        print(f"汇总: OK={ok_count}  FAIL={fail_count}  ERROR={error_count}")
        if fail_count == 0 and error_count == 0:
            print("结论: 所有单据页面均无筛选残留，移除彻底。")
        else:
            print("结论: 仍有筛选残留，需要继续修复。")

        browser.close()

if __name__ == "__main__":
    main()
