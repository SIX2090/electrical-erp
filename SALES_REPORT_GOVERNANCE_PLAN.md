# Sales Report Governance Plan

## Final Integration Update

Final integration completed after the six-agent implementation split.

- `/sales/reports` is now a role-protected sales report center.
- 20 concrete sales report paths are registered once, through dedicated read-only sales report handlers.
- The generic report-section registration and legacy report-route fallback now skip real sales report paths to avoid duplicate Flask rules.
- `/sales/reports/return-impact-analysis` remains hidden/unregistered because no verified read-only return impact service was delivered in this implementation round.
- Sales report access model is `admin`, `manager`, and `sales`; unrelated roles are denied by direct access checks.
- Route catalog, pilot permissions, navigation, and rollout classification were updated for the implemented live reports.

Verified final state:

- `sales_report_rule_count=21`
- `duplicates={}`
- Admin and sales users receive HTTP 200 for `/sales/reports` plus the 20 live report paths.
- Warehouse and finance users receive HTTP 403 for those sales report paths.

## Scope

Agent 6 owns report platform governance only:

- Route inventory and duplicate-route cleanup plan.
- Permission, navigation, catalog, and rollout-classification gap list.
- Acceptance commands for final integration.

This plan does not implement business report SQL, change posting logic, add database fields, or edit route, permission, navigation, or audit-script code.

## Current Sales Report Path Inventory

Source of the full report list: `routes/report_routes.py` under the `sales` report section.

| Path | Current status | Current owner | Notes |
|---|---|---|---|
| `/sales/reports` | Generic module center | `routes/report_route_registration.py` | Read-only report center page for sales report links. |
| `/sales/reports/pending` | Generic placeholder | `routes/report_routes.py` + `routes/report_route_registration.py` | In navigation and sales permission group, but not a real business query. |
| `/sales/reports/customer-ranking` | Generic placeholder | `routes/report_routes.py` + `routes/report_route_registration.py` | In navigation and sales permission group, but not a real business query. |
| `/sales/reports/execution` | Generic placeholder | `routes/report_routes.py` + `routes/report_route_registration.py` | In navigation and sales permission group, but not a real business query. |
| `/sales/reports/summary` | Generic placeholder | `routes/report_routes.py` + `routes/report_route_registration.py` | Missing permission, navigation, route catalog, and rollout classification. |
| `/sales/reports/order-execution-detail` | Real implementation, but duplicate registered | `routes/sales_report_routes.py` | Also present in generic report sections and report catalog registration. |
| `/sales/reports/order-execution-summary` | Generic placeholder | `routes/report_routes.py` + `routes/report_route_registration.py` | Missing permission, navigation, route catalog, and rollout classification. |
| `/sales/reports/project-serial-order-tracking` | Real implementation, but duplicate registered | `routes/sales_report_routes.py` | Also present in generic report sections and report catalog registration. |
| `/sales/reports/shipment-execution-detail` | Generic placeholder | `routes/report_routes.py` + `routes/report_route_registration.py` | Missing permission, navigation, route catalog, and rollout classification. |
| `/sales/reports/shipped-unsettled-detail` | Real implementation, but duplicate registered | `routes/sales_report_routes.py` | Also present in generic report sections and report catalog registration. |
| `/sales/reports/customer-open-order-analysis` | Generic placeholder | `routes/report_routes.py` + `routes/report_route_registration.py` | Missing permission, navigation, route catalog, and rollout classification. |
| `/sales/reports/project-serial-open-order-analysis` | Generic placeholder | `routes/report_routes.py` + `routes/report_route_registration.py` | Missing permission, navigation, route catalog, and rollout classification. |
| `/sales/reports/invoice-execution-detail` | Generic placeholder | `routes/report_routes.py` + `routes/report_route_registration.py` | Missing permission, navigation, route catalog, and rollout classification. |
| `/sales/reports/invoice-summary` | Generic placeholder | `routes/report_routes.py` + `routes/report_route_registration.py` | Missing permission, navigation, route catalog, and rollout classification. |
| `/sales/reports/receivable-collection-detail` | Generic placeholder | `routes/report_routes.py` + `routes/report_route_registration.py` | Missing permission, navigation, route catalog, and rollout classification. |
| `/sales/reports/receivable-aging` | Real implementation, but duplicate registered | `routes/sales_report_routes.py` | Also present in generic report sections and report catalog registration. |
| `/sales/reports/project-serial-gross-margin` | Generic placeholder | `routes/report_routes.py` + `routes/report_route_registration.py` | Missing permission, navigation, route catalog, and rollout classification. |
| `/sales/reports/price-execution-analysis` | Generic placeholder | `routes/report_routes.py` + `routes/report_route_registration.py` | Missing permission, navigation, route catalog, and rollout classification. |
| `/sales/reports/return-impact-analysis` | Generic placeholder | `routes/report_routes.py` + `routes/report_route_registration.py` | Missing permission, navigation, route catalog, and rollout classification. |
| `/sales/reports/delivery-delay-analysis` | Generic placeholder | `routes/report_routes.py` + `routes/report_route_registration.py` | Missing permission, navigation, route catalog, and rollout classification. |
| `/sales/reports/operation-snapshot` | Generic placeholder | `routes/report_routes.py` + `routes/report_route_registration.py` | Missing permission, navigation, route catalog, and rollout classification. |
| `/sales/reports/daily` | Generic placeholder | `routes/report_routes.py` + `routes/report_route_registration.py` | Missing permission, navigation, route catalog, and rollout classification. |

