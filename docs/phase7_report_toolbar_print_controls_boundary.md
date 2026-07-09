# Phase 7 Report Toolbar And Print Control Boundary

## Business Loop

This phase stabilizes read-only report operation controls across finance, inventory, purchase, production, subcontract, service, and the central report catalog.

The affected operator loop is:

Open report -> set filters -> query -> reset filters -> refresh -> print/export -> drill down to source document where applicable.

## Scope

Included:

- Existing report pages discovered by the report print control audit.
- Existing `/reports` report center.
- Existing `/finance/inventory-costing` read-only inventory-costing report views.
- Existing print template list and editor/preview routes.
- Toolbar labels and action exposure only.

Excluded:

- New report routes.
- New report definitions.
- New menu entries.
- New database tables or columns.
- Changes to report SQL, cost calculation, posting, settlement, period close, or inventory accounting rules.
- Changes to protected audit scripts.

## Data Ownership

- Report pages remain read-only surfaces for querying, printing, exporting, and source-document drill-down.
- Inventory-costing write actions remain owned by the existing inventory costing routes and services.
- Print template maintenance remains owned by system administration; this phase only exposes the existing new-template entrance and required list actions.

## Stabilization Finding

The report audit found that many read-only report toolbars exposed refresh, print, export, and source-document drill-down, but did not consistently expose a reset action. The inventory-costing report views were also classified by the global toolbar as list pages, so they missed the report reset action.

## Acceptance Checks

The loop is accepted when:

- Report print controls audit passes.
- Report pages expose query, reset, export, print, and refresh.
- Report toolbar blocks document write actions such as create, save, submit, audit, void, post, and reverse-post.
- Print template list exposes new template, preview, design, copy, set default, enable, and disable actions.
- Report performance audit passes.
- Compile, source integrity, prelaunch, and CRUD completeness checks pass.
