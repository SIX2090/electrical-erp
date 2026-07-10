import asyncio
import os
import json
from playwright.async_api import async_playwright

BASE_URL = "http://127.0.0.1:5000"
OUTPUT_DIR = r"c:\erp\screenshots"
REPORT_FILE = r"c:\erp\reports\ui_quality_issues.json"

PAGES = [
    ("/", "首页", "01_home_workbench"),
    ("/project-delivery-workbench", "项目交付工作台", "01_home_workbench"),
    ("/purchase", "采购工作台", "01_home_workbench"),
    ("/production", "生产工作台", "01_home_workbench"),
    ("/service", "服务工作台", "01_home_workbench"),
    ("/inventory", "库存工作台", "01_home_workbench"),
    ("/master-data", "主数据工作台", "01_home_workbench"),
    ("/mrp", "MRP工作台", "01_home_workbench"),
    ("/trace", "追溯工作台", "01_home_workbench"),
    ("/cost", "成本工作台", "01_home_workbench"),
    ("/purchase_request", "采购申请列表", "02_purchase"),
    ("/purchase_request/new", "采购申请新增", "02_purchase"),
    ("/purchase-orders", "采购订单列表", "02_purchase"),
    ("/purchase_order/new", "采购订单新增", "02_purchase"),
    ("/purchase_receipts", "采购入库列表", "02_purchase"),
    ("/purchase-returns", "采购退货列表", "02_purchase"),
    ("/supplier-quotes", "供应商报价列表", "02_purchase"),
    ("/sales-orders", "销售订单列表", "03_sales"),
    ("/sales-orders/new", "销售订单新增", "03_sales"),
    ("/shipments", "销售发货列表", "03_sales"),
    ("/quotations", "设备报价列表", "03_sales"),
    ("/sales-forecasts", "销售预测单列表", "03_sales"),
    ("/sales-inquiries", "询价单列表", "03_sales"),
    ("/sales-invoices", "销售发票登记列表", "03_sales"),
    ("/sales-returns", "销售退货列表", "03_sales"),
    ("/receivables", "应收账款列表", "03_sales"),
    ("/customer-receipts", "客户收款列表", "03_sales"),
    ("/inventory/detail", "库存明细查询", "04_inventory"),
    ("/inventory/summary", "库存汇总查询", "04_inventory"),
    ("/inventory/aging", "库存账龄查询", "04_inventory"),
    ("/inventory/expiry", "库存效期查询", "04_inventory"),
    ("/transactions", "库存流水查询", "04_inventory"),
    ("/inventory_alerts", "库存预警查询", "04_inventory"),
    ("/batch/tracking", "批次柜号追溯", "04_inventory"),
    ("/inventory_checks", "库存盘点列表", "04_inventory"),
    ("/transfers", "库存调拨列表", "04_inventory"),
    ("/adjustments", "库存调整列表", "04_inventory"),
    ("/inventory/inbound", "其他入库单列表", "04_inventory"),
    ("/inventory/outbound", "其他出库单列表", "04_inventory"),
    ("/assembly-orders", "组装单列表", "04_inventory"),
    ("/disassembly-orders", "拆卸单列表", "04_inventory"),
    ("/inventory/reports", "库存报表中心", "04_inventory"),
    ("/work-orders", "生产工单列表", "05_production"),
    ("/work-orders/new", "生产工单新增", "05_production"),
    ("/production-issues", "生产领料单列表", "05_production"),
    ("/production-returns", "生产退料单列表", "05_production"),
    ("/production-completions", "完工入库单列表", "05_production"),
    ("/production/operation-reports", "工序报工单列表", "05_production"),
    ("/production-schedules", "生产排程列表", "05_production"),
    ("/production-enhance/quality-inspections", "质量检验列表", "05_production"),
    ("/engineering/kitting", "齐套检查", "05_production"),
    ("/requisition", "工单领料处理", "05_production"),
    ("/production-enhance/mrp-requirements", "MRP缺料", "05_production"),
    ("/production/reports", "生产报表中心", "05_production"),
    ("/subcontract", "委外订单列表", "06_subcontract"),
    ("/subcontract/new", "委外订单新增", "06_subcontract"),
    ("/subcontract_issue", "委外发料单列表", "06_subcontract"),
    ("/subcontract_receive", "委外收货单列表", "06_subcontract"),
    ("/finance/sales-invoices", "财务销售发票列表", "07_finance"),
    ("/finance/purchase-invoices", "财务采购发票列表", "07_finance"),
    ("/finance/receivables", "财务应收账款", "07_finance"),
    ("/finance/payables", "财务应付账款", "07_finance"),
    ("/payments", "供应商付款列表", "07_finance"),
    ("/customer-receipts", "客户收款列表", "07_finance"),
    ("/finance/vouchers", "凭证列表", "07_finance"),
    ("/finance/financial-statements", "财务报表", "07_finance"),
    ("/finance/period-close", "期间结账", "07_finance"),
    ("/finance/bank-statements", "银行对账单列表", "07_finance"),
    ("/finance/fx-rates", "汇率管理", "07_finance"),
    ("/finance/fx-adjustments", "汇兑损益调整", "07_finance"),
    ("/material", "物料档案", "08_master_engineering"),
    ("/material/new", "物料新增", "08_master_engineering"),
    ("/customer", "客户档案", "08_master_engineering"),
    ("/supplier", "供应商档案", "08_master_engineering"),
    ("/warehouse", "仓库档案", "08_master_engineering"),
    ("/locations", "库位档案", "08_master_engineering"),
    ("/unit", "计量单位", "08_master_engineering"),
    ("/department", "部门档案", "08_master_engineering"),
    ("/employee", "员工档案", "08_master_engineering"),
    ("/project-master", "项目档案", "08_master_engineering"),
    ("/cabinet-master", "柜号档案", "08_master_engineering"),
    ("/categories/product", "物料分类", "08_master_engineering"),
    ("/categories/customer", "客户分类", "08_master_engineering"),
    ("/categories/supplier", "供应商分类", "08_master_engineering"),
    ("/bom", "BOM清单", "08_master_engineering"),
    ("/bom/new", "BOM新增", "08_master_engineering"),
    ("/production-routings", "工艺路线列表", "08_master_engineering"),
    ("/work-centers", "工作中心列表", "08_master_engineering"),
    ("/income-categories", "收入类别列表", "08_master_engineering"),
    ("/expense-categories", "支出类别列表", "08_master_engineering"),
    ("/auxiliary-data", "辅助资料列表", "08_master_engineering"),
    ("/settlement-terms", "结算期限列表", "08_master_engineering"),
    ("/payment-terms", "收付款条件列表", "08_master_engineering"),
    ("/currencies", "币别列表", "08_master_engineering"),
    ("/settlement-methods", "结算方式", "08_master_engineering"),
    ("/cash-bank-accounts", "账户管理列表", "08_master_engineering"),
    ("/master/chart-of-accounts", "会计科目列表", "08_master_engineering"),
    ("/sales/reports", "销售报表中心", "09_reports"),
    ("/sales/reports/summary", "销售汇总表", "09_reports"),
    ("/sales/reports/order-execution-summary", "销售订单执行汇总", "09_reports"),
    ("/sales/reports/order-execution-detail", "销售订单执行明细", "09_reports"),
    ("/sales/reports/customer-open-order-analysis", "客户未交订单分析", "09_reports"),
    ("/sales/reports/receivable-aging", "销售应收账龄分析", "09_reports"),
    ("/sales/reports/shipment-execution-detail", "销售发货执行明细", "09_reports"),
    ("/sales/reports/invoice-summary", "销售发票汇总表", "09_reports"),
    ("/sales/reports/daily", "销售日报", "09_reports"),
    ("/users", "用户管理", "10_system"),
    ("/permissions/roles", "角色权限", "10_system"),
    ("/operation_logs", "操作日志", "10_system"),
    ("/system_settings/form", "系统设置", "10_system"),
    ("/system/data-health", "数据健康", "10_system"),
    ("/system/print-templates", "打印模板", "10_system"),
    ("/system/database-backups", "数据库备份", "10_system"),
    ("/help/assistant", "AI助手", "10_system"),
    ("/help/operation-manual", "操作手册", "10_system"),
]


