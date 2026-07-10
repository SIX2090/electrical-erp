# Phase 3 Procurement Closure Boundary

## Business Loop

This boundary covers procurement closure from engineering-ready shortages to purchase request, purchase order, receipt/inventory, supplier payable, and project or machine ledger traceability.

The loop starts after engineering readiness and MRP/kitting shortage analysis identify purchasable material shortages. It ends when purchase request execution, purchase order execution, receipt posting, inventory evidence, and supplier payable records can be reconciled by project code and cabinet number.

## Source and Target Documents

Source documents:

- Engineering-ready shortages from MRP and kitting analysis.
- Purchase suggestions that carry engineering readiness, blocked reason, owner role, and next action.
- Approved purchase requests.

Target documents and views:

- Purchase request.
- Purchase order.
- Purchase receipt and inventory stock transaction.
- Supplier payable.
- Project and machine ledger lifecycle events.

## Ownership

- Engineering owns readiness before a shortage can be converted into procurement execution.
- Production and planning own shortage demand and required date basis.
- Purchasing owns purchase request follow-up, supplier confirmation, purchase order creation, and vendor delivery follow-up.
- Warehouse owns receipt/inventory posting evidence.
- Finance consumes supplier payable records and payment status. This boundary does not change finance settlement rules.

## Read-Only Closure Data

Project-axis procurement closure APIs expose read-only status for sales order, project code, or cabinet number. They summarize shortage line count, purchase request count, purchase order count, pending receipt quantity, purchase receipt count, supplier payable count, payable balance, blocked reason, next action, and owner role.

These APIs must not create, submit, approve, void, post, reverse, or settle any business document.

## Out Of Scope

This boundary does not add new ERP modules, normal-user menus, permission surfaces, database tables, supplier scoring rules, payment rules, or accounting rules.

Automatic supplier selection, automatic purchase order generation from unready engineering shortages, invoice certification, supplier payment allocation, and period-close accounting changes are out of scope.

## Acceptance

The loop is accepted only when operators can verify the following:

- Engineering-not-ready shortage rows are blocked from purchase request creation and show blocked reason, owner role, next action, technical confirmation link, and project ledger link.
- Engineering-ready shortage rows can move through purchase request and purchase order without losing project code or cabinet number.
- Purchase receipts create inventory evidence and preserve source purchase order, project code, and cabinet number.
- Supplier payable records are traceable from purchase execution and remain visible in payable query/detail surfaces.
- Project and machine ledger views include purchase request, purchase receipt, and supplier payable lifecycle events.
- Read-only procurement closure APIs expose closure counts and blockers without writing procurement, inventory, or finance documents.