## Existing Real Implementations

These paths have dedicated HTTP handlers in `routes/sales_report_routes.py` and service-backed queries in `services/sales_report_service.py`:

- `/sales/reports/order-execution-detail`
- `/sales/reports/receivable-aging`
- `/sales/reports/project-serial-order-tracking`
- `/sales/reports/shipped-unsettled-detail`

They are already present in:

- `services/pilot_permissions.py`
- `routes/route_catalog.py`
- `MENU_ROLLOUT_CLASSIFICATION.md`
- `templates/base.html`

## Placeholder Routes Still Needing Real Implementation

The remaining sales report paths still render through the generic report center. They should not be declared live business reports until an owning Agent replaces them with real queries, templates, permissions, route catalog entries, and classification rows.

Agent ownership proposal:

| Agent | Paths |
|---|---|
| Agent 1, sales order reports | `/sales/reports/summary`, `/sales/reports/order-execution-summary`, `/sales/reports/customer-open-order-analysis`, `/sales/reports/project-serial-open-order-analysis` |
| Agent 2, shipment and shipped-goods reports | `/sales/reports/shipment-execution-detail` |
| Agent 3, invoice and tax invoice reports | `/sales/reports/invoice-execution-detail`, `/sales/reports/invoice-summary` |
| Agent 4, collection and receivable reports | `/sales/reports/receivable-collection-detail` |
| Agent 5, operation, margin, price, return, and delay reports | `/sales/reports/project-serial-gross-margin`, `/sales/reports/price-execution-analysis`, `/sales/reports/return-impact-analysis`, `/sales/reports/delivery-delay-analysis`, `/sales/reports/operation-snapshot`, `/sales/reports/daily` |
| Agent 6, governance only | `/sales/reports`, plus route de-duplication, permissions, navigation, catalog, rollout classification, and acceptance checks |

The current navigation-only placeholder paths are:

- `/sales/reports/pending`
- `/sales/reports/customer-ranking`
- `/sales/reports/execution`

These should either be replaced by real reports or removed from normal navigation during final integration. If retained, they need explicit rollout classification and permission/catelog consistency.

## Duplicate Route Risk

The following four real paths are registered multiple times:

- `/sales/reports/order-execution-detail`
- `/sales/reports/receivable-aging`
- `/sales/reports/project-serial-order-tracking`
- `/sales/reports/shipped-unsettled-detail`

Current observed URL map order:

