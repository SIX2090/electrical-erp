from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(rel_path):
    return (ROOT / rel_path).read_text(encoding="utf-8")


def main():
    routes = read("routes/after_sale_routes.py")
    service_template = read("templates/service_order_trace_detail.html")
    card_template = read("templates/service_card_trace_detail.html")
    special_lists = read("routes/special_list_routes.py")

    checks = [
        (
            "workbench_uses_pending_queues",
            "售后待办队列" in routes and "售后异常" in routes,
        ),
        (
            "workbench_not_full_document_lists",
            "服务单闭环队列" not in routes and "ORDER BY so.id DESC\n        LIMIT 30" not in routes,
        ),
        (
            "service_parts_stock_check_visible",
            "可用库存" in service_template and "js-stock-hint" in service_template and "短缺" in service_template,
        ),
        (
            "service_cost_finance_basis_visible",
            "售后成本与财务关联" in service_template
            and "parts_cost + labor_cost + travel_cost" in routes
            and "/finance/reports/project-cost" in service_template,
        ),
        (
            "return_visit_score_visible",
            "satisfaction_score" in service_template
            and "satisfaction_score" in card_template
            and "satisfaction_score" in special_lists,
        ),
    ]

    failures = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{name}={'ok' if ok else 'failed'}")
    if failures:
        raise SystemExit("after_sale_boundary_audit=failed: " + ", ".join(failures))
    print("after_sale_boundary_audit=ok")


if __name__ == "__main__":
    main()
