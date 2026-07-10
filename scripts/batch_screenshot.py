import asyncio
import os
import sys
from playwright.async_api import async_playwright

BASE_URL = "http://127.0.0.1:5000"
OUTPUT_DIR = r"c:\erp\screenshots"

PAGES = [
    # 首页/工作台
    ("/", "01_home_workbench/01_home.png"),
    ("/project-delivery-workbench", "01_home_workbench/02_project_delivery_workbench.png"),
    ("/purchase", "01_home_workbench/03_purchase_workbench.png"),
    ("/production", "01_home_workbench/04_production_workbench.png"),
    ("/service", "01_home_workbench/05_service_workbench.png"),
    ("/inventory", "01_home_workbench/06_inventory_workbench.png"),
    ("/master-data", "01_home_workbench/07_master_data_workbench.png"),
    ("/mrp", "01_home_workbench/08_mrp_workbench.png"),
    ("/trace", "01_home_workbench/09_trace_workbench.png"),
    ("/cost", "01_home_workbench/10_cost_workbench.png"),

    # 采购管理
    ("/purchase_request", "02_purchase/01_purchase_requisition_list.png"),
    ("/purchase_request/new", "02_purchase/02_purchase_requisition_new.png"),
    ("/purchase-orders", "02_purchase/03_purchase_order_list.png"),
    ("/purchase_order/new", "02_purchase/04_purchase_order_new.png"),
    ("/purchase_receipts", "02_purchase/05_purchase_receipt_list.png"),
    ("/purchase-returns", "02_purchase/06_purchase_return_list.png"),
    ("/supplier-quotes", "02_purchase/07_supplier_quote_list.png"),

    # 销售管理
    ("/sales-orders", "03_sales/01_sales_order_list.png"),
    ("/sales-orders/new", "03_sales/02_sales_order_new.png"),
    ("/shipments", "03_sales/03_shipment_list.png"),
    ("/quotations", "03_sales/04_quotation_list.png"),
    ("/sales-forecasts", "03_sales/05_sales_forecast_list.png"),
    ("/sales-inquiries", "03_sales/06_sales_inquiry_list.png"),
    ("/sales-invoices", "03_sales/07_sales_invoice_list.png"),
    ("/sales-returns", "03_sales/08_sales_return_list.png"),
    ("/receivables", "03_sales/09_receivables_list.png"),
    ("/customer-receipts", "03_sales/10_customer_receipts_list.png"),

    # 库存管理
    ("/inventory/detail", "04_inventory/01_inventory_detail.png"),
    ("/inventory/summary", "04_inventory/02_inventory_summary.png"),
    ("/inventory/aging", "04_inventory/03_inventory_aging.png"),
    ("/inventory/expiry", "04_inventory/04_inventory_expiry.png"),
    ("/transactions", "04_inventory/05_stock_transactions.png"),
    ("/inventory_alerts", "04_inventory/06_inventory_alerts.png"),
    ("/batch/tracking", "04_inventory/07_batch_tracking.png"),
    ("/inventory_checks", "04_inventory/08_inventory_check_list.png"),
    ("/transfers", "04_inventory/09_transfer_list.png"),
    ("/adjustments", "04_inventory/10_adjustment_list.png"),
    ("/inventory/inbound", "04_inventory/11_other_inbound_list.png"),
    ("/inventory/outbound", "04_inventory/12_other_outbound_list.png"),
    ("/assembly-orders", "04_inventory/13_assembly_order_list.png"),
    ("/disassembly-orders", "04_inventory/14_disassembly_order_list.png"),
    ("/inventory/reports", "04_inventory/15_inventory_report_center.png"),

    # 生产管理
    ("/work-orders", "05_production/01_work_order_list.png"),
    ("/work-orders/new", "05_production/02_work_order_new.png"),
    ("/production-issues", "05_production/03_production_issue_list.png"),
    ("/production-returns", "05_production/04_production_return_list.png"),
    ("/production-completions", "05_production/05_production_completion_list.png"),
    ("/production/operation-reports", "05_production/06_operation_report_list.png"),
    ("/production-schedules", "05_production/07_production_schedule_list.png"),
    ("/production-enhance/quality-inspections", "05_production/08_quality_inspection_list.png"),
    ("/engineering/kitting", "05_production/09_kitting_check.png"),
    ("/requisition", "05_production/10_requisition_list.png"),
    ("/production-enhance/mrp-requirements", "05_production/11_mrp_requirements.png"),
    ("/production/reports", "05_production/12_production_report_center.png"),

    # 委外管理
    ("/subcontract", "06_subcontract/01_subcontract_order_list.png"),
    ("/subcontract/new", "06_subcontract/02_subcontract_order_new.png"),
    ("/subcontract_issue", "06_subcontract/03_subcontract_issue_list.png"),
    ("/subcontract_receive", "06_subcontract/04_subcontract_receive_list.png"),

    # 财务管理
    ("/finance/sales-invoices", "07_finance/01_sales_invoice_list.png"),
    ("/finance/purchase-invoices", "07_finance/02_purchase_invoice_list.png"),
    ("/finance/receivables", "07_finance/03_receivables_list.png"),
    ("/finance/payables", "07_finance/04_payables_list.png"),
    ("/payments", "07_finance/05_payment_list.png"),
    ("/customer-receipts", "07_finance/06_customer_receipt_list.png"),
    ("/finance/vouchers", "07_finance/07_voucher_list.png"),
    ("/finance/financial-statements", "07_finance/08_financial_statements.png"),
    ("/finance/period-close", "07_finance/09_period_close.png"),
    ("/finance/bank-statements", "07_finance/10_bank_statement_list.png"),
    ("/finance/fx-rates", "07_finance/11_fx_rates.png"),
    ("/finance/fx-adjustments", "07_finance/12_fx_adjustments.png"),

    # 基础资料/工程
    ("/material", "08_master_engineering/01_material_master.png"),
    ("/material/new", "08_master_engineering/02_material_new.png"),
    ("/customer", "08_master_engineering/03_customer_master.png"),
    ("/supplier", "08_master_engineering/04_supplier_master.png"),
    ("/warehouse", "08_master_engineering/05_warehouse_master.png"),
    ("/locations", "08_master_engineering/06_location_master.png"),
    ("/unit", "08_master_engineering/07_unit_master.png"),
    ("/department", "08_master_engineering/08_department_master.png"),
    ("/employee", "08_master_engineering/09_employee_master.png"),
    ("/project-master", "08_master_engineering/10_project_master.png"),
    ("/cabinet-master", "08_master_engineering/11_cabinet_master.png"),
    ("/categories/product", "08_master_engineering/12_product_category.png"),
    ("/categories/customer", "08_master_engineering/13_customer_category.png"),
    ("/categories/supplier", "08_master_engineering/14_supplier_category.png"),
    ("/bom", "08_master_engineering/15_bom_list.png"),
    ("/bom/new", "08_master_engineering/16_bom_new.png"),
    ("/production-routings", "08_master_engineering/17_routing_list.png"),
    ("/work-centers", "08_master_engineering/18_work_center_list.png"),
    ("/income-categories", "08_master_engineering/19_income_categories.png"),
    ("/expense-categories", "08_master_engineering/20_expense_categories.png"),
    ("/auxiliary-data", "08_master_engineering/21_auxiliary_data.png"),
    ("/settlement-terms", "08_master_engineering/22_settlement_terms.png"),
    ("/payment-terms", "08_master_engineering/23_payment_terms.png"),
    ("/currencies", "08_master_engineering/24_currencies.png"),
    ("/settlement-methods", "08_master_engineering/25_settlement_methods.png"),
    ("/cash-bank-accounts", "08_master_engineering/26_cash_bank_accounts.png"),
    ("/master/chart-of-accounts", "08_master_engineering/27_chart_of_accounts.png"),

    # 报表中心
    ("/sales/reports", "09_reports/01_sales_report_center.png"),
    ("/sales/reports/summary", "09_reports/02_sales_summary.png"),
    ("/sales/reports/order-execution-summary", "09_reports/03_order_execution_summary.png"),
    ("/sales/reports/order-execution-detail", "09_reports/04_order_execution_detail.png"),
    ("/sales/reports/customer-open-order-analysis", "09_reports/05_customer_open_order.png"),
    ("/sales/reports/receivable-aging", "09_reports/06_receivable_aging.png"),
    ("/sales/reports/shipment-execution-detail", "09_reports/07_shipment_execution_detail.png"),
    ("/sales/reports/invoice-summary", "09_reports/08_invoice_summary.png"),
    ("/sales/reports/daily", "09_reports/09_sales_daily.png"),

    # 系统管理
    ("/users", "10_system/01_user_management.png"),
    ("/permissions/roles", "10_system/02_role_permissions.png"),
    ("/operation_logs", "10_system/03_operation_logs.png"),
    ("/system_settings/form", "10_system/04_system_settings.png"),
    ("/system/data-health", "10_system/05_data_health.png"),
    ("/system/print-templates", "10_system/06_print_templates.png"),
    ("/system/database-backups", "10_system/07_database_backups.png"),
    ("/help/assistant", "10_system/08_help_assistant.png"),
    ("/help/operation-manual", "10_system/09_operation_manual.png"),
]


async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for _, rel_path in PAGES:
        full_path = os.path.join(OUTPUT_DIR, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        page = await context.new_page()

        # 登录
        print("Logging in...")
        await page.goto(f"{BASE_URL}/login")
        await page.fill('input[name="username"]', "admin")
        await page.fill('input[name="password"]', "admin")
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")
        print("Logged in successfully.")

        success = 0
        failed = 0
        errors = []

        for url_path, rel_path in PAGES:
            full_path = os.path.join(OUTPUT_DIR, rel_path)
            url = f"{BASE_URL}{url_path}"
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                await asyncio.sleep(0.5)
                await page.screenshot(path=full_path, full_page=True)
                success += 1
                print(f"[OK] {url_path} -> {rel_path}")
            except Exception as e:
                failed += 1
                errors.append((url_path, str(e)))
                print(f"[FAIL] {url_path}: {e}")

        await browser.close()

        print(f"\n{'='*60}")
        print(f"Screenshot complete: {success} success, {failed} failed")
        if errors:
            print(f"\nFailed pages:")
            for path, err in errors:
                print(f"  {path}: {err}")


if __name__ == "__main__":
    asyncio.run(main())
