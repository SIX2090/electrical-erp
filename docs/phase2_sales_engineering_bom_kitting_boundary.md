# Phase 2 Sales Engineering BOM Kitting Boundary

## Business Loop

This boundary covers the sales order to engineering technical confirmation loop for machine-tool and special-purpose equipment manufacturing.

The loop starts from a sales order or project requirement and flows through product configuration, engineering technical confirmation, BOM/routing/drawing readiness, MRP shortage analysis, kitting readiness, and work order preparation.

## Source and Target Documents

Source documents:

- Sales order.
- Product configuration document when option selection is needed before engineering confirmation.

Target documents and views:

- Engineering technical confirmation document.
- Project or production BOM reference.
- MRP run and suggestion records.
- Kitting readiness query.
- Work order entry and work order detail.

## Read-Only Readiness Data

Project-axis engineering readiness APIs expose read-only JSON readiness data for sales order, project code, or machine serial number. These APIs must summarize status, owner role, blocked reason, next action, technical confirmation basis, released drawing basis, and kitting basis.

The readiness APIs must not create, submit, audit, reverse, void, or post any business document. They are warning and guidance surfaces only.

## Ownership

- Sales owns customer requirement clarity and sales order source data.
- Engineering owns technical confirmation, BOM basis, routing basis, drawing version, and open ECN closure.
- Production owns work order preparation and execution after engineering readiness is complete.
- Purchasing and warehouse consume MRP/kitting results after readiness; they do not own this boundary.

## Out of Scope

This boundary does not add new ERP modules, menus, database tables, or normal user pages.

Product configuration and engineering confirmation must not directly create purchase orders, work orders, stock transactions, finance postings, outsourcing orders, or shipment documents.

Finance posting, inventory posting, automatic procurement generation, and production completion are outside this phase.

## Acceptance

The loop is accepted only when operators can verify the following without relying on HTTP 200 alone:

- A sales order or project can show whether engineering readiness is complete.
- The readiness surface shows owner role, blocked reason, next action, technical confirmation basis, BOM basis, drawing basis, and kitting basis.
- Engineering technical confirmation can be prefilled from sales order context.
- Technical confirmation blocks incomplete BOM, routing, drawing, or open ECN conditions before confirmation.
- MRP and kitting views preserve project code and machine serial number as traceability fields.
- Work order preparation can drill back to BOM, MRP shortage, kitting readiness, and project ledger context.
- Read-only readiness APIs do not write execution, inventory, procurement, or finance documents.
