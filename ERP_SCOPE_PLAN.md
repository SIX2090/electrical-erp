# ERP Scope Stabilization Plan

## Objective

Stabilize the current machine-tool manufacturing ERP for trial go-live by proving the existing core loops instead of adding new modules.

## Current Automated Baseline

- Prelaunch audit: `core_pages=34`, `errors=0`, `warnings=0`.
- CRUD completeness: `targets=46`, `OK=46`, `errors=0`.
- Master-data completion scope: passed.
- System document gap audit: `documents_checked=13`, `risk_high=0`, `risk_medium=0`, `risk_low=0`.

## First Fix Batch

1. Inventory document entry visibility
   - Fix `/inventory/inbound` and `/inventory/outbound` list pages so operators can see the key document context: document information, source document, material detail count, inventory cost unit price, lot number, project number, and machine serial number.
   - Preserve `/inventory/inbound/new` and `/inventory/outbound/new` as the document-entry routes.

2. Material opening UI boundary
   - Keep material opening separate from other inbound.
   - Make the material opening form expose its own save action and opening-only labels.

## Next Readiness Batches

1. Opening and master-data reconciliation
   - Material opening, subcontract opening, AR opening, AP opening, account opening balances.
   - Reconcile quantities and balances against import sheets before trial go-live.

2. Five core business loops
   - Purchase request -> purchase order -> receipt -> inventory -> payable.
   - Sales order -> shipment -> receivable -> receipt settlement.
   - Work order -> material issue/return -> completion inbound -> cost.
   - Subcontract order -> issue -> receive -> variance/scrap -> payable.
   - Service card/order -> acceptance/return visit/RMA -> service cost and settlement trace.

3. Trace and cost proof
   - Project number and machine serial number must flow through sales, engineering, purchase, inventory, production, subcontract, shipment, service, AR/AP, and cost reports.
   - Trace integrity findings must be reviewed before trial go-live.

4. Operations readiness
   - Daily backup task configured or assigned to operations.
   - Restore drill completed on a controlled restore target: `wms_restore_drill_20260629`, `RESTORE_OK`, `331` public tables, `8` users, `66` products.
   - Role permission smoke test passed for trial roles.
   - Print templates confirmed for released document types.
