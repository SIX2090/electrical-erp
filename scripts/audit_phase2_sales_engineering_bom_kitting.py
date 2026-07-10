from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def require(name: str, ok: bool, detail: str) -> tuple[str, bool, str]:
    return name, ok, detail


def main() -> int:
    project_routes = read("routes/project_routes.py")
    trace_template = read("templates/project_trace_detail.html")
    confirmation_routes = read("routes/engineering_confirmation_routes.py")
    confirmation_form = read("templates/engineering_technical_confirmation_form.html")
    confirmation_list = read("templates/engineering_technical_confirmation_list.html")
    confirmation_detail = read("templates/engineering_technical_confirmation_detail.html")
    app_text = read("app.py")
    help_service = read("services/erp_help_service.py")
    boundary = read("docs/phase2_sales_engineering_bom_kitting_boundary.md")

    readiness_routes = [
        "/api/project-machine-ledger/machine/<path:cabinet_no>/engineering-readiness",
        "/api/project-machine-ledger/project/<path:project_code>/engineering-readiness",
        "/api/project-machine-ledger/order/<int:order_id>/engineering-readiness",
    ]
    readiness_route_text = "\n".join(
        line for line in project_routes.splitlines() if "engineering-readiness" in line
    )

    checks = [
        require(
            "boundary_documented",
            all(
                token in boundary
                for token in (
                    "sales order to engineering technical confirmation",
                    "Business Loop",
                    "read-only JSON readiness data",
                    "Acceptance",
                )
            ),
            "phase 2 loop boundary is documented before code",
        ),
        require(
            "shared_readiness_payload",
            "_project_axis_engineering_readiness_payload" in project_routes
            and "_project_engineering_readiness(query_one, order, kit_summary)" in project_routes,
            "readiness payload reuses the existing project-axis readiness calculation",
        ),
        require(
            "readiness_routes",
            all(route in project_routes for route in readiness_routes),
            "order, project-code, and machine-cabinet readiness APIs exist",
        ),
        require(
            "readiness_routes_readonly",
            "@app.post" not in readiness_route_text and "execute_db" not in readiness_route_text,
            "readiness APIs are GET-only and do not write business documents",
        ),
        require(
            "readiness_payload_fields",
            all(
                token in project_routes
                for token in (
                    '"engineering_readiness": readiness',
                    '"kit_summary": kit_summary',
                    '"next_action": readiness.get("next_action")',
                    '"owner_role": readiness.get("owner_role")',
                    '"blocked_reason": readiness.get("blocked_reason")',
                )
            ),
            "readiness API exposes status, owner, blocker, next action, and kitting basis",
        ),
        require(
            "technical_confirmation_events",
            all(
                token in project_routes
                for token in (
                    "FROM engineering_technical_confirmations",
                    'event_type="technical_confirmation"',
                    'url_prefix="/engineering/technical-confirmations"',
                )
            )
            and "technical_confirmation" in trace_template,
            "lifecycle event stream includes technical confirmation documents",
        ),
        require(
            "project_detail_readiness_ui",
            all(
                token in trace_template
                for token in (
                    "engineering_readiness.ready",
                    "engineering_readiness.confirmation",
                    "engineering_readiness.released_drawing",
                    "engineering_readiness.blocked_reason",
                    "/engineering/technical-confirmations/new?sales_order_id={{ order.id }}",
                )
            ),
            "project ledger detail exposes engineering readiness and the proper entry link",
        ),
        require(
            "technical_confirmation_prefill",
            all(
                token in confirmation_routes + confirmation_form
                for token in (
                    "_prefill_confirmation_from_sales_order",
                    "sales_order_id",
                    "project_code",
                    "cabinet_no",
                    "drawing_no",
                    "drawing_version",
                    "bom_id",
                )
            ),
            "technical confirmation entry can be prefilled from sales order context",
        ),
        require(
            "technical_confirmation_reference_validation",
            all(
                token in confirmation_routes
                for token in (
                    "_validate_confirmation_references",
                    "BOM不属于当前产品/机型",
                    "BOM没有明细",
                    "工艺路线不属于当前产品/机型",
                    "图纸版本不是已发布有效版本",
                )
            ),
            "technical confirmation save validates BOM, routing, BOM lines, and released drawing version",
        ),
        require(
            "technical_confirmation_reference_filtering",
            all(
                token in confirmation_form
                for token in (
                    "data-product-id",
                    "filterByProduct",
                    "bomSelect",
                    "routingSelect",
                    "已按当前产品/机型筛选",
                )
            ),
            "technical confirmation entry filters BOM and routing options by selected product",
        ),
        require(
            "technical_confirmation_detail_readiness",
            all(
                token in confirmation_routes + confirmation_detail
                for token in (
                    "_confirmation_execution_readiness",
                    "bom_item_count",
                    "released_drawing_id",
                    "下游执行状态",
                    "BOM明细",
                    "图纸有效性",
                    "项目/柜号台账",
                )
            ),
            "technical confirmation detail exposes locked-material readiness and ledger drill-down",
        ),
        require(
            "technical_confirmation_list_readiness",
            all(
                token in confirmation_routes + confirmation_list
                for token in (
                    "item[\"execution_readiness\"]",
                    "执行准备度",
                    "BOM明细",
                    "图纸有效",
                    "台账",
                )
            ),
            "technical confirmation list shows execution readiness and project ledger drill-down",
        ),
        require(
            "technical_confirmation_confirm_guard",
            all(
                token in confirmation_routes
                for token in (
                    "reference_errors = _validate_confirmation_references",
                    "不能确认：",
                    "BOM没有明细",
                    "图纸版本不是已发布有效版本",
                )
            ),
            "technical confirmation action revalidates references before confirmation",
        ),
        require(
            "engineering_alert_api",
            all(
                token in project_routes
                for token in (
                    "/api/project-machine-ledger/engineering-readiness/alerts",
                    "project_engineering_readiness_alerts_api",
                    "technical_confirmation_url",
                    "blocked_reason",
                    "owner_role",
                )
            ),
            "engineering readiness exposes a read-only alert queue for warning surfaces",
        ),
        require(
            "assistant_context_api",
            all(
                token in project_routes
                for token in (
                    "/api/project-machine-ledger/assistant-context",
                    "_project_axis_assistant_context",
                    "assistant_guidance",
                    "AI助手只解释和引导",
                )
            ),
            "project ledger exposes read-only assistant context by project, machine, or order keyword",
        ),
        require(
            "topbar_engineering_warning",
            all(
                token in app_text
                for token in (
                    "engineering_not_ready",
                    "工程准备未就绪",
                    "/engineering/technical-confirmations",
                    "技术确认、BOM、图纸或齐套仍有缺口",
                )
            ),
            "topbar warning includes engineering readiness blockers without adding a new module",
        ),
        require(
            "ai_manual_engineering_guidance",
            all(
                token in help_service
                for token in (
                    "engineering_readiness",
                    "工程准备",
                    "技术确认单",
                    "/api/project-machine-ledger/engineering-readiness/alerts",
                    "AI助手可以按项目号、柜号或销售订单号读取工程准备上下文",
                )
            ),
            "AI operation helper includes machine-tool engineering readiness guidance",
        ),
        require(
            "no_new_menu_scope",
            'href="/api/project-machine-ledger' not in trace_template,
            "new APIs are not exposed as normal ERP menus or shortcut pages",
        ),
    ]

    failures = [item for item in checks if not item[1]]
    print("phase2_sales_engineering_bom_kitting_audit=ok" if not failures else "phase2_sales_engineering_bom_kitting_audit=failed")
    print(f"checked_items={len(checks)}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
