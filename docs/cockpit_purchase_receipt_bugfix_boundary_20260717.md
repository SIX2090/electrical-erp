# Cockpit and Purchase Receipt Bugfix Boundary — 2026-07-17

## Affected Loops

- Management cockpit read-only reconciliation across sales, production, inventory, procurement, and finance.
- Purchase order -> purchase receipt -> inventory receipt -> purchase-order execution quantity/status.

## Page Types and Routes

- Existing management cockpit only; no new report or route.
- Existing purchase receipt detail audit action only; no route, menu, permission, or classification change.

## Data Owners

- KPI service owns read-only aggregation.
- Purchase receipt route owns document transition and order execution counters.
- Inventory service owns balance, batch, legacy summary, and stock transaction posting.

## Required Behavior

- KPI queries must use the actual schema tables and recognize established Chinese and legacy English statuses.
- Purchase receipt audit must lock the receipt and related order data, reject duplicate/full or partial reposting, and commit every line posting, order-line received quantity, order header amount/status, and receipt status in one transaction.
- Any failure must roll back the complete audit operation.

## Downstream Impact

Inventory balances and transactions, purchase execution quantity/status, cockpit AR/AP/cash/backlog/WIP/open-PO values, traceability, payable/cost reconciliation, and later reverse-audit guards.

## Acceptance

1. A multi-line receipt either posts all lines and statuses or posts nothing.
2. Retrying an audited receipt creates no duplicate stock or order quantities.
3. Failure on a later line rolls back earlier lines.
4. Cockpit AR/AP/cash values reconcile to actual ledgers and cash-bank data.
5. Chinese and English closed/void/completed statuses are excluded consistently.

## Non-Goals

- New KPI pages or metrics.
- Changes to settlement, accrual, voucher, general-ledger, tax, or period-close rules.
- Schema changes or data repair.
- Bulk deletion of duplicate functions without module-specific equivalence review.
