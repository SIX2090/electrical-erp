# P0 Engine Stabilization Boundary

Date: 2026-06-20

This document fixes the boundary for the first P0 development batch after the six-agent read-only audit. It is intentionally narrow: stabilize the manufacturing ERP engine foundations without expanding menus, modules, or report scope.

## Boundary Summary

Affected business loop:

Sales/project demand -> BOM/routing/drawing readiness -> work order -> material requirement and kitting -> purchase/subcontract/inventory evidence -> completion/shipment/service -> AR/AP and cost evidence.

Page types:

- Existing document entry and detail pages only where a workflow already exists.
- Existing list, query, workbench, and report pages remain separated.
- No new normal-navigation menu group.
- No new `/trace/*`, `/mrp/*`, `/cost/*`, or `/security/*` public route in this batch.

Data owner:

- Engineering owns BOM, routing, drawing, and ECN metadata.
- Production owns work-order execution snapshots and material requirements.
- Warehouse owns inventory balances and stock transactions.
- Purchase and subcontracting own procurement and outsourcing source documents.
- Finance owns AR/AP, vouchers, general ledger, period close, and finance-owned reports.
- System/admin owns route and permission policy.

Primary trace axis:

- Use `project_code` and `cabinet_no`.
- Do not introduce a second project or machine axis such as `project_id`, `machine_no`, or `cabinet`.
- Use line-level `line_project_code` and `line_cabinet_no` where a document line can override the header. Empty line fields inherit the header values.

## P0-A: Trace Field Standardization

Goal:

Freeze the current project and cabinet trace vocabulary before engine coding.

In scope:

- Treat `project_code` and `cabinet_no` as the canonical business trace fields.
- Treat `project_masters.project_code` and `cabinet_masters.cabinet_no` as the master-data reference sources.
- Prefer `source_doc_type`, `source_doc_id`, `source_doc_no`, and `source_line_no` for new source references.
- Keep compatibility with existing `source_type`, `source_id`, and `source_no` fields where they already exist.

Out of scope:

- Adding new trace axis fields.
- Dropping or renaming existing compatibility fields.
- Rewriting historical source reference columns.

Acceptance:

- New code does not add a second project or cabinet naming convention.
- Existing audits continue to report clean source integrity and prelaunch status.

## P0-B: Work Order Execution Snapshots

Goal:

Prevent released work-order execution from drifting when BOM, routing, or drawing records change later.

In scope:

- Capture a work-order execution snapshot at work-order creation or release using existing work-order, BOM, routing, and drawing data.
- Snapshot payload must include the work-order header, BOM header and lines, routing header and operations, and drawing metadata where available.
- Existing work-order detail may display snapshot evidence if it can be added without creating a new route or menu entry.
- Material requirement generation for a work order should use the stored snapshot when available.

Out of scope:

- Full ECN task management.
- Automatic purchase, production, inventory, service, or finance document changes from ECN.
- New BOM version center routes or menus.
- PDM, MES, APS, or external drawing integration.

Acceptance:

- A work order can explain which BOM, routing, and drawing metadata were used at execution time.
- Regenerating material requirements for a snapshotted work order is not affected by later BOM line edits.
- No report page gains document write actions.

## P0-C: Read-Only MRP Calculation Snapshot

Goal:

Turn current shortage consumption into an explainable, repeatable MRP calculation without automatic downstream document creation.

In scope:

- Start from a single `work_order_id`, or from a `project_code + cabinet_no` context when a work order is available.
- Use the work-order snapshot BOM when present; otherwise use the existing selected BOM.
- Calculate gross demand from multi-level BOM quantities and loss rate.
- Deduct available inventory, locked inventory, purchase requisitions, purchase on-order quantity, and work-order issued/returned quantity where current data supports it.
- Write or expose a calculation snapshot and line-level explanation only if schema and route boundary are explicitly approved in the implementation step.

Out of scope:

- Automatic creation of purchase requests, production orders, subcontract orders, or transfer orders.
- Automatic substitute material approval.
- Finite capacity scheduling.
- Full subcontract WIP and production WIP deduction in the first pass.

