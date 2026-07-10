# Phase 5 Delivery, Outsourcing, And Service Boundary

## Sales Delivery Loop

Sales delivery starts from an audited sales order and flows to shipment, inventory outbound movement, customer receivable, service-card creation, and project or machine-cabinet traceability.

The source document is the sales order. Target documents are sales shipment, stock transaction, customer receivable, and machine service card. Sales owns customer delivery follow-up, warehouse owns outbound execution, finance owns receivable and receipt reconciliation, and service owns after-sale lifecycle records after shipment.

Acceptance requires that the shipment, receivable, service card, project ledger, and stock transaction all preserve project code and cabinet number when present.

## Outsourcing Loop

Outsourcing starts from an existing subcontract order or work-order-driven outsourced process and flows to subcontract issue, processor receipt, subcontract receive, WIP or inventory update, payable basis, and work-order cost refresh when the outsourced process is tied to a parent work order.

The source document is the subcontract order or parent work order. Target documents are subcontract issue, subcontract receive, stock transaction, subcontract WIP movement, payable basis, and work-order cost lines where applicable. Production and purchasing own the source demand, warehouse owns issue and receive execution, and finance owns payable settlement rules.

Acceptance requires subcontract issue and receive events to appear in the project or machine-cabinet ledger and remain traceable to source documents.

## Service Loop

Service starts from a shipped machine service card and flows to installation acceptance, service order, dispatch, checklist or handling record, return visit, RMA, claim, recovery, close, service cost, and project or machine-cabinet traceability.

The source document is the machine service card, usually created from sales shipment. Target documents are installation acceptance, machine service order, service dispatch, service checklist, service return visit, machine service RMA, service cost, and claim or recovery records. Service owns service execution and RMA closure; finance owns fee settlement and accounting treatment.

Acceptance requires service card, acceptance, service order, and RMA events to appear in the project or machine-cabinet ledger and remain searchable by project code and cabinet number.

## Out Of Scope

- No new ERP module, menu, permission surface, route, table, column, or normal-user navigation entry.
- No finance settlement, accrual, period-close, or accounting-rule change.
- No offline installer generation.
- No generic dashboard expansion.
- No replacement of existing document-entry and document-list separation.

## Business Rules

- Build business loops, not isolated pages.
- Keep sales delivery, outsourcing, and service documents separated from reports.
- Workbench pages may show pending queues, blocked reasons, owners, next actions, and downstream impact only.
- Project code and cabinet number are traceability fields. They are not universal mandatory fields unless the system option requires them.
- Existing shipment, outsourcing, service, inventory, finance, and project ledger pages remain the only runtime surface for this phase.

## Acceptance Checks

- Phase 5 boundary audit passes.
- Runtime verifier covers the sales delivery loop, outsourcing loop, service loop, and project-axis events.
- First-machine service closure audit passes.
- Service closure verifier reports no blocking findings.
- After-sale service boundary audit reports no errors.
- Compile, source integrity, prelaunch, CRUD completeness, navigation, direct access, and inventory consistency audits remain clean after any code or data repair.
