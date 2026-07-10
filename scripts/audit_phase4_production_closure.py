from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def require(name: str, ok: bool, detail: str) -> tuple[str, bool, str]:
    return name, ok, detail


def route_block(source: str, route: str) -> str:
    marker = f'@app.get("{route}"'
    start = source.find(marker)
    if start < 0:
        return ""
    next_route = source.find("\n    @app.", start + len(marker))
    return source[start:] if next_route < 0 else source[start:next_route]


def main() -> int:
    boundary = read("docs/phase4_production_closure_boundary.md")
    cost_service = read("services/work_order_cost_service.py")
    pick_routes = read("routes/production_pick_routes.py")
    completion_routes = read("routes/production_completion_routes.py")
    project_routes = read("routes/project_routes.py")
    trace_template = read("templates/project_trace_detail.html")
    permissions = read("services/pilot_permissions.py")

    closure_routes = [
        "/api/project-machine-ledger/machine/<path:cabinet_no>/production-closure",
        "/api/project-machine-ledger/project/<path:project_code>/production-closure",
        "/api/project-machine-ledger/order/<int:order_id>/production-closure",
    ]
    closure_route_text = "\n".join(route_block(project_routes, route) for route in closure_routes)

    checks = [
        require(
            "boundary_documented",
            all(
                token in boundary
                for token in (
                    "Work order",
                    "material issue",
                    "completion inbound",
                    "work order cost collection",
                    "project and machine ledger",
                    "Out Of Scope",
                )
            ),
            "phase 4 production closure boundary is documented before code",
        ),
        require(
            "cost_service_schema_and_sync",
            all(
                token in cost_service
                for token in (
                    "sync_work_order_costs",
                    "ensure_work_order_cost_schema",
                    "work_order_costs",
                    "work_order_cost_lines",
                    "工单领料",
                    "工单退料",
                    "完工入库",
                    "DELETE FROM work_order_cost_lines",
                )
            ),
            "cost sync service creates schema and regenerates controlled system cost lines idempotently",
        ),
        require(
            "production_pick_cost_sync",
            "from services.work_order_cost_service import sync_work_order_costs" in pick_routes
            and "sync_work_order_costs(" in pick_routes
            and "UPDATE wo_material_items SET issued_qty" in pick_routes
            and "UPDATE wo_material_items SET returned_qty" in pick_routes,
            "production issue and return posting updates work-order material quantities and syncs costs",
        ),
        require(
            "production_completion_cost_sync",
            "from services.work_order_cost_service import sync_work_order_costs" in completion_routes
            and completion_routes.count("sync_work_order_costs(") >= 2
            and "INSERT INTO wo_complete_items" in completion_routes
            and "reverse_posted_at=NOW()" in completion_routes,
            "completion post and reverse-post both update completion rows and resync costs",
        ),
        require(
            "project_lifecycle_production_events",
            all(
                token in project_routes
                for token in (
                    'event_type="production_issue"',
                    'event_type="production_return"',
                    'event_type="production_completion"',
                    'event_type="work_order_cost"',
                    'url_prefix="/production-issues"',
                    'url_prefix="/production-returns"',
                    'url_prefix="/production-completions"',
                )
            ),
            "project/machine lifecycle event stream includes issue, return, completion, and cost events",
        ),
        require(
            "project_lifecycle_template_labels",
            all(
                token in trace_template
                for token in (
                    "production_issue",
                    "生产领料",
                    "production_return",
                    "生产退料",
                    "production_completion",
                    "完工入库",
                    "work_order_cost",
                    "工单成本",
                )
            ),
            "project ledger detail labels production closure events clearly",
        ),
        require(
            "production_closure_payload",
            all(
                token in project_routes
                for token in (
                    "_project_axis_production_closure_payload",
                    "work_order_count",
                    "pending_issue_qty",
                    "issue_doc_count",
                    "return_doc_count",
                    "completion_doc_count",
                    "cost_line_count",
                    "total_cost",
                    "blocked_reason",
                    "next_action",
                    "owner_role",
                )
            ),
            "read-only payload exposes closure counts, status, blocker, owner, and next action",
        ),
        require(
            "production_closure_routes",
            all(route in project_routes for route in closure_routes),
            "machine, project, and order production-closure APIs exist",
        ),
        require(
            "production_closure_routes_readonly",
            closure_route_text
            and "@app.post" not in closure_route_text
            and "execute_db" not in closure_route_text
            and "INSERT INTO" not in closure_route_text
            and "UPDATE " not in closure_route_text,
            "production-closure APIs are GET-only and do not write business documents",
        ),
        require(
            "no_new_production_menu",
            "production-closure" not in permissions,
            "phase 4 adds read-only APIs without adding a new normal-user menu or permission surface",
        ),
    ]

    failed = False
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        print(f"{status} {name}: {detail}")
        failed = failed or not ok
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
