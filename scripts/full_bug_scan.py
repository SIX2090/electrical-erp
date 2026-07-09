import asyncio
import os
import json
import traceback
from datetime import datetime
from playwright.async_api import async_playwright

BASE_URL = "http://127.0.0.1:5000"
REPORT_FILE = r"c:\erp\reports\full_bug_report.json"
SCREENSHOT_DIR = r"c:\erp\reports\bug_screenshots"

PAGES = [
    ("/", "ERP首页"),
    ("/project-delivery-workbench", "项目交付工作台"),
    ("/purchase", "采购工作台"),
    ("/production", "生产工作台"),
    ("/service", "服务工作台"),
    ("/inventory", "库存工作台"),
    ("/master-data", "主数据工作台"),
    ("/mrp", "MRP工作台"),
    ("/trace", "追溯工作台"),
    ("/cost", "成本工作台"),
    ("/purchase_request", "采购申请列表"),
    ("/purchase-orders", "采购订单列表"),
    ("/purchase_receipts", "采购入库列表"),
    ("/purchase-returns", "采购退货列表"),
    ("/supplier-quotes", "供应商报价列表"),
    ("/sales-orders", "销售订单列表"),
    ("/shipments", "销售发货列表"),
    ("/quotations", "设备报价列表"),
    ("/sales-forecasts", "销售预测单列表"),
    ("/sales-inquiries", "询价单列表"),
    ("/sales-invoices", "销售发票登记列表"),
    ("/sales-returns", "销售退货列表"),
    ("/receivables", "应收账款列表"),
    ("/customer-receipts", "客户收款列表"),
    ("/inventory/detail", "库存明细查询"),
    ("/inventory/summary", "库存汇总查询"),
    ("/inventory/aging", "库存账龄查询"),
    ("/inventory/expiry", "库存效期查询"),
    ("/transactions", "库存流水查询"),
    ("/inventory_alerts", "库存预警查询"),
    ("/batch/tracking", "批次机号追溯"),
    ("/inventory_checks", "库存盘点列表"),
    ("/transfers", "库存调拨列表"),
    ("/adjustments", "库存调整列表"),
    ("/inventory/inbound", "其他入库单列表"),
    ("/inventory/outbound", "其他出库单列表"),
    ("/assembly-orders", "组装单列表"),
    ("/disassembly-orders", "拆卸单列表"),
    ("/inventory/reports", "库存报表中心"),
    ("/work-orders", "生产工单列表"),
    ("/production-issues", "生产领料单列表"),
    ("/production-returns", "生产退料单列表"),
    ("/production-completions", "完工入库单列表"),
    ("/production/operation-reports", "工序报工单列表"),
    ("/production-schedules", "生产排程列表"),
    ("/production-enhance/quality-inspections", "质量检验列表"),
    ("/engineering/kitting", "齐套检查"),
    ("/requisition", "工单领料处理"),
    ("/production-enhance/mrp-requirements", "MRP缺料"),
    ("/production/reports", "生产报表中心"),
    ("/subcontract", "委外订单列表"),
    ("/subcontract_issue", "委外发料单列表"),
    ("/subcontract_receive", "委外收货单列表"),
    ("/finance/sales-invoices", "财务销售发票列表"),
    ("/finance/purchase-invoices", "财务采购发票列表"),
    ("/finance/receivables", "财务应收账款"),
    ("/finance/payables", "财务应付账款"),
    ("/payments", "供应商付款列表"),
    ("/finance/vouchers", "凭证列表"),
    ("/finance/financial-statements", "财务报表"),
    ("/finance/period-close", "期间结账"),
    ("/finance/bank-statements", "银行对账单列表"),
    ("/finance/fx-rates", "汇率管理"),
    ("/finance/fx-adjustments", "汇兑损益调整"),
    ("/material", "物料档案"),
    ("/customer", "客户档案"),
    ("/supplier", "供应商档案"),
    ("/warehouse", "仓库档案"),
    ("/locations", "库位档案"),
    ("/unit", "计量单位"),
    ("/department", "部门档案"),
    ("/employee", "员工档案"),
    ("/project-master", "项目档案"),
    ("/machine-serial-master", "机号档案"),
    ("/categories/product", "物料分类"),
    ("/categories/customer", "客户分类"),
    ("/categories/supplier", "供应商分类"),
    ("/bom", "BOM清单"),
    ("/production-routings", "工艺路线列表"),
    ("/work-centers", "工作中心列表"),
    ("/income-categories", "收入类别列表"),
    ("/expense-categories", "支出类别列表"),
    ("/auxiliary-data", "辅助资料列表"),
    ("/settlement-terms", "结算期限列表"),
    ("/payment-terms", "收付款条件列表"),
    ("/currencies", "币别列表"),
    ("/settlement-methods", "结算方式"),
    ("/cash-bank-accounts", "账户管理列表"),
    ("/master/chart-of-accounts", "会计科目列表"),
    ("/sales/reports", "销售报表中心"),
    ("/sales/reports/summary", "销售汇总表"),
    ("/sales/reports/order-execution-summary", "销售订单执行汇总"),
    ("/sales/reports/order-execution-detail", "销售订单执行明细"),
    ("/sales/reports/customer-open-order-analysis", "客户未交订单分析"),
    ("/sales/reports/receivable-aging", "销售应收账龄分析"),
    ("/sales/reports/shipment-execution-detail", "销售发货执行明细"),
    ("/sales/reports/invoice-summary", "销售发票汇总表"),
    ("/sales/reports/daily", "销售日报"),
    ("/users", "用户管理"),
    ("/permissions/roles", "角色权限"),
    ("/operation_logs", "操作日志"),
    ("/system_settings/form", "系统设置"),
    ("/system/data-health", "数据健康"),
    ("/system/print-templates", "打印模板"),
    ("/system/database-backups", "数据库备份"),
    ("/help/assistant", "AI助手"),
    ("/help/operation-manual", "操作手册"),
]


