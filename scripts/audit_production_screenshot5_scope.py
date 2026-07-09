import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def main():
    checks = []
    production_routes = _read("routes/production_routes.py")
    requisition_template = _read("templates/work_order_requisition.html")
    detail_template = _read("templates/work_order_trace_detail.html")

    checks.append(("workbench_queue_title", "生产待办与异常队列" in production_routes))
    checks.append(("workbench_not_full_list", "不是完整工单列表" in production_routes))
    checks.append(("workbench_has_no_full_material_lines", "material_lines" not in production_routes[production_routes.find("def render_production_dashboard"):production_routes.find("def render_work_order_list")]))
    checks.append(("stage_has_scheduling_waiting_pause", '("创建", "排产", "待料", "投产", "加工", "暂停", "装配", "调试", "入库")' in production_routes))
    checks.append(("kit_result_in_requisition", "齐套结果" in requisition_template and "缺料" in requisition_template))
    checks.append(("reporting_entry_visible", "工序完工汇报" in detail_template and "报工数量" in detail_template))
    checks.append(("cost_detail_visible", "工单成本明细" in detail_template and "材料/委外/人工/制造费用" in production_routes))
    checks.append(("schedule_compare_visible", "计划/实际对比" in production_routes and "order.schedule_compare" in detail_template))

    failures = [name for name, ok in checks if not ok]
    print("production_screenshot5_scope_audit=ok" if not failures else "production_screenshot5_scope_audit=failed")
    for name, ok in checks:
        print(f"{'ok' if ok else 'failed'} | {name}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
