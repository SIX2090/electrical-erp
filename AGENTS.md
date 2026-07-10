# Project Rules

## Backup Policy

- Production must run `scripts/pg_backup.py` daily through Windows Task Scheduler or an equivalent operations scheduler.
- Before any schema migration, run `scripts/pg_backup.py --output backups/pre_migration_<desc>.dump`.
- Restore drill must be performed before go-live with `scripts/pg_restore.py --input <dump_file>` against a controlled restore target.

## ERP Scope Discipline

- Before writing ERP code, define the boundary first. Do not start implementation until the affected business loop, page type, route exposure, data owner, upstream source document, downstream impact, and acceptance check are clear.
- Do not add new ERP modules or menus until the stabilization plan in `ERP_SCOPE_PLAN.md` is complete.
- Prefer fixing and proving existing core workflows over expanding functional scope.
- Any page exposed to normal users must be classified as `live`, `fix`, `readonly`, `internal`, or `hidden`.
- Hide unfinished modules instead of leaving low-quality placeholder pages in navigation.
- HTTP 200 is not enough; verify that operators can complete the workflow and reconcile the resulting data.
- If a requested change removes or hides an ERP page, audit and update every dependent menu entry, shortcut, return link, redirect, permission expectation, and automated audit before declaring the deletion complete.
- If the boundary is unclear, stop and write the boundary in `ERP_BOUNDARY_STABILIZATION.md` or `MENU_ROLLOUT_CLASSIFICATION.md` before editing application code.

## Chinese ERP UX Rules

- Keep page types separate: workbench, document list, document entry, master data, query list, report, finance, and system admin.
- Document, list, and report pages must follow conventional ERP operation patterns: dense top toolbar, status-aware actions, search/filter, refresh, print, export, return/exit, and source/detail drill-down where applicable.
- Do not simplify high-frequency ERP pages into sparse web-app pages; operators should not need extra clicks to find common document, list, or report actions.
- Normal navigation labels must reveal page type. List or query-list routes must include `列表` or `查询`; report routes must include `报表`, `明细`, `汇总`, `分析`, or `对账`; document-entry routes should use `新增` or `录入`.
- Navigation must keep workbench, document entry, document list/query, and report entries in separate labeled groups; do not put create/document-entry links in the same group as list/query links.
- Do not mix document write actions into reports.
- Do not mix report-style analysis into high-frequency document entry pages.
- Core document pages must be dense, searchable, status-aware, and keyboard-friendly.
- Visible Chinese labels, statuses, and business terms must not contain mojibake, replacement characters, or placeholder text.
- Markdown planning, audit, handoff, and release documents must be written in English to avoid encoding damage. Operator-facing ERP UI labels and business terms remain clean Chinese.

## Encoding Safety Rules

- Do not create or edit Chinese text through PowerShell string redirection, Python write scripts, shell heredocs, or console pipelines.
- Use `apply_patch` for every manual edit that adds, changes, or removes Chinese UI text, status labels, business terms, or mixed Chinese/English ERP copy.
- Before declaring work complete, run `scripts/source_integrity_audit.py` and fix any mojibake, replacement characters, repeated question-mark replacement text, or corrupt Chinese status finding.
- If a file already contains mojibake, remove or repair the corrupt literal instead of adding compatibility aliases that preserve dirty text in source code.
- Never knowingly leave corrupt Chinese in `AGENTS.md`, templates, routes, services, navigation, audit output, or operator-facing pages.

## Core Workflow Priority

Focus first on:

- Product and project master: product family, machine model, project number, cabinet number.
- Technical master: material, BOM, routing, work center, outsourced process, key control point.
- Master data: material, customer, supplier, outsourced processor, warehouse, location, unit, department, employee, category.
- Purchase: request, order, receipt, payable.
- Outsourcing: outsourced order, issue to processor, receive from processor, scrap/short receipt, payable.
- Inventory: inbound, outbound, transfer, adjustment, check, balance, transactions.
- Sales: order, shipment, receivable.
- Basic production: BOM, work order, requisition, completion/inbound when available.
- Service: service card by cabinet number, installation acceptance, service order, RMA.
- Finance reconciliation: AR/AP, period close, basic financial statements.

Advanced after-sale, quality, payroll, asset, logistics, marketing, custom document, and custom report features are out of scope until the core version is stable.

## Industry Direction