async def main():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    all_bugs = []
    stats = {
        "total_pages": len(PAGES),
        "pages_checked": 0,
        "pages_with_bugs": 0,
        "total_js_errors": 0,
        "total_console_errors": 0,
        "total_console_warnings": 0,
        "total_network_failures": 0,
        "total_http_errors": 0,
        "total_page_errors": 0,
        "bugs_by_severity": {"critical": 0, "high": 0, "medium": 0, "low": 0},
        "bugs_by_category": {},
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        page = await context.new_page()

        page_errors = []
        console_messages = []
        network_failures = []
        http_errors = []

        def on_pageerror(err):
            page_errors.append({
                "message": str(err),
                "stack": getattr(err, "stack", ""),
            })

        def on_console(msg):
            text = msg.text
            if msg.type in ("error", "warning"):
                console_messages.append({
                    "type": msg.type,
                    "text": text[:2000],
                    "location": getattr(msg, "location", {}),
                })

        def on_requestfailed(req):
            failure = req.failure
            if failure:
                network_failures.append({
                    "url": req.url,
                    "method": req.method,
                    "failure": failure.get("errorText", str(failure)),
                    "resource_type": req.resource_type,
                })

        def on_response(resp):
            if resp.status >= 400:
                http_errors.append({
                    "url": resp.url,
                    "status": resp.status,
                    "status_text": resp.status_text,
                    "method": resp.request.method,
                    "resource_type": resp.request.resource_type,
                })

        page.on("pageerror", on_pageerror)
        page.on("console", on_console)
        page.on("requestfailed", on_requestfailed)
        page.on("response", on_response)

        print("Logging in...")
        await page.goto(f"{BASE_URL}/login", timeout=15000)
        await page.fill('input[name="username"]', "admin")
        await page.fill('input[name="password"]', "admin")
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle", timeout=10000)
        await asyncio.sleep(0.5)
        print("Logged in.\n")

        for idx, (url_path, page_name) in enumerate(PAGES, 1):
            url = f"{BASE_URL}{url_path}"
            print(f"[{idx:3d}/{len(PAGES)}] {page_name} ...", end="", flush=True)

            page_bugs = []
            page_errors.clear()
            console_messages.clear()
            network_failures.clear()
            http_errors.clear()

            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                await asyncio.sleep(0.5)

                http_status = response.status if response else 0
                page_title = await page.title()

                if http_status >= 500:
                    bug = {
                        "category": "server_error",
                        "severity": "critical",
                        "message": f"HTTP {http_status} Internal Server Error",
                        "url": url_path,
                        "status_code": http_status,
                    }
                    page_bugs.append(bug)
                    screenshot_path = os.path.join(SCREENSHOT_DIR, f"err500_{idx:03d}_{page_name}.png")
                    try:
                        await page.screenshot(path=screenshot_path, full_page=True)
                        bug["screenshot"] = screenshot_path
                    except Exception:
                        pass
                elif http_status >= 400:
                    bug = {
                        "category": "http_error",
                        "severity": "high",
                        "message": f"HTTP {http_status} {response.status_text if response else ''}",
                        "url": url_path,
                        "status_code": http_status,
                    }
                    page_bugs.append(bug)

                if page_errors:
                    for err in page_errors:
                        bug = {
                            "category": "javascript_error",
                            "severity": "critical",
                            "message": err["message"][:500],
                            "stack": err["stack"][:1000] if err["stack"] else "",
                            "url": url_path,
                        }
                        page_bugs.append(bug)
                        stats["total_js_errors"] += 1

                if console_messages:
                    for msg in console_messages:
                        if msg["type"] == "error":
                            bug = {
                                "category": "console_error",
                                "severity": "high",
                                "message": msg["text"][:500],
                                "url": url_path,
                            }
                            page_bugs.append(bug)
                            stats["total_console_errors"] += 1
                        elif msg["type"] == "warning":
                            if any(kw in msg["text"].lower() for kw in ["failed", "error", "404", "500", "not found", "deprecated", "cannot read", "undefined"]):
                                bug = {
                                    "category": "console_warning",
                                    "severity": "medium",
                                    "message": msg["text"][:500],
                                    "url": url_path,
                                }
                                page_bugs.append(bug)
                            stats["total_console_warnings"] += 1

                if network_failures:
                    for nf in network_failures:
                        bug = {
                            "category": "network_failure",
                            "severity": "high",
                            "message": f"请求失败: {nf['failure']}",
                            "failed_url": nf["url"],
                            "method": nf["method"],
                            "resource_type": nf["resource_type"],
                            "url": url_path,
                        }
                        page_bugs.append(bug)
                        stats["total_network_failures"] += 1

                if http_errors:
                    for he in http_errors:
                        if he["url"].startswith(("data:", "blob:", "chrome-extension:")):
                            continue
                        if "/static/" in he["url"] and he["status"] == 404:
                            bug = {
                                "category": "missing_static_resource",
                                "severity": "medium",
                                "message": f"静态资源404: {he['method']} {he['status']}",
                                "failed_url": he["url"],
                                "url": url_path,
                            }
                        elif he["status"] >= 500:
                            bug = {
                                "category": "api_server_error",
                                "severity": "critical",
                                "message": f"API 5xx错误: {he['method']} {he['status']} {he['status_text']}",
                                "failed_url": he["url"],
                                "url": url_path,
                            }
                        else:
                            bug = {
                                "category": "http_error_response",
                                "severity": "high",
                                "message": f"HTTP {he['status']} 响应: {he['method']} {he['status_text']}",
                                "failed_url": he["url"],
                                "url": url_path,
                            }
                        page_bugs.append(bug)
                        stats["total_http_errors"] += 1

                content = await page.content()
                if "Traceback (most recent call last)" in content or "Internal Server Error" in page_title:
                    bug = {
                        "category": "server_exception",
                        "severity": "critical",
                        "message": "页面显示Python异常回溯或Internal Server Error",
                        "url": url_path,
                        "title": page_title,
                    }
                    page_bugs.append(bug)
                    screenshot_path = os.path.join(SCREENSHOT_DIR, f"traceback_{idx:03d}_{page_name}.png")
                    try:
                        await page.screenshot(path=screenshot_path, full_page=True)
                        bug["screenshot"] = screenshot_path
                    except Exception:
                        pass

                if "404 Not Found" in page_title or "Not Found" in page_title and http_status == 404:
                    bug = {
                        "category": "page_not_found",
                        "severity": "high",
                        "message": "页面返回404 Not Found",
                        "url": url_path,
                        "title": page_title,
                    }
                    page_bugs.append(bug)

                visible_text = await page.evaluate("() => document.body ? document.body.innerText : ''")
                if visible_text and ("jinja2.exceptions" in visible_text or "UndefinedError" in visible_text or "TemplateNotFound" in visible_text):
                    bug = {
                        "category": "template_render_error",
                        "severity": "critical",
                        "message": "Jinja2模板渲染错误",
                        "url": url_path,
                    }
                    page_bugs.append(bug)

                if page_bugs:
                    print(f"  -> {len(page_bugs)} bugs found")
                    for b in page_bugs:
                        stats["bugs_by_severity"][b["severity"]] = stats["bugs_by_severity"].get(b["severity"], 0) + 1
                        cat = b["category"]
                        stats["bugs_by_category"][cat] = stats["bugs_by_category"].get(cat, 0) + 1
                    stats["pages_with_bugs"] += 1
                    all_bugs.append({
                        "page": page_name,
                        "url": url_path,
                        "http_status": http_status,
                        "title": page_title,
                        "bugs": page_bugs,
                    })
                else:
                    print("  OK")

                stats["pages_checked"] += 1

            except Exception as e:
                bug = {
                    "category": "page_load_error",
                    "severity": "critical",
                    "message": f"页面加载异常: {str(e)[:300]}",
                    "url": url_path,
                }
                page_bugs.append(bug)
                stats["total_page_errors"] += 1
                stats["pages_with_bugs"] += 1
                all_bugs.append({
                    "page": page_name,
                    "url": url_path,
                    "bugs": page_bugs,
                })
                print(f"  -> ERROR: {str(e)[:100]}")

        await browser.close()

    report = {
        "scan_time": datetime.now().isoformat(),
        "base_url": BASE_URL,
        "stats": stats,
        "bugs": all_bugs,
    }

    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"BUG检测完成!")
    print(f"  检查页面: {stats['pages_checked']}/{stats['total_pages']}")
    print(f"  有问题页面: {stats['pages_with_bugs']}")
    print(f"  严重(critical): {stats['bugs_by_severity'].get('critical', 0)}")
    print(f"  高(high): {stats['bugs_by_severity'].get('high', 0)}")
    print(f"  中(medium): {stats['bugs_by_severity'].get('medium', 0)}")
    print(f"  低(low): {stats['bugs_by_severity'].get('low', 0)}")
    print(f"  分类统计: {json.dumps(stats['bugs_by_category'], ensure_ascii=False)}")
    print(f"\n详细报告: {REPORT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