1. Dedicated real handlers from `routes/sales_report_routes.py`.
2. Legacy report route entries from `routes/route_catalog.py` / `routes/data_route_registration.py`.
3. Generic report-section handlers from `routes/report_route_registration.py`.

This order currently lets the real handlers win. The risk remains high because duplicate exact paths make behavior dependent on registration order. Future route registration changes could silently switch a real report back to a generic placeholder.

Final integration should leave exactly one Flask rule per concrete sales report path.

## Recommended Final Route Registration Strategy

Use one of these strategies consistently:

### Preferred Strategy

- Keep `/sales/reports` as the module report center.
- Keep real concrete sales reports in `routes/sales_report_routes.py` or split them into dedicated route modules by Agent area.
- Remove any real concrete sales report path from the generic `REPORT_SECTIONS` list once it has a real implementation.
- Do not add real concrete sales report paths to `REPORT_ROUTES` if they already have dedicated handlers.
- Let the report center link to real routes, but do not register those same paths as generic section routes.

### Transitional Strategy

- Add a `REAL_REPORT_PATHS` exclusion set to `register_clean_report_routes`.
- Skip generic registration for paths owned by dedicated report modules.
- Keep the path in the report center metadata only as a link target, not as a generic route.

The preferred strategy is clearer and avoids hidden registration behavior.

## Permission Gaps

Currently covered in `services/pilot_permissions.py` sales group:

- `/sales/reports/pending`
- `/sales/reports/customer-ranking`
- `/sales/reports/execution`
- `/sales/reports/order-execution-detail`
- `/sales/reports/receivable-aging`
- `/sales/reports/project-serial-order-tracking`
- `/sales/reports/shipped-unsettled-detail`

Missing permission coverage if the remaining placeholders become real routes:

- `/sales/reports`
- `/sales/reports/summary`
- `/sales/reports/order-execution-summary`
- `/sales/reports/shipment-execution-detail`
- `/sales/reports/customer-open-order-analysis`
- `/sales/reports/project-serial-open-order-analysis`
- `/sales/reports/invoice-execution-detail`
- `/sales/reports/invoice-summary`
- `/sales/reports/receivable-collection-detail`
- `/sales/reports/project-serial-gross-margin`
- `/sales/reports/price-execution-analysis`
- `/sales/reports/return-impact-analysis`
- `/sales/reports/delivery-delay-analysis`
- `/sales/reports/operation-snapshot`
- `/sales/reports/daily`

Recommended access model:

- `admin`, `manager`, and `sales`: allowed.
- `finance`: allowed only for finance-owned receivable, invoice, and collection reconciliation reports if the business owner confirms cross-module access.
- `warehouse`, `production`, `purchase`, and unrelated roles: denied unless a specific cross-module report is deliberately exposed.

## Navigation Gaps

Current `templates/base.html` sales report navigation includes:

- `/sales/reports/pending`
- `/sales/reports/customer-ranking`
- `/sales/reports/execution`
- `/sales/reports/order-execution-detail`
- `/sales/reports/receivable-aging`
- `/sales/reports/project-serial-order-tracking`
- `/sales/reports/shipped-unsettled-detail`

Recommended final navigation shape:

- Add one stable entry for `/sales/reports` as the sales report center.
- Keep the normal left navigation short; avoid listing every report in the main menu.
- Inside the report center, group links by:
  - Sales order reports.
  - Shipment and shipped-goods reports.
  - Invoice and tax invoice reports.
  - Collection and receivable reports.
  - Project and serial trace reports.
  - Operation analysis reports.
- Do not expose generic placeholder routes in normal navigation.

## Route Catalog Gaps

Current `routes/route_catalog.py` includes only the four real sales report paths.

When a placeholder becomes a real report, add a route catalog entry for it with the closest read-only source table. Suggested mapping:

