# Phase 4 Production Closure Boundary

## Business Loop

This boundary covers production closure from Work order preparation through material issue, operation reporting, completion inbound, work order cost collection, and project and machine ledger traceability.

The loop starts after engineering readiness and work order preparation are complete. It ends when issued materials, production returns, completion inbound records, stock transactions, and work order cost lines can be reconciled by work order, project code, and cabinet number.

## Source and Target Documents

Source documents:

- Work order.
- Work order BOM material requirements.
- MRP and kitting shortage basis.
- Quality inspection results when completion is gated by inspection.

Target documents and views:

- Production material issue document.
- Production material return document.
- Operation report records.
- Completion inbound document.
- Stock transaction and inventory balance records.
- Work order cost collection records.
- Project and machine ledger lifecycle events.

## Ownership

- Production owns work order execution, operation reporting, and completion readiness.
- Warehouse owns material issue, material return, completion inbound posting, stock movement, and location accuracy.
- Engineering owns BOM, routing, drawing, and ECN readiness before execution.
- Finance consumes work order cost collection output and period-close warnings, but finance settlement rules are not changed in this boundary.

## Read-Only Closure Data

Project-axis production closure APIs expose read-only data for sales order, project code, or cabinet number. They summarize work order count, pending issue quantity, issue document count, return document count, completion document count, cost line count, total cost, blocked reason, next action, and owner role.

The read-only APIs must not create, submit, audit, reverse, void, post, or delete any production, inventory, procurement, or finance document.

## Out Of Scope

This boundary does not add new ERP modules, normal-user menus, permission surfaces, database tables, or finance allocation rules.

Automatic production scheduling, payroll calculation, advanced MES dispatch, new cost allocation formulas, and period-close accounting changes are out of scope.

## Acceptance

The loop is accepted only when operators can verify the following:

- A work order can show BOM basis, material issue status, pending issue quantity, completion quantity, blocked reason, owner role, and next action.
- Material issue and return documents update work order material quantities and inventory consistently.
- Completion inbound documents create traceable stock transactions and can be reversed through controlled document logic.
- Work order cost collection regenerates controlled system cost lines idempotently from material issue, return, completion, subcontract, and operation-report basis.
- Project and machine ledger views include production issue, production return, completion inbound, and work order cost lifecycle events.
- Project code and cabinet number remain traceability fields throughout issue, return, completion, inventory, and cost views.
