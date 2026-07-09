"""找出单据页面菜单栏中"筛选"按钮的实际位置。"""
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5000"

PAGES = [
    ("/purchase_order/new", "采购订单新增"),
    ("/work_order/new", "工单新增"),
    ("/purchase_request/new", "采购申请新增"),
]

def login(page):
    page.goto(f"{BASE}/login", wait_until="networkidle")
    page.fill('input[name="username"]', "admin")
    page.fill('input[name="password"]', "admin")
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")

def inspect(page, path, name):
    print(f"\n{'='*70}")
    print(f"页面: {name} ({path})")
    print('='*70)
    try:
        page.goto(f"{BASE}{path}", wait_until="networkidle", timeout=15000)
    except Exception as exc:
        print(f"访问失败: {exc}")
        return

    # 查找所有包含"筛选"文字的元素
    print("\n[1] 所有包含'筛选'文字的元素:")
    elements = page.locator('text=/筛选/').all()
    for i, el in enumerate(elements):
        try:
            tag = el.evaluate("e => e.tagName")
            cls = el.evaluate("e => e.className")
            text = el.inner_text()[:80]
            outer = el.evaluate("e => e.outerHTML.substring(0, 300)")
            print(f"  [{i}] <{tag}> class='{cls}' text='{text}'")
            print(f"      HTML: {outer}")
        except Exception:
            pass

    # 查找菜单栏
    print("\n[2] document-menu-bar 内的所有按钮/链接:")
    menu_items = page.locator('.document-menu-bar__item').all()
    for i, el in enumerate(menu_items):
        try:
            text = el.inner_text().strip()
            tag = el.evaluate("e => e.tagName")
            event = el.get_attribute('data-menu-event') or ''
            print(f"  [{i}] <{tag}> text='{text}' event='{event}'")
        except Exception:
            pass

    # 查找漏斗图标
    print("\n[3] 所有 bi-funnel 图标元素:")
    funnels = page.locator('.bi-funnel').all()
    for i, el in enumerate(funnels):
        try:
            parent = el.evaluate("e => e.parentElement.outerHTML.substring(0, 300)")
            print(f"  [{i}] parent: {parent}")
        except Exception:
            pass

    # 截图保存
    page.screenshot(path=f"c:/erp/logs/filter_inspect_{name}.png", full_page=False)
    print(f"\n[4] 截图已保存: c:/erp/logs/filter_inspect_{name}.png")

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()
        login(page)
        print("[OK] 登录成功")
        for path, name in PAGES:
            inspect(page, path, name)
        browser.close()

if __name__ == "__main__":
    main()