| Path | Suggested source table |
|---|---|
| `/sales/reports` | `sales_orders` |
| `/sales/reports/summary` | `sales_orders` |
| `/sales/reports/order-execution-summary` | `sales_orders` |
| `/sales/reports/shipment-execution-detail` | `sales_shipments` |
| `/sales/reports/customer-open-order-analysis` | `sales_orders` |
| `/sales/reports/project-serial-open-order-analysis` | `sales_orders` |
| `/sales/reports/invoice-execution-detail` | `sales_invoices` |
| `/sales/reports/invoice-summary` | `sales_invoices` |
| `/sales/reports/receivable-collection-detail` | `customer_receivables` |
| `/sales/reports/project-serial-gross-margin` | `sales_orders` |
| `/sales/reports/price-execution-analysis` | `sales_orders` |
| `/sales/reports/return-impact-analysis` | `sales_returns` |
| `/sales/reports/delivery-delay-analysis` | `sales_orders` |
| `/sales/reports/operation-snapshot` | `sales_orders` |
| `/sales/reports/daily` | `sales_orders` |

## Rollout Classification Gaps

Current `MENU_ROLLOUT_CLASSIFICATION.md` classifies only the four real reports as `live`.

Recommended classification before final release:

- Real implemented reports: `live`.
- Generic placeholders that remain reachable: `readonly` only if they clearly display placeholder/sample status and are not in normal navigation.
- Generic placeholders not ready for users: `hidden`.
- Do not classify a generic placeholder as `live`.

The following paths need classification once ownership is decided:

- `/sales/reports`
- `/sales/reports/pending`
- `/sales/reports/customer-ranking`
- `/sales/reports/execution`
- `/sales/reports/summary`
- `/sales/reports/order-execution-summary`
- `/sales/reports/shipment-execution-detail`
- `/sales/reports/customer-open-order-analysis`
- `/sales/reports/project-serial-open-order-analysis`
- `/sales/reports/invoice-execution-detail`
- `/sales/reports/invoice-summary`
- `/sales/reports/receivable-collection-detail`
- `/sales/reports/project-serial-gross-margin`
- `/sales/reports/price-execution-analysis`
- `/sales/reports/return-impact-analysis`
- `/sales/reports/delivery-delay-analysis`
- `/sales/reports/operation-snapshot`
- `/sales/reports/daily`

## Source Integrity Risk

`routes/sales_report_routes.py` currently contains mojibake in comments, docstrings, titles, and column labels. Agent 6 does not repair it in this governance-only patch, but final integration must repair or replace those corrupt literals before declaring the sales report work complete.

Do not add compatibility aliases that preserve corrupt Chinese literals.

## Acceptance Commands

Run after final integration, in order:

```powershell
.\.venv\Scripts\python.exe -m compileall app.py routes services scripts
.\.venv\Scripts\python.exe scripts\source_integrity_audit.py
.\.venv\Scripts\python.exe scripts\erp_prelaunch_audit.py
.\.venv\Scripts\python.exe scripts\audit_erp_crud_completeness.py
cmd /c "set INVENTORY_NAV_MODE=gt_pilot&& set PG_PASSWORD=admin&& .\.venv\Scripts\python.exe scripts\audit_trial_visible_navigation.py"
cmd /c "set INVENTORY_NAV_MODE=gt_pilot&& set PG_PASSWORD=admin&& .\.venv\Scripts\python.exe scripts\audit_trial_direct_access_matrix.py"
```

Additional sales report-specific checks:

```powershell
.\.venv\Scripts\python.exe - <<'PY'
from app import create_app

app = create_app()
sales_rules = {}
for rule in app.url_map.iter_rules():
    if rule.rule.startswith("/sales/reports"):
        sales_rules.setdefault(rule.rule, []).append(rule.endpoint)

duplicates = {path: endpoints for path, endpoints in sales_rules.items() if len(endpoints) > 1}
print("sales_report_duplicate_routes=", len(duplicates))
for path, endpoints in sorted(duplicates.items()):
    print(path, endpoints)
PY
```

Expected final duplicate count: `0`.

Runtime access matrix expected behavior:

- `admin`, `manager`, and `sales`: HTTP 200 for live sales report routes.
- Unrelated normal roles: HTTP 403 for sales-owned report routes.
- Hidden placeholder routes: not visible in navigation and not advertised as live.
