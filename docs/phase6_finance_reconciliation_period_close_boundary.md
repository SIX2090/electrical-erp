# Phase 6 Finance Reconciliation And Period-Close Boundary

## Business Loop

This phase stabilizes the existing finance reconciliation loop for a machine-tool ERP:

Sales order / shipment -> sales invoice -> receivable -> customer receipt -> AR settlement -> cash/bank journal -> receivable reports -> period-close readiness.

Purchase receipt / subcontract receive -> purchase invoice -> payable -> supplier payment -> AP settlement -> cash/bank journal -> payable reports -> period-close readiness.

## Scope

Included:

- Existing AR and AP documents.
- Existing customer receipts and supplier payments.
- Settlement detail to settlement header consistency.
- Sales and purchase invoice registration lists.
- Sales and purchase three-way matching and invoice reconciliation reports.
- Customer, supplier, project number, and machine serial number finance detail reports.
- Cash/bank account governance, bank reconciliation, and fund reports.
- Voucher generation preview and period-close readiness checks.
- Menu exposure for finance users and administrators.

Excluded:

- New accounting recognition rules.
- New settlement algorithms.
- New accrual, allocation, or period-close algorithms.
- New finance modules, new finance routes, new database tables, or new fields.
- Any change to period-close posting behavior without a written accounting rule.

## Data Ownership

- AR documents are owned by Finance and sourced from sales shipment, sales invoice, or opening AR data.
- AP documents are owned by Finance and sourced from purchase receipt, subcontract receive, purchase invoice, or opening AP data.
- Receipt and payment documents are owned by Finance and must reconcile with settlement details and cash/bank journals.
- Project number and machine serial number remain traceability dimensions. They are used for finance detail and cost follow-up, not as universal mandatory fields.
- Inventory and cost posting remain owned by the designated posting services; finance routes must not write inventory or cost facts directly.

## Stabilization Findings

- Customer receipt and supplier payment headers can become stale when settlement detail rows exist but header settled and unapplied amounts are not recalculated.
- Finance menu exposure must keep management, invoice, reconciliation, report, period-end, and settings entries distinct.
- Project/machine-number AR and AP details must remain visible to finance users because project number and machine serial number are the main manufacturing traceability axis.
- Sales invoice registration and purchase invoice registration belong under finance invoice management, not sales or purchase operator menus.

## Acceptance Checks

The loop is accepted when:

- AR/AP enhancement audit reports no settlement header/detail mismatches.
- Finance blueprint audit reports all required finance menu labels and paths.
- Finance AR, AP, fund, bank reconciliation, counterparty, voucher preview, exchange, and period-close readiness audits pass.
- Inventory balance consistency still reports zero findings after finance checks.
- Visible navigation and direct access matrix audits pass for pilot users.
- Source integrity reports no mojibake or replacement-character findings.

## Current Status

As of this phase, no finance business rule was changed. The stabilization work is limited to data consistency repair and finance menu exposure alignment for the existing routes and reports.
