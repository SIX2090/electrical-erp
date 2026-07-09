import asyncio
import os
import json
import psycopg2
from datetime import datetime
from playwright.async_api import async_playwright

BASE_URL = "http://127.0.0.1:5000"
REPORT_FILE = r"c:\erp\reports\deep_bug_report.json"
SCREENSHOT_DIR = r"c:\erp\reports\bug_screenshots"

os.makedirs(SCREENSHOT_DIR, exist_ok=True)

PG_PASSWORD = os.environ.get("PG_PASSWORD", "admin")


def get_db_conn():
    return psycopg2.connect(
        host="127.0.0.1", port=5432, dbname="postgres",
        user="postgres", password=PG_PASSWORD,
    )


def get_existing_records():
    """Query database for existing document IDs to test detail pages"""
    conn = get_db_conn()
    cur = conn.cursor()
    records = {}
    tables = [
        ("purchase_requests", "/purchase-requests/", "id"),
        ("purchase_orders", "/purchase-orders/", "id"),
        ("purchase_receipts", "/purchase-receipts/", "id"),
        ("sales_orders", "/sales-orders/", "id"),
        ("sales_shipments", "/shipments/", "id"),
        ("work_orders", "/work-orders/", "id"),
        ("production_issues", "/production-issues/", "id"),
        ("production_completions", "/production-completions/", "id"),
        ("subcontract_orders", "/subcontract/", "id"),
        ("boms", "/bom/", "id"),
        ("products", "/material/", "id"),
        ("customers", "/customer/", "id"),
        ("suppliers", "/supplier/", "id"),
        ("warehouses", "/warehouse/", "id"),
        ("transfer_orders", "/transfers/", "id"),
        ("inventory_adjustments", "/adjustments/", "id"),
        ("inventory_check_orders", "/inventory_checks/", "id"),
        ("inventory_assembly_orders", "/assembly-orders/", "id"),
    ]
    for table, url_prefix, id_col in tables:
        try:
            cur.execute(f'SELECT {id_col} FROM {table} ORDER BY id DESC LIMIT 3')
            rows = cur.fetchall()
            records[table] = [{"id": r[0], "url": f"{url_prefix}{r[0]}"} for r in rows]
        except Exception as e:
            records[table] = {"error": str(e)}
    cur.close()
    conn.close()
    return records


async def test_api_endpoints(page):
    """Test API endpoints for errors"""
    api_bugs = []
    apis_to_test = [
        ("/api/menu", "菜单API"),
        ("/api/workbench/queues", "工作台队列API"),
        ("/api/lov/materials", "物料LOV API"),
        ("/api/lov/customers", "客户LOV API"),
        ("/api/lov/suppliers", "供应商LOV API"),
        ("/api/lov/warehouses", "仓库LOV API"),
        ("/api/doc_nav/work_orders/1", "工单导航API"),
        ("/api/system/health", "系统健康检查API"),
    ]
    for api_path, name in apis_to_test:
        try:
            resp = await page.goto(f"{BASE_URL}{api_path}", wait_until="domcontentloaded", timeout=10000)
            if resp.status >= 400:
                api_bugs.append({
                    "category": "api_error",
                    "severity": "high" if resp.status >= 500 else "medium",
                    "message": f"{name} 返回 HTTP {resp.status}",
                    "url": api_path,
                    "status_code": resp.status,
                })
            else:
                try:
                    text = await page.text_content("body")
                    if text and "Traceback" in text:
                        api_bugs.append({
                            "category": "api_traceback",
                            "severity": "critical",
                            "message": f"{name} 返回异常回溯",
                            "url": api_path,
                        })
                except Exception:
                    pass
        except Exception as e:
            api_bugs.append({
                "category": "api_load_error",
                "severity": "high",
                "message": f"{name} 加载失败: {str(e)[:200]}",
                "url": api_path,
            })
    return api_bugs