This project is for low-voltage switchgear and distribution automation control equipment manufacturing, not a generic ERP.

Company product families include 低压抽出式开关柜, 低压固定式开关柜, 低压配电柜, 动力配电箱, 照明配电箱, 无功补偿装置, 配电自动化终端DTU, 环网柜, and 箱式变电站.

Project number and cabinet number are the main tracking axis. They must flow through sales, BOM, purchase, inventory, outsourcing, work order, assembly, wiring, testing, shipment, on-site service, AR/AP, and cost reports.
They are traceability fields, not universal mandatory fields. Make-to-stock production of standard distribution boxes, small-company simplified operation, and early project preparation may leave project number or cabinet number blank unless the system option `require_project_cabinet` is explicitly enabled. UI labels should show them as recommended traceability fields instead of always marking them required.

Use Digiwin-style manufacturing ERP as the primary benchmark. Do not switch the product direction to generic SaaS dashboards, Kingdee-style finance-first pages, or Yonyou-style broad module expansion unless the user explicitly changes this rule.

- Build business loops, not isolated pages.
- Define the loop boundary before coding: source document, target document, status transition, inventory/finance posting, owner, blocked reason, next action, and reconciliation report.
- Surface source document, next action, blocked reason, owner, and downstream impact.
- Connect BOM, MRP, purchase, outsourcing, warehouse, work order, quality, shipment, service, and cost.
- Prefer workbench queues and exception lists over decorative dashboards.
- Workbench pages must not render full business record lists. A workbench may show role-specific pending queues, exception queues, blocked reasons, owners, next actions, and downstream impact only.
- Deleted workbench root routes must not be reused as compatibility entrances. Replace them with explicit document-entry, document-list, query-list, report, finance, or system-admin routes.
- Stabilization and acceptance must be done by business loop: purchase request to purchase order to receipt to inventory to payable; sales order to shipment to receivable; work order to requisition/completion/inbound; service card/order/RMA to fee/cost.
- Do not copy proprietary UI verbatim; implement the manufacturing management logic in this product's own interface.

## Schema Change Rules

- All DDL changes (CREATE TABLE, ALTER TABLE, ADD COLUMN, CREATE INDEX) must be written into `services/schema_migrations.py` first. Never execute DDL inline inside routes or services at request time.
- Before any schema migration, run `scripts/pg_backup.py --output backups/pre_migration_<desc>.dump`.
- Never run `DROP COLUMN` or `DROP TABLE` without explicit user instruction naming the column or table.
- After a schema change, run `python -m compileall app.py routes services` to confirm no broken references.

## Route Registration Checklist

Every new route added to `routes/` must also complete all of the following before the task is declared done:

1. Permission registered in `services/pilot_permissions.py` for every role that needs access.
2. Page classified in `MENU_ROLLOUT_CLASSIFICATION.md` as `live`, `fix`, `readonly`, `internal`, or `hidden`.
3. Route catalogued in `routes/route_catalog.py` or the equivalent registry file.
4. If the route is document entry or document list, it must be reachable from normal navigation and pass `audit_trial_visible_navigation.py`.

A route that exists in Flask but is missing from the permission registry or menu classification is incomplete.

## Finance Module Rules

- Financial records (AR lines, AP lines, cost lines, period summaries) must only be written by the designated posting service (`services/inventory_posting_service.py` or equivalent). Never INSERT or UPDATE finance tables directly inside route handlers.
- Do not modify settlement, accrual, or period-close logic unless the user explicitly provides the accounting rule to implement.
- Before touching any period-close related table, run `scripts/pg_backup.py`.
- Do not add new finance report pages or cost allocation logic without a written boundary definition from the user.

## Scope Freeze Rule

- Do not add any new route, database field, page, or navigation entry unless the user explicitly requests it in this session.
- Bug fixes must be scoped to the minimum change that reproduces and resolves the reported bug. Do not refactor surrounding code, add helper utilities, or improve unrelated logic during a bug fix.
- If fixing a bug requires a larger structural change, stop and describe the required change to the user before proceeding.

## Audit Script Protection Rules

The `scripts/` directory contains the system's verification safety net. These rules are mandatory:

**Never modify audit scripts unless explicitly instructed.**
- Do not edit, rename, delete, or refactor any file matching `scripts/audit_*.py`, `scripts/verify_*.py`, `scripts/validate_*.py`, or `scripts/erp_prelaunch_audit.py`.
- If a business change causes an audit script to fail, fix the application code — not the audit script.
- The only permitted reason to edit an audit script is when the user explicitly says "update the audit script for X" with a clear scope description.