async def main():
    all_issues = []
    page_stats = {
        "total": len(PAGES),
        "success": 0,
        "failed": 0,
        "console_errors": 0,
        "network_errors": 0,
        "slow_pages": 0,
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        page = await context.new_page()

        console_errors = []
        network_errors = []

        def on_console(msg):
            if msg.type in ("error", "warning"):
                console_errors.append({
                    "type": msg.type,
                    "text": msg.text,
                })

        def on_requestfailed(req):
            if req.failure:
                network_errors.append({
                    "url": req.url,
                    "failure": req.failure,
                })

        page.on("console", on_console)
        page.on("requestfailed", on_requestfailed)

        # 登录
        print("Logging in...")
        await page.goto(f"{BASE_URL}/login")
        await page.fill('input[name="username"]', "admin")
        await page.fill('input[name="password"]', "admin")
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")
        print("Logged in.")

        for idx, (url_path, page_name, module) in enumerate(PAGES, 1):
            print(f"[{idx}/{len(PAGES)}] Checking: {page_name} ({url_path})...")
            url = f"{BASE_URL}{url_path}"

            page_issues = []
            console_errors.clear()
            network_errors.clear()

            try:
                start_time = asyncio.get_event_loop().time()
                response = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                await asyncio.sleep(0.3)
                load_time = asyncio.get_event_loop().time() - start_time

                # 检查HTTP状态码
                if response and response.status >= 400:
                    page_issues.append({
                        "type": "http_error",
                        "severity": "high",
                        "message": f"HTTP {response.status}",
                    })

                # 检查加载时间
                if load_time > 5:
                    page_issues.append({
                        "type": "slow_load",
                        "severity": "medium",
                        "message": f"加载时间: {load_time:.2f}s",
                    })
                    page_stats["slow_pages"] += 1

                # 检查控制台错误
                err_count = sum(1 for e in console_errors if e["type"] == "error")
                warn_count = sum(1 for e in console_errors if e["type"] == "warning")
                if err_count > 0:
                    page_issues.append({
                        "type": "console_error",
                        "severity": "high",
                        "message": f"{err_count} 个错误, {warn_count} 个警告",
                        "details": [e["text"] for e in console_errors if e["type"] == "error"][:5],
                    })
                    page_stats["console_errors"] += err_count

                # 检查网络请求失败
                if len(network_errors) > 0:
                    page_issues.append({
                        "type": "network_error",
                        "severity": "medium",
                        "message": f"{len(network_errors)} 个请求失败",
                        "details": [e["url"] for e in network_errors][:5],
                    })
                    page_stats["network_errors"] += len(network_errors)

                # 检查页面标题
                title = await page.title()
                if not title or "错误" in title or "Error" in title:
                    page_issues.append({
                        "type": "title_issue",
                        "severity": "medium",
                        "message": f"页面标题: {title}",
                    })

                # 截图
                screenshot_path = os.path.join(OUTPUT_DIR, module, f"{idx:03d}_{page_name}.png")
                try:
                    await page.screenshot(path=screenshot_path, full_page=True)
                except Exception as e:
                    page_issues.append({
                        "type": "screenshot_error",
                        "severity": "low",
                        "message": f"截图失败: {str(e)}",
                    })

                page_stats["success"] += 1

            except Exception as e:
                page_issues.append({
                    "type": "page_error",
                    "severity": "high",
                    "message": f"页面访问失败: {str(e)}",
                })
                page_stats["failed"] += 1

            if page_issues:
                all_issues.append({
                    "page": page_name,
                    "url": url_path,
                    "module": module,
                    "issues": page_issues,
                })
                print(f"  -> 发现 {len(page_issues)} 个问题")

        await browser.close()

    # 保存报告
    report = {
        "stats": page_stats,
        "issues": all_issues,
        "total_pages_with_issues": len(all_issues),
    }

    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"检测完成!")
    print(f"总页面数: {page_stats['total']}")
    print(f"成功: {page_stats['success']}")
    print(f"失败: {page_stats['failed']}")
    print(f"有问题的页面: {len(all_issues)}")
    print(f"控制台错误总数: {page_stats['console_errors']}")
    print(f"网络请求失败总数: {page_stats['network_errors']}")
    print(f"慢页面数: {page_stats['slow_pages']}")
    print(f"\n详细报告已保存到: {REPORT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
