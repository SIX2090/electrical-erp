from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def require(name: str, ok: bool, detail: str) -> tuple[str, bool, str]:
    return name, ok, detail


def main() -> int:
    boundary = read("docs/phase5_delivery_outsourcing_service_boundary.md")
    project_routes = read("routes/project_routes.py")
    registry = read("routes/registry.py")
    trace_template = read("templates/project_trace_detail.html")
    permissions = read("services/pilot_permissions.py")
    verifier = read("scripts/verify_phase5_delivery_outsourcing_service_loops.py")

    checks = [
        require(
            "boundary_documented",
            all(
                token in boundary
                for token in (
                    "Sales Delivery Loop",
                    "Outsourcing Loop",
                    "Service Loop",
                    "Out Of Scope",
                    "No offline installer generation",
                )
            ),
            "phase 5 boundary is documented before ERP code changes",
        ),
        require(
            "project_lifecycle_outsourcing_events",
            all(
                token in project_routes
                for token in (
                    'event_type="subcontract_issue"',
                    'event_type="subcontract_receive"',
                    'url_prefix="/subcontract_issue"',
                    'url_prefix="/subcontract_receive"',
                )
            ),
            "project ledger includes subcontract issue and receive events",
        ),
        require(
            "project_lifecycle_service_events",
            all(
                token in project_routes
                for token in (
                    'event_type="service_card"',
                    'event_type="service_acceptance"',
                    'event_type="service_order"',
                    'event_type="service_rma"',
                    'url_prefix="/service-cards"',
                    'url_prefix="/service-acceptance"',
                )
            ),
            "project ledger includes service card, acceptance, service order, and RMA events",
        ),
        require(
            "project_lifecycle_template_labels",
            all(
                token in trace_template
                for token in (
                    "subcontract_issue",
                    "subcontract_receive",
                    "service_card",
                    "service_acceptance",
                )
            ),
            "project trace detail labels all phase 5 event types",
        ),
        require(
            "subcontract_receive_cost_sync",
            "from services.work_order_cost_service import sync_work_order_costs" in registry
            and "parent_work_order_id" in registry
            and 'source_type="subcontract_receive"' in registry
            and "sync_work_order_costs(" in registry,
            "subcontract receive audit refreshes work-order cost when linked to a parent work order",
        ),
        require(
            "runtime_verifier_covers_three_loops",
            all(
                token in verifier
                for token in (
                    "sales_delivery_loop",
                    "outsourcing_loop",
                    "service_loop",
                    "/sales/",
                    "/subcontract_issue/new",
                    "/subcontract_receive/new",
                    "/service-acceptance/new",
                    "/service-orders/new",
                    "/service-rmas/new",
                    "_project_axis_events",
                )
            ),
            "runtime verifier covers sales, outsourcing, service, and project ledger events",
        ),
        require(
            "no_new_phase5_menu",
            "phase5" not in permissions.lower()
            and "delivery_outsourcing_service" not in permissions,
            "phase 5 does not add a new normal-user menu or permission surface",
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
