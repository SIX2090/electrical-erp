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
    boundary = read("docs/phase3_procurement_closure_boundary.md")
    procurement_routes = read("routes/procurement_routes.py")
    suggestions_template = read("templates/purchase_suggestions.html")
    registry = read("routes/registry.py")
    project_routes = read("routes/project_routes.py")
    trace_template = read("templates/project_trace_detail.html")

    closure_routes = [
        "/api/project-machine-ledger/machine/<path:serial_no>/procurement-closure",
        "/api/project-machine-ledger/project/<path:project_code>/procurement-closure",
        "/api/project-machine-ledger/order/<int:order_id>/procurement-closure",
    ]
    closure_route_text = "\n".join(route_block(project_routes, route) for route in closure_routes)

    checks = [
        require(
            "boundary_documented",
            all(
                token in boundary
                for token in (
                    "engineering-ready shortages",
                    "purchase request",
                    "purchase order",
                    "receipt/inventory",
                    "supplier payable",
                    "Acceptance",
                )
            ),
            "phase 3 procurement closure boundary is documented before code",
        ),
        require(
            "purchase_suggestion_engineering_gate",
            all(
                token in procurement_routes
                for token in (
                    "_engineering_ready_sql",
                    "engineering_ready",
                    "工程未就绪",
                    "technical_confirmation_link",
                    "project_ledger_link",
                    "blocked_reason",
                )
            ),
            "purchase suggestions expose engineering readiness, blocker, and drill-down links",
        ),
        require(
            "purchase_suggestion_template",
            all(
                token in suggestions_template
                for token in ("工程准备", "已就绪", "未就绪", "技术确认", "项目台账")
            ),
            "purchase suggestion list shows engineering readiness instead of hiding the blocker",
        ),
        require(
            "suggestion_create_blocks_unready",
            all(
                token in registry
                for token in (
                    "_project_engineering_readiness",
                    "blocked_engineering",
                    'row.get("engineering_ready")',
                    "工程准备未就绪",
                    "不能生成采购申请",
                )
            ),
            "bulk and project shortage purchase-request creation block engineering-not-ready rows",
        ),
        require(
            "project_lifecycle_procurement_events",
            all(
                token in project_routes
                for token in (
                    'event_type="purchase_request"',
                    'event_type="purchase_receipt"',
                    'event_type="supplier_payable"',
                    'url_prefix="/purchase_request"',
                    'url_prefix="/purchase_receipts"',
                    'url_prefix="/payables"',
                )
            ),
            "project/machine lifecycle event stream includes request, receipt, and supplier payable",
        ),
        require(
            "project_lifecycle_template_labels",
            all(
                token in trace_template
                for token in ("purchase_request", "采购申请", "purchase_receipt", "采购入库", "supplier_payable", "供应商应付")
            ),
            "project ledger detail labels procurement closure events clearly",
        ),
        require(
            "procurement_closure_payload",
            all(
                token in project_routes
                for token in (
                    "_project_axis_procurement_closure_payload",
                    "shortage_line_count",
                    "purchase_request_count",
                    "purchase_order_count",
                    "pending_receipt_qty",
                    "purchase_receipt_count",
                    "supplier_payable_count",
                    "payable_balance",
                    '"blocked_reason": blocked_reason',
                    '"next_action": next_action',
                    '"owner_role": owner_role',
                )
            ),
            "read-only payload exposes closure counts, status, blocker, owner, and next action",
        ),
        require(
            "procurement_closure_routes",
            all(route in project_routes for route in closure_routes),
            "machine, project, and order procurement-closure APIs exist",
        ),
        require(
            "procurement_closure_routes_readonly",
            closure_route_text
            and "@app.post" not in closure_route_text
            and "execute_db" not in closure_route_text
            and "INSERT INTO" not in closure_route_text
            and "UPDATE " not in closure_route_text,
            "procurement-closure APIs are GET-only and do not write business documents",
        ),
        require(
            "no_new_procurement_menu",
            "/api/project-machine-ledger/order/<int:order_id>/procurement-closure" in project_routes
            and "procurement-closure" not in read("services/pilot_permissions.py"),
            "phase 3 adds read-only APIs without adding a new normal-user menu or permission surface",
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
