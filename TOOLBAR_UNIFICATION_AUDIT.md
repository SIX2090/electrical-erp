# Toolbar Unification Audit

Date: 2026-06-30
Scope: read-only audit of toolbar sources in `app.py`, `templates/`, and `routes/`.

## Boundary

This audit does not change application templates, routes, business logic, audit scripts, schema, permissions, or navigation.

The goal is to define acceptance rules for unified toolbars and identify the remaining cleanup items by page type:

- List pages
- Report/query pages
- Document entry pages
- Document detail pages
- Print-page exceptions

## Toolbar Sources Found

The current toolbar behavior is assembled from multiple sources:

1. `app.py`
   - Defines global toolbar actions by inferred page type.
   - Entry pages: new, save, save-and-new, refresh, return-to-list, print, extras, more.
   - Report pages: query, reset, refresh-report, print, more.
   - Workbench pages: refresh, more.
   - Detail pages: search/navigation, refresh, print, extras, more.
   - Other/list pages: filter, refresh, print, copy, more.

2. `templates/base.html`
   - Renders `globalOperationToolbar`.
   - Merges local `document_menu_bar` instances into the global toolbar.
   - Deduplicates by visible label.
   - Handles global events such as print, copy table, export table, submit form, copy document, delete document, void document, import, and batch.

3. `templates/partials/document_menu_bar.html`
   - Shared macro for local document/menu actions.
   - Supports buttons, links, nav groups, dropdowns, disabled items, and grouped "more" items.
   - Has default actions including tool/dropdown/export/refresh/exit style actions when no actions are passed.

4. `templates/simple_list.html`
   - Shared list page template.
   - Now relies on the global list toolbar for common list actions.
   - Still owns list-local filter form, import/template/bulk actions, row actions, and pagination.

5. `templates/module_report.html`
   - Shared module report template.
   - Imports `document_menu_bar` but does not render a local menu.
   - Has a stale `reportPrintMenuBtn` listener with no matching button in the template.

6. Route-level extras
   - `g.toolbar_extras` appears in route code and can inject page-specific actions into the global toolbar.
   - Found in `routes/inventory_routes.py`, `routes/production_completion_routes.py`, `routes/production_pick_routes.py`, and `routes/registry.py`.

## Counts

Template-level counts:

- Templates containing `document_menu_bar`: 106
- Templates containing direct `window.print()` or `exportReportTable`/table export logic, excluding `base.html`: 40
- Templates containing both `document_menu_bar` and direct print/export logic: 9
- Confirmed templates that may appear as "More/Tools only" or lack a full standard list toolbar: 2
- Confirmed print-page exceptions with direct print logic: 6

Route-level counts:

- `simple_list.html` render call sites: 26
- `module_report.html` render path references: 2
- `g.toolbar_extras` assignments/usages in route files: 15

## Acceptance Rules

### List Pages

Required common toolbar:

- Filter
- Refresh
- Print
- Copy table
- More

Allowed `More` items:

- Export Excel
- Export CSV
- Return home or other low-frequency navigation

Not allowed:

- A normal list page showing only `More` or only `Tools`.
- Duplicate filter/refresh/print buttons split across global and page-local toolbars.
- New-document creation embedded as the main list toolbar action unless the page is explicitly classified as document entry.
- Fake PDF export if the action only calls browser print.

### Report and Query Pages

Required common toolbar:

- Query
- Reset
- Refresh report
- Print
- More

Allowed `More` items:

- Real export actions only, such as Excel or CSV.
- Drill-down links only when they do not mutate business documents.

Not allowed:

- Create, submit, audit, post, void, or other document-write actions.
- Page-local print/export buttons when the global report toolbar already provides them.
- `Export PDF` if the implementation is only `window.print()`.
- Dead event handlers for missing buttons.

### Document Entry Pages

Required common toolbar:

- New
- Save
- Save and new, when the page supports continuing entry
- Refresh
- Return to list
- Print, only when meaningful before or after save
- More

Allowed `More` items:

- Copy document, delete, void, import, template, or batch actions only when the page has an explicit implementation and status rules.

Not allowed:

- Heavy document actions hidden only in a local card header while the global toolbar also exists.
- Report export or analysis actions.
- Row-grid actions promoted to the page-level toolbar.

### Document Detail Pages

Required common toolbar:

- Search or document navigation where applicable
- Refresh
- Print
- Status-aware actions, supplied either by global inference or `g.toolbar_extras`
- More

Allowed page body actions:

- Row-level drill-downs.
- Line-level actions inside a detail grid.
- Read-only source/target document links.

Not allowed:

- Duplicate page-level return, print, post, reverse-post, audit, reverse-audit, close, void, or copy actions in the body when the same action is available in the global toolbar.
- Local page action strips that compete with the global toolbar.

### Print Page Exceptions

Print-only templates may keep a visible print button and `window.print()`.

The exception applies only when the route is a dedicated print/preview page and not a normal list, report, entry, or detail page.

Confirmed print-page exception templates:

- `templates/check_print.html`
- `templates/document_print.html`
- `templates/print_template_preview.html`
- `templates/purchase_invoice_print.html`
- `templates/requisition_print.html`
- `templates/transfer_print.html`

## Remaining Issues

### P0 - List Pages Missing a Complete Standard Toolbar

Confirmed templates:

- `templates/operation_report_list.html`
- `templates/production_completion_list.html`

Problem:

- These are normal list pages but do not use `simple_list.html`.
- They rely on page-local shortcut links and/or global fallback behavior instead of an explicit standard list toolbar.
- They can appear functionally weaker than the unified list pattern, especially when only `More` or `Tools` remains visible at the top.

