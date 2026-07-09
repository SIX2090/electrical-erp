from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative):
    return (ROOT / relative).read_text(encoding="utf-8", errors="replace")


def check(name, ok, detail):
    return {"name": name, "ok": bool(ok), "detail": detail}


def main():
    dashboard = read("templates/inventory_dashboard.html")
    transactions = read("templates/inventory_transactions.html")
    report = read("templates/module_report.html")
    adjustment = read("templates/inventory_adjustment_form.html")
    detail = read("templates/inventory_document_detail.html")
    inventory_routes = read("routes/inventory_routes.py")
    special_lists = read("routes/special_list_routes.py")

    checks = [
        check(
            "workbench_no_full_balance_list",
            "库存余额" not in dashboard and "最近库存流水" not in dashboard and "批次/机号结余" not in dashboard,
            "库存工作台不得渲染完整库存明细、流水或批次列表",
        ),
        check(
            "negative_stock_policy_visible",
            "allow_negative_stock" in dashboard and "负库存" in dashboard and "allow_negative_stock" in inventory_routes,
            "负库存风险必须清楚提示 allow_negative_stock 状态",
        ),
        check(
            "check_difference_analysis",
            "difference_summary" in detail and "profit_qty" in inventory_routes and "loss_qty" in inventory_routes,
            "盘点单详情需显示盘盈、盘亏和差异金额",
        ),
        check(
            "adjustment_reason_required",
            'name="remark"' in adjustment and "required" in adjustment and "调整原因必填" in adjustment,
            "调整单原因/备注必填并提示审批状态",
        ),
        check(
            "transaction_summary_entry",
            "/inventory/reports/inout-summary" in transactions and "/inventory/reports/ledger" in transactions,
            "库存流水需提供按物料/仓库/期间汇总入口",
        ),
        check(
            "report_big_data_hint",
            "大数据量库存报表" in report and "避免加载重图表" in report,
            "库存报表需提示筛选和避免重图表",
        ),
        check(
            "list_prompt_updates",
            "\\u76d8\\u70b9\\u5dee\\u5f02" in special_lists and "\\u8c03\\u6574\\u539f\\u56e0" in special_lists and "\\u5ba1\\u6279" in special_lists,
            "盘点/调整列表需提示差异分析和审批原因",
        ),
    ]
    failed = [item for item in checks if not item["ok"]]
    print(f"checked_items={len(checks)}")
    for item in checks:
        status = "ok" if item["ok"] else "FAIL"
        print(f"{status} {item['name']}: {item['detail']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