**Never silence audit failures.**
- Do not change expected counts, thresholds, or pass conditions in audit scripts to make them pass.
- Do not wrap audit calls in try/except to suppress failures.
- A failing audit script means the application has a bug. Fix the bug.

**Audit scripts are the ground truth.**
- If application code and an audit script disagree, the audit script is correct by default.
- If you believe an audit script has a genuine defect, stop and explain why before touching it.

**Run audits after every change.**
After any code change, run in order:
```
python -m compileall app.py routes services scripts
python scripts\source_integrity_audit.py
python scripts\erp_prelaunch_audit.py
```
For changes touching inventory, also run:
```
set PG_PASSWORD=admin && python scripts\audit_inventory_balance_consistency.py
```
For changes touching permissions or navigation:
```
set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=admin && python scripts\audit_trial_visible_navigation.py
set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=admin && python scripts\audit_trial_direct_access_matrix.py
```
Do not declare work complete until all relevant audit scripts pass with their expected output.

## Verification

Before declaring ERP work complete, run the following checks in order and confirm each expected output:

| Script | Command | Expected Output |
|--------|---------|----------------|
| Python compile | `python -m compileall app.py routes services scripts` | No syntax errors |
| Source integrity | `python scripts\source_integrity_audit.py` | `source_integrity=ok`, `source_mojibake_findings=0` |
| Prelaunch audit | `python scripts\erp_prelaunch_audit.py` | `errors=0`, `warnings=0`, `core_pages=34` |
| CRUD completeness | `python scripts\audit_erp_crud_completeness.py` | `targets=46`, `OK=46`, `errors=0` |

For changes touching inventory, also run:

| Script | Command | Expected Output |
|--------|---------|----------------|
| Inventory consistency | `set PG_PASSWORD=admin && python scripts\audit_inventory_balance_consistency.py` | `findings=0` |

For changes touching permissions or navigation, also run:

| Script | Command | Expected Output |
|--------|---------|----------------|
| Visible navigation | `set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=admin && python scripts\audit_trial_visible_navigation.py` | `checked_users=7`, no unexpected routes |
| Direct access matrix | `set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=admin && python scripts\audit_trial_direct_access_matrix.py` | PASS |

Do not declare work complete if any script produces output outside its expected range. Verify the exact business workflow affected by the change, not only the HTTP response status.

## Document Entry and List Separation Rule

- Document entry pages and document list/query/workbench pages must remain separated in navigation and page layout.
- A document list answers "which documents exist"; a document entry/detail page answers "what is this one document and which state actions can be performed on it".
- Do not place create/new document actions inside document list shortcuts, workbench shortcut strips, report pages, or query pages.
- Do not treat a list page modal, inline drawer, or popup form as a proper ERP document. If the action creates a business voucher, it must have its own document-entry route and its own document-detail route.
- A proper ERP document must have an independent route, document number, header, line grid, source document, status, save/submit/audit/reverse-audit/void/print actions where applicable, and clear inventory/finance/project-trace impact.
- Lists may provide search, filters, sorting, status, next action, batch print/export, and links to document entry or detail pages only. They must not own heavy header/detail-line editing.
- Every normal-menu create route must live under a labeled document-entry group such as `生产单据`, `采购单据`, `销售单据`, or `库存单据`.
- List, query, report, and workbench pages may link to detail or processing actions for existing records, but they must not expose standalone new-document buttons unless the page itself is classified as document entry.
- For production, `/work-orders/new` is a production document-entry route; `/work-orders` is the production work-order list/workbench route. They must not be mixed.
- For outsourcing, `/subcontract_issue` and `/subcontract_receive` are document lists only. Outsourcing issue and receive creation must use independent document-entry pages such as `/subcontract_issue/new` and `/subcontract_receive/new`, and details must use independent document-detail pages such as `/subcontract_issue/<id>` and `/subcontract_receive/<id>`.

## Material Entry Rule

- In all document-entry line grids, operators search/select materials from the `物料名称` field only.
- Do not expose a separate editable `物料` selector column in document-entry line grids.
- Keep hidden `product_id` fields for backend submission, and auto-fill material code, specification, unit, price/cost, and other snapshots after the material name is selected.