Acceptance:

- The same input produces the same result when source data is unchanged.
- Each shortage line can explain source BOM line, gross demand, available quantity, deduction quantities, and net shortage.
- Existing `/engineering/kitting`, `/production-enhance/mrp-requirements`, and `/procurement/suggestions` boundaries remain intact.

## P0-D: Trace Link Gap Closure

Goal:

Use the existing `trace_links` and `trace_snapshots` tables instead of building another trace model.

In scope:

- Add missing `trace_links` writes inside existing create, post, settle, or conversion flows only when the source and target documents already exist.
- Priority links:
  - sales order -> customer receivable
  - purchase requisition -> purchase order
  - purchase order -> supplier payable
  - subcontract order -> subcontract issue
  - subcontract order -> subcontract receive
  - subcontract order -> supplier payable
  - service card -> service order
  - service order -> RMA
  - source document -> stock transaction where the stock transaction already records source evidence

Out of scope:

- New trace pages.
- New graph visualization.
- New normal-navigation trace menu.
- Backfilling all historical rows unless explicitly selected as a separate batch.

Acceptance:

- New trace writes are idempotent.
- Trace integrity checks do not report duplicate edges.
- Source and target project/cabinet values are not silently changed by trace writes.

## P0-E: Cost Collection Proof

Goal:

Prove project and cabinet cost evidence through existing cost services and reports without changing finance posting rules.

In scope:

- Reuse `work_order_cost_service.py` as the work-order cost foundation.
- Compare material cost from work-order issue/return lines, labor and overhead from operation reports, subcontract cost from payable or subcontract evidence, and service cost from service orders.
- Keep project and cabinet cost reports read-only.

Out of scope:

- Direct writes to customer receivable, supplier payable, vouchers, voucher lines, general ledger, accounting periods, or period close tables.
- New cost allocation rules.
- Month-end manufacturing overhead allocation.
- Automatic voucher generation or period-close changes.

Acceptance:

- Work-order material cost can be reconciled to issued and returned material lines.
- Project/cabinet cost evidence can trace each cost component to a source document.
- Cost reporting does not post inventory or finance records.

## P0-F: Data Permission Boundary

Goal:

Avoid designing data visibility in a way that conflicts with the current route permission model.

In scope:

- First implementation should focus on query scope filtering, direct detail access protection, and export using the same scope.
- Scope dimensions are project, cabinet, department, customer, and supplier.
- Admin and manager can bypass data scope by policy unless later changed by the user.

Out of scope:

- Full data permission UI in this batch.
- New security menu entries.
- Edit or approve scope behavior.

Acceptance:

- If data scope is enabled for a resource, list, detail, API, and export use the same data boundary.
- Route permission, rollout classification, and navigation audits remain clean.

## Required Verification

Before any code change:

```cmd
.venv\Scripts\python.exe -m compileall app.py routes services scripts
.venv\Scripts\python.exe scripts\source_integrity_audit.py
.venv\Scripts\python.exe scripts\erp_prelaunch_audit.py
.venv\Scripts\python.exe scripts\audit_erp_crud_completeness.py
```

Before any schema migration:

```cmd
.venv\Scripts\python.exe scripts\pg_backup.py --output backups\pre_migration_p0_engine_stabilization.dump
```

After any schema or application code change:

```cmd
.venv\Scripts\python.exe -m compileall app.py routes services scripts
.venv\Scripts\python.exe scripts\source_integrity_audit.py
.venv\Scripts\python.exe scripts\erp_prelaunch_audit.py
.venv\Scripts\python.exe scripts\audit_erp_crud_completeness.py
```

If inventory behavior is touched:

```cmd
set PG_PASSWORD=admin && .venv\Scripts\python.exe scripts\audit_inventory_balance_consistency.py
```

If permission, route, or navigation behavior is touched:

```cmd
set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=admin && .venv\Scripts\python.exe scripts\audit_trial_visible_navigation.py
set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=admin && .venv\Scripts\python.exe scripts\audit_trial_direct_access_matrix.py
```
