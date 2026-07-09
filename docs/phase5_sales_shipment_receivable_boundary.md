# Phase 5 Sales Shipment Receivable Boundary

## Business Loop

Sales order -> sales shipment -> customer receivable -> customer receipt and reconciliation -> project and machine serial traceability.

## Source Document

The source document is the audited sales order. The sales order owns customer, project code, machine serial number, price, delivery intent, and shipment demand.

## Target Documents

- Sales shipment records outbound execution and inventory movement.
- Customer receivable records the AR balance by customer, source document, project code, and machine serial number.
- Customer receipt records collection against the sales order or receivable source.
- Project and machine serial ledgers expose downstream traceability across shipment, receivable, service card, and stock transactions.

## In Scope

- Existing sales order, shipment, receivable, receipt, project trace, service card, and inventory transaction pages.
- Existing sales and finance menu boundaries.
- Existing first-machine trial data used by sales completion audits.
- Existing inventory balance, batch tracking, stock transaction, and legacy inventory derived-summary reconciliation.

## Out of Scope

- No new route, menu, database table, or database field.
- No finance settlement rule, accrual rule, or period-close logic change.
- No new invoice or collection module expansion.

## Owners

- Sales owns sales order and shipment follow-up.
- Warehouse owns shipment stock execution.
- Finance owns receivable, invoice, receipt, and reconciliation pages.
- Project trace is shared read-only visibility across sales, warehouse, service, and finance.

## Status And Blocking Rules

- A sales shipment must be based on an audited sales order.
- Finance-owned entries such as receivables and sales invoices must not be duplicated in the sales navigation group.
- Sales may keep direct query access to receivable/project trace pages where existing permissions allow it, but homepage and navigation shortcuts must not present those pages as sales-owned work.
- Project code and machine serial number are traceability fields. They should flow when present, but are not universal mandatory fields unless the system option requires them.

## Acceptance Checks

- First-machine completion, shipment, receivable, service card, project trace, and inventory transaction audit passes.
- Sales dashboard boundary audit passes.
- Trial sales menu entries audit passes, with finance-owned links excluded from sales-owned menus.
- Sales E2E order -> shipment -> invoice -> receipt flow completes.
- Inventory balance consistency remains clean after the sales E2E flow.
- Compile, source integrity, prelaunch, CRUD completeness, visible navigation, and direct access matrix audits pass.