Acceptance:

- They should expose the standard list toolbar: filter, refresh, print, copy table, more.
- Their local shortcut links should remain secondary navigation, not the page toolbar.
- No document creation should be mixed into the list toolbar unless the page is reclassified as document entry.

### P1 - Report Pages Still Owning Local Print/Export

Templates with direct print/export logic that are not print-page exceptions:

- `templates/finance_aging_report.html`
- `templates/finance_detail_ledger.html`
- `templates/finance_general_ledger.html`
- `templates/financial_statements.html`
- `templates/module_report.html`
- `templates/project_cost_report.html`
- `templates/report_center.html`
- `templates/report_view.html`
- `templates/cost/variance.html`
- `templates/finance/account_balance_report.html`
- `templates/finance/account_detail_ledger.html`
- `templates/finance/balance_sheet.html`
- `templates/finance/cash_flow_statement.html`
- `templates/finance/income_statement.html`
- `templates/finance/inventory_cost_ledger.html`
- `templates/finance/inventory_ledger_reconciliation.html`
- `templates/finance/period_closing_check.html`
- `templates/finance/period_closing_history.html`
- `templates/finance/period_closing_home.html`
- `templates/finance/project_cost_detail.html`
- `templates/finance/project_cost_summary.html`
- `templates/finance/project_gross_profit.html`
- `templates/finance/purchase_invoice_reconciliation.html`
- `templates/finance/purchase_three_way_match.html`
- `templates/finance/sales_invoice_reconciliation.html`
- `templates/finance/sales_three_way_match.html`
- `templates/finance/serial_cost_summary.html`
- `templates/finance/serial_cost_variance.html`
- `templates/finance/trial_balance_report.html`
- `templates/finance/uninvoiced_sales.html`
- `templates/finance/unreceived_purchase_invoice.html`
- `templates/reports/generic_sales_report.html`
- `templates/reports/sales_receivable_reports.html`

Problem:

- These pages still contain local `window.print()` and/or `exportReportTable()` logic.
- Global report pages already provide print and export-style actions.
- This creates duplicate or inconsistent locations for report actions.

Acceptance:

- Each report should use one report toolbar only.
- Real exports should remain as explicit Excel/CSV actions.
- Browser print should be named print, not PDF export.
- Local print/export buttons should be removed or migrated to global/report toolbar actions.

### P1 - Dead or Half-Migrated Report Toolbar Code

Confirmed template:

- `templates/module_report.html`

Problem:

- Imports `document_menu_bar` but does not render it.
- Binds a click listener to `reportPrintMenuBtn`, but no matching element exists in the template.

Acceptance:

- Remove the dead listener, or render the intended button through the unified report toolbar.
- Keep report actions in the global report toolbar.

### P2 - Document Detail Pages With Competing Body Action Strips

Confirmed high-risk template:

- `templates/finance/voucher_detail.html`

Problem:

- Uses `document_menu_bar`.
- Also has a body-level action strip with return-to-list, post, reverse-post, and print.
- This competes with the global/detail toolbar and splits status-aware document actions across two locations.

Acceptance:

- Move page-level status actions into the unified toolbar or route-level extras.
- Keep only row-level or source/target drill-down actions in the document body.

Templates with both `document_menu_bar` and direct print/export logic requiring review:

- `templates/finance_aging_report.html`
- `templates/finance_detail_ledger.html`
- `templates/finance_general_ledger.html`
- `templates/financial_statements.html`
- `templates/module_report.html`
- `templates/project_cost_report.html`
- `templates/report_center.html`
- `templates/report_view.html`
- `templates/finance/voucher_detail.html`

Most of these are report/query pages, but they should still be reviewed because the local macro/global merge model and direct page-local actions can create duplicate or stale operations.

### P2 - Route-Level Extras Need Ownership Review

Confirmed files:

- `routes/inventory_routes.py`
- `routes/production_completion_routes.py`
- `routes/production_pick_routes.py`
- `routes/registry.py`

Problem:

- `g.toolbar_extras` is a valid extension point, but its ownership is not yet documented per page type.
- Empty extras are used to suppress or normalize actions in some entry/detail forms.

Acceptance:

- Extras should be allowed only for page-specific actions that are status-aware and implemented.
- Extras must not duplicate global standard actions by label or behavior.
- Extras should not introduce report actions into document pages or document-write actions into reports.

## Suggested Fix Order

### P0

Normalize list pages that can appear as `More/Tools only`:

- `templates/operation_report_list.html`
- `templates/production_completion_list.html`

### P1

Normalize report toolbar ownership:

- Remove local report print/export buttons where global report toolbar owns them.
- Keep only real Excel/CSV exports.
- Remove fake PDF export naming.
- Clean `module_report.html` dead listener.

### P2

Normalize document details:

- Start with `templates/finance/voucher_detail.html`.
- Move page-level status actions into unified toolbar/extras.
- Leave body content for document facts, lines, source links, target links, and row-level actions.

## Verification Checklist for Future Toolbar Changes

Run after any toolbar code change:

1. `python -m compileall app.py routes services scripts`
2. `python scripts\source_integrity_audit.py`
3. `python scripts\erp_prelaunch_audit.py`
4. `python scripts\audit_erp_crud_completeness.py`

Additional manual checks:

1. Open one `simple_list.html` list page and verify exactly one common list toolbar.
2. Open one legacy list page and verify it does not show only `More` or `Tools`.
3. Open one financial report and verify print/export appear in only one toolbar.
4. Open one document entry page and verify save/return/print actions are not duplicated.
5. Open one document detail page and verify status actions are not split between body and toolbar.
6. Open one print-only page and verify the print button remains available.