async def main():
    all_bugs = []
    stats = {
        "detail_pages_tested": 0,
        "detail_pages_with_bugs": 0,
        "api_endpoints_tested": 0,
    }

    print("Querying database for existing records...")
    records = get_existing_records()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        page = await context.new_page()

        page_errors = []
        console_errors = []
        network_failures = []

        def on_pageerror(err):
            page_errors.append(str(err))

        def on_console(msg):
            if msg.type == "error":
                console_errors.append(msg.text[:500])

        def on_requestfailed(req):
            if req.failure and not req.url.startswith("data:"):
                network_failures.append(f"{req.method} {req.url} -> {req.failure.get('errorText', '')}")

        page.on("pageerror", on_pageerror)
        page.on("console", on_console)
        page.on("requestfailed", on_requestfailed)

        print("Logging in...")
        await page.goto(f"{BASE_URL}/login", timeout=15000)
        await page.fill('input[name="username"]', "admin")
        await page.fill('input[name="password"]', "admin")
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle", timeout=10000)
        await asyncio.sleep(0.5)
        print("Logged in.\n")

        # Test API endpoints
        print("Testing API endpoints...")
        api_bugs = await test_api_endpoints(page)
        stats["api_endpoints_tested"] = 8
        all_bugs.extend(api_bugs)
        if api_bugs:
            print(f"  Found {len(api_bugs)} API issues")
        else:
            print("  All APIs OK")

        # Test detail pages
        print("\nTesting detail pages...")
        for table, recs in records.items():
            if isinstance(recs, dict) and "error" in recs:
                all_bugs.append({
                    "category": "database_query_error",
                    "severity": "medium",
                    "message": f"Table {table} query error: {recs['error']}",
                })
                continue
            for rec in recs[:2]:
                url = rec["url"]
                page_errors.clear()
                console_errors.clear()
                network_failures.clear()
                stats["detail_pages_tested"] += 1

                try:
                    resp = await page.goto(f"{BASE_URL}{url}", wait_until="domcontentloaded", timeout=15000)
                    try:
                        await page.wait_for_load_state("networkidle", timeout=5000)
                    except Exception:
                        pass
                    await asyncio.sleep(0.3)

                    page_bugs = []
                    http_status = resp.status if resp else 0
                    title = await page.title()

                    if http_status >= 500:
                        page_bugs.append({
                            "category": "detail_page_500",
                            "severity": "critical",
                            "message": f"详情页返回 HTTP {http_status}",
                            "url": url,
                            "table": table,
                            "doc_id": rec["id"],
                        })
                    elif http_status >= 400:
                        page_bugs.append({
                            "category": "detail_page_404",
                            "severity": "high",
                            "message": f"详情页返回 HTTP {http_status}",
                            "url": url,
                            "table": table,
                            "doc_id": rec["id"],
                        })

                    if page_errors:
                        for err in page_errors:
                            page_bugs.append({
                                "category": "detail_page_js_error",
                                "severity": "critical",
                                "message": err[:300],
                                "url": url,
                                "table": table,
                            })

                    if console_errors:
                        for err in console_errors:
                            if any(kw in err.lower() for kw in ["failed", "error", "not found", "404", "500", "undefined", "cannot read"]):
                                page_bugs.append({
                                    "category": "detail_page_console_error",
                                    "severity": "high",
                                    "message": err[:300],
                                    "url": url,
                                    "table": table,
                                })

                    nav_config = await page.evaluate("""() => {
                        const el = document.getElementById('doc-nav-config');
                        if (!el) return { exists: false };
                        return {
                            exists: true,
                            table: el.dataset.navTable,
                            base: el.dataset.navBase,
                            docId: el.dataset.docId,
                        };
                    }""")

                    # Check if toolbar has nav buttons
                    toolbar_buttons = await page.evaluate("""() => {
                        const buttons = [];
                        document.querySelectorAll('.global-toolbar button, .global-toolbar .toolbar-btn, [data-event]').forEach(b => {
                            buttons.push(b.textContent.trim());
                        });
                        return buttons;
                    }""")

                    content_text = await page.evaluate("() => document.body ? document.body.innerText.substring(0, 2000) : ''")
                    if "Traceback" in content_text or "Internal Server Error" in title:
                        page_bugs.append({
                            "category": "detail_page_traceback",
                            "severity": "critical",
                            "message": "详情页显示Python异常回溯",
                            "url": url,
                            "table": table,
                        })

                    if page_bugs:
                        stats["detail_pages_with_bugs"] += 1
                        for b in page_bugs:
                            all_bugs.append(b)
                        screenshot_path = os.path.join(SCREENSHOT_DIR, f"detail_bug_{table}_{rec['id']}.png")
                        try:
                            await page.screenshot(path=screenshot_path, full_page=False)
                        except Exception:
                            pass
                        print(f"  {table}/{rec['id']}: {len(page_bugs)} bugs")
                    else:
                        print(f"  {table}/{rec['id']}: OK")

                except Exception as e:
                    all_bugs.append({
                        "category": "detail_page_load_error",
                        "severity": "critical",
                        "message": f"详情页加载异常: {str(e)[:200]}",
                        "url": url,
                        "table": table,
                    })
                    print(f"  {table}/{rec['id']}: ERROR - {str(e)[:100]}")

        await browser.close()

    # Add known inventory consistency bug
    all_bugs.append({
        "category": "data_consistency",
        "severity": "high",
        "message": "批次跟踪与库存余额不一致: product_id=173, warehouse_id=58, location_id=11, batch_qty=0 vs balance_qty=1.000, qty_diff=-1.000",
        "repair_hint": "run scripts/repair_inventory_balance_consistency.py --dry-run; use --apply only after review",
    })

    # Categorize bugs
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    category_counts = {}
    for b in all_bugs:
        sev = b.get("severity", "medium")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        cat = b.get("category", "unknown")
        category_counts[cat] = category_counts.get(cat, 0) + 1

    report = {
        "scan_time": datetime.now().isoformat(),
        "base_url": BASE_URL,
        "stats": {
            **stats,
            "total_bugs": len(all_bugs),
            "by_severity": severity_counts,
            "by_category": category_counts,
        },
        "bugs": all_bugs,
    }

    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"深度BUG检测完成!")
    print(f"  详情页测试: {stats['detail_pages_tested']}")
    print(f"  详情页有BUG: {stats['detail_pages_with_bugs']}")
    print(f"  API端点测试: {stats['api_endpoints_tested']}")
    print(f"  BUG总数: {len(all_bugs)}")
    print(f"  严重(critical): {severity_counts.get('critical', 0)}")
    print(f"  高(high): {severity_counts.get('high', 0)}")
    print(f"  中(medium): {severity_counts.get('medium', 0)}")
    print(f"  低(low): {severity_counts.get('low', 0)}")
    print(f"\n详细报告: {REPORT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
