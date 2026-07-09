from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(rel_path):
    return (ROOT / rel_path).read_text(encoding="utf-8")


def main():
    boundary = read("ERP_BOUNDARY_STABILIZATION.md")
    routes = read("routes/project_cost_routes.py")
    template = read("templates/project_cost_report.html")
    visible_text_source = routes + template

    checks = [
        (
            "boundary_defined",
            "Agent 5 Project And Machine Cost Closure Boundary" in boundary
            and "Upstream source documents" in boundary
            and "Target document" in boundary
            and "Status transition" in boundary
            and "Blocked reason" in boundary
            and "Next action" in boundary
            and "Downstream impact" in boundary,
        ),
        (
            "read_only_report_routes",
            "@app.get(\"/finance/reports/project-cost\"" in routes
            and "@app.get(\"/finance/reports/machine-cost\"" in routes
            and "@app.post(" not in routes
            and "INSERT INTO" not in routes
            and "UPDATE " not in routes
            and "DELETE FROM" not in routes,
        ),
        (
            "cost_sources_complete",
            all(
                marker in routes
                for marker in [
                    "采购材料成本",
                    "委外加工成本",
                    "工单实际成本",
                    "库存出库成本",
                    "售后服务成本",
                    "销售收入参考",
                    "standard_amount",
                    "variance_amount",
                    "period_status",
                ]
            ),
        ),
        (
            "operator_columns_visible",
            all(
                marker in template
                for marker in [
                    "标准成本",
                    "实际成本",
                    "成本差异",
                    "委外成本",
                    "售后成本",
                    "阻塞原因",
                    "下一步",
                    "下游影响",
                    "期间结转准备",
                    "本页不修改单据状态、库存成本或财务分录",
                ]
            ),
        ),
        (
            "no_statutory_finance_expansion",
            "自动过账" not in routes
            and "总账凭证" in template
            and "不改总账" in routes,
        ),
        (
            "clean_chinese_text",
            not any(marker in visible_text_source for marker in [chr(0xFFFD), chr(63) * 3, chr(0x9422), chr(0x95BF)]),
        ),
    ]

    failures = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{name}={'ok' if ok else 'failed'}")
    if failures:
        raise SystemExit("project_machine_cost_boundary_audit=failed: " + ", ".join(failures))
    print("project_machine_cost_boundary_audit=ok")


if __name__ == "__main__":
    main()
