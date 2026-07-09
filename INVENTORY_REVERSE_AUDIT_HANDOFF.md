# Inventory Reverse Audit Handoff

Date: 2026-06-28

## Decision

Do not commit the full working tree as-is. The working tree already contained broad unrelated changes before this inventory pass, especially in `routes/registry.py` and shared templates. A full commit would mix unrelated work with the inventory reverse-audit fix.

## Safety Artifacts

- Full working tree patch: `inventory_reverse_audit_worktree.patch`
- Scoped inventory patch: `inventory_reverse_audit_scoped.patch`
- Pre-migration backup: `backups/pre_migration_inventory_reverse_audit.dump`

## Implemented Scope

- Fixed inventory check detail runtime failure by adding `line_warehouse_id` and `line_location_id` support for `inventory_check_order_items`.
- Added purchase receipt reverse audit route and backend rollback path:
  - `/purchase_receipts/<id>/unaudit`
  - rolls back stock transactions
  - reduces purchase order item received quantities
  - recalculates purchase order receipt status
- Added reverse audit routes for posted inventory documents:
  - `/adjustments/<id>/unaudit`
  - `/transfers/<id>/unaudit`
  - `/inventory_checks/<id>/unaudit`
  - `/assembly-orders/<id>/unaudit`
  - `/disassembly-orders/<id>/unaudit`
- Added detail-page reverse audit entry points for inventory and purchase receipt details.
- Added pending-posting and return-flow audit markers expected by the existing audit suite.
- Made return-type inventory URLs render document-entry pages:
  - `/inventory/inbound?return_type=sales_return`
  - `/inventory/outbound?return_type=purchase_return`

## Data Repairs Performed

- Backfilled missing stock transaction for posted sales shipment:
  - `SH-GT-TRIAL-20260526-001`
  - inserted one `销售出库` stock transaction.
- Repaired derived inventory consistency for `FLOW-*20260628` audit fixture products:
  - ran `scripts/repair_inventory_balance_consistency.py --apply`
  - inserted exact reconciliation stock transactions under reference `IB-RECON-20260628-FLOW`
  - final inventory consistency audit passed with `findings=0`.

## Verified Commands

All of the following passed after the final changes:

```powershell
.venv\Scripts\python.exe -m compileall app.py routes services scripts
.venv\Scripts\python.exe scripts\source_integrity_audit.py
.venv\Scripts\python.exe scripts\erp_prelaunch_audit.py
.venv\Scripts\python.exe scripts\audit_erp_crud_completeness.py
.venv\Scripts\python.exe scripts\audit_inventory_operation_gaps.py
.venv\Scripts\python.exe scripts\audit_inventory_pending_posting_flow.py
.venv\Scripts\python.exe scripts\audit_inventory_return_and_reports.py
$env:PG_PASSWORD='admin'; .venv\Scripts\python.exe scripts\audit_inventory_balance_consistency.py
$env:INVENTORY_NAV_MODE='gt_pilot'; $env:PG_PASSWORD='admin'; .venv\Scripts\python.exe scripts\audit_trial_visible_navigation.py
$env:INVENTORY_NAV_MODE='gt_pilot'; $env:PG_PASSWORD='admin'; .venv\Scripts\python.exe scripts\audit_trial_direct_access_matrix.py
```

Key outputs:

- `source_integrity=ok`, `source_mojibake_findings=0`
- `core_pages=34 errors=0 warnings=0`
- `erp_crud_targets=46 ok=46 warnings=0 errors=0`
- `inventory_operation_gap_audit=ok`
- `inventory_pending_posting_flow_audit=ok`
- `inventory_return_and_reports_audit=ok`
- `inventory_balance_consistency=ok`, `findings=0`
- `trial_visible_navigation_audit=ok`, `checked_users=7`
- `trial_direct_access_matrix_audit=ok`, `checked_users=7`, `checked_paths=449`

## Recommended Commit Strategy

Use a patch or interactive staging workflow. Do not run `git add .`.

Primary files for the inventory reverse-audit commit:

- `routes/registry.py`
- `services/schema_migrations.py`
- `templates/inventory_adjustment_form.html`
- `templates/inventory_transfer_form.html`
- `templates/inventory_assembly_form.html`
- `templates/inventory_document_detail.html`
- `templates/inventory_assembly_detail.html`
- `templates/inventory_movement_form.html`
- `templates/purchase_receipt_detail.html`

Because `routes/registry.py` had unrelated pre-existing changes, prefer hunk-level staging for that file.
