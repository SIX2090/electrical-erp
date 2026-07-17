# Inventory Posting Stabilization Boundary — 2026-07-17

## Business Loop

Existing inventory-impact documents to stock transaction ledger and dimensional inventory balances.

## Requested Outcome

Remove duplicated route-level stock balance and transaction mutations when the existing inventory service already implements the same posting semantics.

## Page Types and Routes

No page type, route, menu, permission, or rollout classification changes are authorized. Existing document entry, detail, list, audit, unaudit, close, and cancel behavior must remain exposed exactly as before.

## Data Owner

- `services/inventory_service.py` owns product locking, balance locking, weighted-average inbound costing, outbound costing, dimensional balance updates, legacy inventory synchronization, and stock transaction creation.
- Existing document routes own request validation, document header/line persistence, status transitions, response messages, and redirects.

## Source Documents

Existing inbound, outbound, transfer, adjustment, check, assembly, production pick/completion, shipment, receipt, return, and subcontract documents only. No new document type is introduced.

## Status and Posting Contract

- Preserve every current allowed source status and target status.
- Preserve existing idempotency and downstream guards.
- Preserve source type, source document number, source line, warehouse, location, lot, project number, cabinet number, quantity, unit cost, and amount.
- A refactor is permitted only when the designated service produces the same balance and transaction effect as the replaced code.
- If service behavior cannot be proven equivalent statically, leave the call site unchanged and record it for database-backed acceptance.

## Downstream Impact

Inventory balance, stock transaction ledger, batch/lot trace, project/cabinet trace, production/project cost, AR/AP reconciliation, and reversal evidence may consume posted movements. No finance posting rule is changed in this boundary.

## Acceptance

1. Critical Python static checks pass.
2. No newly introduced route, permission, menu, DDL, or Chinese encoding finding exists.
3. Inventory consistency audit reports `findings=0` in an approved runtime environment.
4. Each changed source document posts once, rejects a duplicate post, reverses through its established action, and reconciles document lines to stock transactions and dimensional balances.

## Explicit Non-Goals

- AR/AP settlement, accrual, invoice, voucher, general-ledger, period-close, and financial-statement rules.
- Schema changes or data repair.
- Removing route-level document header/line persistence.
- Refactoring a call site whose accounting, costing, or reversal equivalence is unclear.
