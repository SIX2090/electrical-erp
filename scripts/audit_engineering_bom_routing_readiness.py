from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def require(name: str, condition: bool, detail: str) -> tuple[str, bool, str]:
    return name, condition, detail


def main() -> int:
    boundary = read("ERP_BOUNDARY_STABILIZATION.md")
    migrations = read("services/schema_migrations.py")
    route = read("routes/engineering_confirmation_routes.py")
    form = read("templates/engineering_technical_confirmation_form.html")
    detail = read("templates/engineering_technical_confirmation_detail.html")
    listing = read("templates/engineering_technical_confirmation_list.html")
    classification = read("MENU_ROLLOUT_CLASSIFICATION.md")
    combined = "\n".join([boundary, migrations, route, form, detail, listing, classification])

    required_columns = [
        "process_program_no",
        "tooling_requirement",
        "inspection_standard",
        "ecn_impact_summary",
    ]
    readiness_tokens = [
        "BOM存在未关闭ECN影响",
        "缺少检验标准",
        "缺少加工程序号或不适用说明",
        "缺少工装夹具要求或不适用说明",
    ]
    boundary_tokens = [
        "Engineering/BOM/Routing Readiness Boundary",
        "Source document",
        "Target document",
        "Status transition",
        "Blocked reason",
        "Downstream impact",
        "Acceptance checks",
    ]

    checks = [
        require("boundary_defined", all(token in boundary for token in boundary_tokens), "boundary document records the required business loop fields"),
        require("no_finance_scope", "/finance" not in boundary.split("## Engineering/BOM/Routing Readiness Boundary", 1)[-1].split("## ", 1)[0], "engineering boundary does not add finance routes"),
        require("schema_columns", all(column in migrations for column in required_columns), "schema migration adds engineering readiness fields"),
        require("route_ensures_columns", "_ensure_engineering_confirmation_readiness_columns" in route and all(column in route for column in required_columns), "route layer ensures fields for existing local databases"),
        require("form_fields", all(column in form for column in required_columns), "document entry exposes process program, tooling, inspection, and ECN impact fields"),
        require("list_visibility", all(column in listing for column in ("process_program_no", "tooling_requirement", "inspection_standard", "执行准备度")), "document list exposes readiness basis"),
        require("detail_visibility", all(column in detail for column in ("process_program_no", "tooling_requirement", "inspection_standard", "ecn_impact_summary", "下游影响")), "document detail exposes readiness and downstream impact"),
        require("readiness_gate", all(token in route for token in readiness_tokens), "confirmation gate blocks incomplete engineering readiness"),
        require("ecn_gate", "bom_engineering_changes" in route and "NOT IN ('closed', 'voided')" in route, "open BOM ECN impact blocks confirmation"),
        require("page_classification_kept", "/engineering/technical-confirmations" in classification and "/production-routings" in classification and "/work-centers" in classification, "existing engineering/BOM/routing routes remain classified"),
        require("no_new_module", "PLM" in boundary and "must not become" in boundary and "/engineering/plm" not in combined, "scope is not expanded into a generic PLM/PDM module"),
    ]

    failures = [check for check in checks if not check[1]]
    print("engineering_bom_routing_readiness_audit=ok" if not failures else "engineering_bom_routing_readiness_audit=failed")
    print(f"checked_items={len(checks)}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
