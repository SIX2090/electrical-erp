# Next Session Handoff

Current first-machine trial decision: `GO`

Date: 2026-06-29

## Current Scope

The current scope is trial go-live stabilization for the existing machine-tool manufacturing ERP core. No new modules are open. The latest work repaired inventory document visibility, material opening save exposure, restore-drill evidence, inventory consistency evidence, and the pilot role master-data read baseline.

## Current Automated Baseline

- Prelaunch audit: `core_pages=34 errors=0 warnings=0`.
- CRUD completeness: `targets=46 OK=46 errors=0`.
- System document gaps: `documents_checked=13 risk_high=0 risk_medium=0 risk_low=0`.
- Inventory balance consistency: `findings=0`.
- Full system operator simulation: `failed_pages=0 failed_post_checks=0`.
- Trial sales menu entries, operator task queues, and first-machine lifecycle ledger are passing as of 2026-06-29.
- Trial role permissions page and direct access matrix are passing after preserving the default `master` read group for sales, purchase, warehouse, production, and service pilot roles.

## Trial POST action scope

POST exposure remains part of the release gate and passed in the latest run:

```powershell
python scripts\audit_trial_post_action_scope.py
```

## Backup and Restore

Backup succeeded before the inventory balance repair:

```powershell
.venv\Scripts\python.exe scripts\pg_backup.py --output backups\pre_inventory_balance_repair_20260629.dump
```

A second backup was taken before repairing first-machine trial material consistency:

```powershell
.venv\Scripts\python.exe scripts\pg_backup.py --output backups\pre_inventory_balance_repair_trial_materials_20260629.dump
```

Restore drill completed on an isolated target database `wms_restore_drill_20260629` and the temporary database was removed after validation.

- Restore result: `RESTORE_OK`.
- Restored public tables: `331`.
- Restored users: `8`.
- Restored products: `66`.

## Inventory Consistency Repair Evidence

The 2026-06-29 final inventory consistency repair covered first-machine trial materials `GT-MAT-TRIAL-001` and `GT-MAT-TRIAL-002`.

- Repair script updated derived legacy inventory and batch tracking rows.
- Four `stock_transactions` rows were appended with transaction type `inventory_balance_reconciliation`.
- Final audit result: `inventory_balance_consistency=ok`, `findings=0`.

## Recommended Next Session

1. Reconcile real cutover data: material opening, subcontract opening, AR/AP opening, open purchase orders, open sales orders, work orders, service orders, and inventory balances.
2. Freeze production cutover time, data-freeze time, rollback owner, and backup retention owner.
3. Re-run the final verification chain after any further change.
