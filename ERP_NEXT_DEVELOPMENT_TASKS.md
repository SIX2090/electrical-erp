# ERP Next Development Tasks

Date: 2026-06-16

This task list turns `docs/erp_development_blueprint_20260616.md` into executable development work. It follows the current project rule: stabilize existing core business loops before adding new routes, tables, modules, menus, or reports.

## Execution Rules

- Define the affected business loop and page type before code changes.
- Prefer one small loop repair at a time.
- Do not add routes, schema fields, menus, modules, finance posting rules, inventory posting rules, settlement logic, or period-close behavior unless the active task explicitly requires it.
- Keep workbench, document entry, document list, query list, report, master data, finance, and system admin pages separate.
- Reports remain read-only unless the route is explicitly a document workflow.
- Any route change must update permission registration, route catalog, and menu rollout classification.
- Any schema change must be written into `services/schema_migrations.py` after a pre-migration backup.
- Any Chinese UI text change must pass source integrity checks before completion.

## Verification Baseline

Run this baseline before starting a development batch and after each completed batch:

```cmd
.venv\Scripts\python.exe -m compileall app.py routes services scripts
.venv\Scripts\python.exe scripts\source_integrity_audit.py
.venv\Scripts\python.exe scripts\erp_prelaunch_audit.py
.venv\Scripts\python.exe scripts\audit_erp_crud_completeness.py
```

Additional checks:

```cmd
set PG_PASSWORD=admin && .venv\Scripts\python.exe scripts\audit_inventory_balance_consistency.py
set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=admin && .venv\Scripts\python.exe scripts\audit_trial_visible_navigation.py
set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=admin && .venv\Scripts\python.exe scripts\audit_trial_direct_access_matrix.py
offline_one_click_install.cmd /audit
```

## 2026-06-16 Finance Phase 1 Progress

Completed after reading the finance blueprint:

- Updated AR/AP document audits to follow canonical `/finance/...` routes instead of legacy compatibility paths.
- Added canonical finance receipt/payment document routes to `MENU_ROLLOUT_CLASSIFICATION.md`.
- Proved first-machine finance settlement workflow with project and serial traceability.
- Recorded evidence in `docs/finance_phase1_operator_workflow_evidence_20260616.md`.
- No installer package was built.

Validation passed:

- `compileall app.py routes services scripts`
- `audit_finance_phase1_closure.py`
- `audit_finance_ar_documents.py`
- `audit_finance_ap_documents.py`
- `audit_finance_kingdee_blueprint_phase1.py`
- `audit_trial_visible_navigation.py`
- `audit_trial_direct_access_matrix.py`
- `source_integrity_audit.py`
- `erp_prelaunch_audit.py`
- `audit_erp_crud_completeness.py`
- `audit_first_machine_finance_settlement.py`

## P0: Baseline And Safety Net

### P0-01: Re-run Current Baseline Audits

Priority: P0

Goal: prove the current extracted package is still stable before feature or repair work.

Scope:

- No business code change.
- Run compile, source integrity, prelaunch, CRUD completeness.
- Run visible navigation and direct access matrix.
- Run installer audit.

Likely files:

- No file edits expected.
- Audit outputs may land under `logs`.

Acceptance:

- Compile has no syntax errors.
- Source integrity reports no mojibake or replacement-character findings.
- Prelaunch audit reports zero errors.
- CRUD completeness reports all configured targets OK.
- Visible navigation and direct access matrix have no unexpected route exposure.
- Installer audit passes.

### P0-02: Create Loop Acceptance Worksheet

Priority: P0

Goal: create a simple checklist for proving each core loop by operator action, not just HTTP 200.

Scope:

- Add a Markdown worksheet under `docs`.
- Track loop name, source document, target document, owner, route, test account, operation steps, expected data effect, report reconciliation, blocked reason, next action, and result.
- Do not change application code.

Likely files:

- `docs/erp_loop_acceptance_worksheet_20260616.md`

Acceptance:

- Worksheet covers sales, purchase, engineering/BOM, production, subcontracting, inventory, service, and finance.
- Worksheet references existing routes only.
- No new route or schema requirement is introduced.

### P0-03: Confirm Route Classification Consistency

Priority: P0

Goal: make sure live, readonly, hidden, internal, and fix route states match normal navigation and permissions.

Scope:

- Audit existing `MENU_ROLLOUT_CLASSIFICATION.md`, `services/pilot_permissions.py`, and route catalog.
- Fix documentation or registration only when an inconsistency is proven.
- Do not expose hidden placeholder pages.

Likely files:

- `MENU_ROLLOUT_CLASSIFICATION.md`
- `services/pilot_permissions.py`
- `routes/route_catalog.py`

Acceptance:

- Every normal menu route has a classification.
- Every live route needed by a normal role has permission coverage.
- Hidden routes are not visible in normal navigation.
- Visible navigation and direct-access audits pass.

## P1: Core Loop Proof

### P1-01: Sales Order To Shipment To Receivable Proof

Priority: P1

Business loop: sales order -> shipment -> invoice/receivable -> receipt follow-up.

Goal: prove an operator can trace a sales order through delivery and receivable evidence.

Scope:

- Use existing sales order, shipment, invoice, receivable, and receipt pages.
- Verify project number and machine serial number display where existing data supports them.
- Verify sales list pages show status, next action, or blocked reason where implemented.
- Keep sales reports read-only.

Likely files if defects are found:

- `routes/sales*.py` or sales-related routes in `app.py`
- `services/sales_*_service.py`
- `templates/sales_order_list.html`
- `templates/shipment_detail.html`
- `templates/reports/*sales*.html`

Acceptance:

- Sales order detail can be opened from list/search.
- Shipment evidence links back to source order where current schema supports it.
- Receivable or invoice evidence can be reconciled from existing reports.
- No sales report writes business data.

### P1-02: Purchase Request To Receipt To Payable Proof

Priority: P1

Business loop: purchase request -> purchase order -> receipt -> invoice/payable -> payment follow-up.

Goal: prove purchase execution and finance reconciliation can be followed without mixing ownership.

Scope:

- Use existing purchase request, order, receipt, invoice, payable, and payment routes.
- Verify purchase receipt inventory evidence is visible but posting remains controlled.
- Verify received-not-invoiced reports remain read-only.

Likely files if defects are found:

- `routes/purchase*.py`
- `services/payable_posting_service.py`
- `templates/purchase_request*.html`
- `templates/purchase_order*.html`
- `templates/purchase_receipt*.html`
- `templates/payable_list.html`

Acceptance:

- Purchase request and purchase order are separated as document entry/list pages.
- Receipt evidence can be traced to order and material lines.
- Payable view belongs to finance and does not become a purchase document page.
- No new posting rule is introduced.

### P1-03: Inventory Posting And Balance Proof

Priority: P1

Business loop: inventory document -> stock posting -> balance -> transaction trace -> report.

Goal: prove controlled inventory documents update or reconcile balance evidence correctly.

Scope:

- Use existing inbound, outbound, transfer, adjustment, check, assembly, or disassembly document flows.
- Verify stock transaction trace and balance drill-down.
- Keep inventory reports read-only.

Likely files if defects are found:

- `services/inventory_service.py`
- `services/inventory_posting_service.py`
- `templates/inventory_*`
- `templates/transfer*.html`
- `templates/check*.html`
- `templates/reports/*inventory*.html`

Acceptance:

- Inventory list, entry, detail, query, and report pages remain separate.
- Inventory consistency audit returns no findings after fixes.
- Balance and transaction trace agree for the tested document.

### P1-04: Engineering BOM To Kitting Readiness Proof

Priority: P1

Business loop: sales/project trace -> engineering confirmation -> BOM/routing/drawing readiness -> kitting shortage.

Goal: prove engineering readiness surfaces blockers before production execution.

Scope:

- Use existing engineering technical confirmation, BOM, drawing, routing, work center, and kitting pages.
- Verify missing BOM, routing, drawing, inspection basis, tooling, or ECN impact appears as a blocker where supported.
- Keep drawing ledger as ERP metadata only.

Likely files if defects are found:

- `routes/engineering*.py`
- `routes/bom*.py`
- `services/production_execution_service.py`
- `templates/engineering_*`
- `templates/bom*.html`

Acceptance:

- Engineering pages do not act as production work-order entry pages.
- BOM/ECN pages do not mutate inventory, production, or finance documents directly.
- Kitting readiness can be reviewed from existing data.

### P1-05: Work Order To Issue To Completion Proof

Priority: P1

Business loop: work order -> material issue/return -> operation report -> completion inbound -> WIP/cost evidence.

Goal: prove the production execution loop can be followed and reconciled by project/serial where available.

Scope:

- Use existing work order, production issue, production return, operation report, completion, and production report routes.
- Verify `/work-orders` and `/work-orders/new` remain distinct by page type.
- Keep cost reports read-only unless an explicit accounting rule is provided.

Likely files if defects are found:

- `routes/production*.py`
- `services/work_order_material_service.py`
- `services/work_order_cost_service.py`
- `services/production_execution_service.py`
- `templates/work_order*.html`
- `templates/production_*`

Acceptance:

- Work order creation, list, detail, issue, return, operation, and completion behavior are not mixed into one ambiguous page.
- Production report pages do not post inventory or finance.
- Operators can identify shortage, WIP, completion status, and next action.

### P1-06: Subcontracting Issue And Receive Proof

Priority: P1

Business loop: subcontract order -> issue to processor -> receive from processor -> variance/WIP -> payable follow-up.

Goal: prove outsourcing execution has clear document boundaries and reconciliation evidence.

Scope:

- Use existing subcontract order, issue, receive, WIP, execution, variance, and payable reconciliation routes.
- Ensure issue and receive creation use document-entry pages, not list-page editing.
- Keep subcontract payable reconciliation read-only.

Likely files if defects are found:

- `routes/subcontract*.py`
- `templates/subcontract*.html`
- `templates/reports/*subcontract*.html`

Acceptance:

- Subcontract issue and receive lists remain lists only.
- Issue and receive document details show source, quantity, variance, and next action where supported.
- Reports reconcile existing documents without posting finance.

### P1-07: Service Order To RMA Closure Proof

Priority: P1

Business loop: service card -> service order -> RMA -> recovery/cost follow-up.

Goal: prove service and RMA records carry owner, blocked reason, next action, and downstream impact.

Scope:

- Use existing service card, service order, service acceptance, and RMA routes.
- Verify service-order detail RMA creation behavior remains consistent with standalone RMA entry.
- Keep service finance/cost behavior read-only unless settlement rules are explicitly defined.

Likely files if defects are found:

- `routes/service*.py`
- `services/after_sale_service.py`
- `templates/service_*`

Acceptance:

- Linked RMA has non-empty owner and next action when still open.
- Source service order reflects RMA handling state.
- Service workbench remains a queue and exception surface.

### P1-08: Finance AR/AP Reconciliation Proof

Priority: P1

Business loop: receivable/payable -> receipt/payment -> aging/statement/cash-bank reconciliation.

Goal: prove finance-owned workflows remain role-restricted and reconcilable.

Scope:

- Use existing customer receipt, supplier payment, AR/AP, cash-bank, aging, and statement routes.
- Verify finance reports state clear metric basis where visible.
- Do not change settlement, period close, voucher, tax, bad debt, fund transfer, or statutory report behavior.

Likely files if defects are found:

- `routes/finance*.py`
- `services/payable_posting_service.py`
- `templates/finance_*`
- `templates/receivable_list.html`
- `templates/payable_list.html`

Acceptance:

- Finance document pages are restricted to finance/admin roles according to existing permission policy.
- AR/AP reports are read-only.
- No route handler writes finance tables directly when a posting service should own the write.

## P2: Operator Experience Hardening

### P2-01: Document Entry Grid Consistency

Priority: P2

Goal: make high-frequency document-entry line grids behave consistently.

Scope:

- Review sales, purchase, inventory, production, subcontracting, and service document-entry templates.
- Material selection should be based on material name search with hidden backend IDs where applicable.
- Auto-fill material code, specification, unit, price/cost/tax where current data supports it.
- Persist any frequent custom fields that operators rely on.

Acceptance:

- No frontend-only business field is presented as saved data.
- Detail grids remain compact, searchable, and keyboard-friendly.
- Source integrity and prelaunch audits pass.

### P2-02: List Page Search And Next Action Consistency

Priority: P2

Goal: make document lists useful for daily follow-up.

Scope:

- Review list pages for status, date, partner, material, document number, project number, serial number, owner, blocked reason, and next action.
- Add missing filters or columns only where backed by existing data.
- Do not turn list pages into document-entry pages.

Acceptance:

- Each reviewed list has clear status and follow-up cues.
- Search/filter behavior uses existing schema fields.
- No report or list owns heavy document editing.

### P2-03: Report Read-Only Governance Pass

Priority: P2

Goal: ensure report pages remain trustworthy reconciliation surfaces.

Scope:

- Review sales, purchase, inventory, production, subcontracting, service, and finance reports.
- Confirm report controls are limited to query, reset, refresh, export, print, and drill-down.
- Hide or mark placeholder reports that cannot reconcile current tables.

Acceptance:

- Report controls audit passes where available.
- Reports do not expose create, submit, audit, void, post, settle, or close actions.
- Each reviewed report has clear source table and metric basis.

### P2-04: Master Data Practicality Pass

Priority: P2

Goal: make master data maintenance support core loops without becoming transaction pages.

Scope:

- Review material, customer, supplier, warehouse, location, unit, department, employee, category, project master, and machine serial master pages.
- Ensure import/export/template behavior is available where already implemented.
- Ensure trace/detail links do not duplicate business document entrances.

Acceptance:

- Master data pages maintain reference attributes only.
- Historical free-text categories are not treated as the only category source when category master exists.
- Master pages do not show duplicate shortcut strips or fake process actions.

## P3: Package And Trial Operations

### P3-01: Offline Package Refresh Procedure

Priority: P3

Goal: make future trial packages reproducible after development batches.

Scope:

- Document the exact packaging sequence after audits pass.
- Refresh `db/wms_current.dump` only after the application is stable.
- Exclude `.venv`, `pgdata`, `logs`, `__pycache__`, `.pytest_cache`, runtime secrets, and local backup dumps.

Acceptance:

- Extracted package passes `offline_one_click_install.cmd /audit`.
- Start and restart commands work on a clean trial machine.
- Package info reflects the current package build.

### P3-02: Backup And Restore Drill Evidence

Priority: P3

Goal: ensure go-live operations can prove recoverability.

Scope:

- Run or document backup and restore drill flow using existing scripts.
- Surface latest restore drill evidence in system admin views where already supported.
- Do not add web-based destructive restore actions.

Acceptance:

- Backup dump can be produced.
- Restore drill result is recorded.
- Operations manual remains aligned with the actual scripts.

## First Recommended Batch

Start with this batch:

1. P0-01: Re-run Current Baseline Audits.
2. P0-02: Create Loop Acceptance Worksheet.
3. P1-01: Sales Order To Shipment To Receivable Proof.
4. P1-02: Purchase Request To Receipt To Payable Proof.
5. P1-03: Inventory Posting And Balance Proof.

Reason:

These tasks prove the package, the acceptance method, and the three highest-frequency loops before production, subcontracting, service, and finance refinements. They should reveal whether the next work is page usability, data linkage, posting consistency, or report reconciliation.

## Completion Record Template

Use this format at the bottom of this file or in a separate handoff note after each completed task:

```text
Task:
Date:
Operator role:
Routes tested:
Data used:
Defect found:
Files changed:
Audits run:
Result:
Remaining risk:
Next task:
```

## Completion Records

## Phase D: Operations Quality Improvement

Date: 2026-06-23

Phase D starts only after Phase B engine deepening and Phase C finance phase 2 are considered complete. The execution boundary is defined in `ERP_BOUNDARY_STABILIZATION.md` under `Phase D Operations Quality Boundary`.

### D0: Baseline And Route Governance

Priority: D0

Goal: prove the current package is stable before touching quality, scheduling, print, or mobile execution.

Scope:

- Run compile, source integrity, prelaunch, CRUD completeness, visible navigation, and direct access matrix.
- Confirm `/production-enhance/quality-inspections`, `/production-schedules`, `/system/print-templates`, and `/mobile/scan` are governed by route classification and permission expectations.
- Do not add routes, menus, schema fields, posting rules, finance rules, or inventory rules.

Acceptance:

- Baseline audits pass.
- Existing Phase D surfaces are classified and permissioned.
- Any defect found is fixed as a minimal existing-route bug fix.

### D0-UX: Traditional ERP Page Operation Standard

Priority: D0

Goal: make document, list, and report pages feel like conventional manufacturing ERP pages instead of sparse web pages.

Scope:

- Document detail pages should expose top toolbar actions for new, edit/save, submit/audit/close where applicable, source/detail drill-down, print, refresh, exit, and previous/next document navigation.
- Document list pages should expose search/filter, refresh, print, copy/export, import/template where applicable, batch selection where applicable, status, next action, and detail links.
- Report pages should expose query, reset, refresh, print, export, and drill-down only; they must not expose document write actions.
- Apply first to Phase D quality, scheduling, attachment/print, and mobile-adjacent pages, then scan the same pattern across core ERP pages.

Acceptance:

- Operators can find the common toolbar action without scrolling.
- Toolbars are status-aware and page-type aware.
- The page does not mix document entry, list, report, or workbench responsibilities.
- Source integrity and prelaunch audits pass after each batch.

### D1: Quality Management Hardening

Priority: D1

Goal: make quality inspection and nonconformance handling reliable enough to gate completion, rework, scrap, and release.

Scope:

- Stabilize existing quality inspection entry, list, detail, audit, close, attachment, and report behavior.
- Align incoming inspection evidence with purchase receipt follow-up where existing data supports it.
- Align completion inspection evidence with work-order completion readiness where existing data supports it.
- Align service repair quality evidence with service order and RMA follow-up where existing data supports it.
- Verify work-order quality summaries show release status, failed quantity, blocked reason, next action, owner, and downstream impact.
- Keep quality reports read-only.
- Do not create a new quality module, new CAPA module, or automatic quality closure engine.

Acceptance:

- Operators can trace a work order to its inspection record and back.
- Failed or held inspections surface owner, blocked reason, next action, and downstream impact.
- Quality release does not bypass existing work-order, inventory, or finance ownership.

### D2: Production Scheduling Hardening

Priority: D2

Goal: make existing production schedules useful for daily dispatch and rescheduling.

Scope:

- Stabilize existing production schedule list/detail/edit and dispatch controls.
- Show work order, project number, machine serial number, work center, planned dates, dispatch status, responsible person, blocked reason, next action, and downstream impact where existing data supports it.
- Review whether the existing schedule surface can show work-center workload, daily capacity, and conflict warnings from current tables.
- Keep start/finish operation reporting owned by existing operation-report or work-order execution pages.
- Keep `/production-schedules` as a schedule/query/dispatch surface, not a work-order entry page.
- Do not build APS, finite-capacity optimization, automatic dispatch, or new calendar/Gantt engines in this phase.

Acceptance:

- Operators can identify which schedule line is ready, blocked, dispatched, rescheduled, paused, or completed.
- Schedule state can be reconciled with the work order and work center.
- No production document entry action is moved into the schedule list.

### D3: Attachment And Print Output Hardening

Priority: D3

Goal: make document attachments and print output usable for shop-floor and office handoff.

Scope:

- Stabilize existing document attachment panels and print template maintenance.
- Cover contract, drawing, inspection report, and business-document attachment use cases only where existing document detail pages already support attachments.
- Verify representative document print/preview behavior for production, warehouse, purchase, sales, service, and finance where existing print routes exist.
- Keep batch export limited to existing export surfaces and existing data-permission rules.
- Keep print templates system-owned and source documents business-owned.
- Do not replace the current print-template engine or introduce new document state transitions from print actions.

Acceptance:

- Attachments can be uploaded, viewed, and removed only on existing supported document detail pages.
- Printing and previewing do not mutate document status or posting state.
- Print-template permissions remain system-admin governed.

### D4: Mobile Scan Hardening

Priority: D4

Goal: make the existing mobile scan surface safe for warehouse and production-side quick execution.

Scope:

- Stabilize `/mobile/scan`, material lookup, scan submit, and result feedback.
- Limit mobile write actions to existing controlled scan modes and existing posting paths.
- Review mobile warehouse inbound/outbound usability and mobile production operation reporting only where an existing desktop workflow already owns the business action.
- Ensure read-only users can query but cannot submit stock-changing actions.
- Do not build a full mobile ERP replacement, new app shell, or offline synchronization.

Acceptance:

- Mobile scan can query material and stock trace data.
- Authorized users can submit only allowed scan actions.
- Unauthorized or read-only users cannot post movement through mobile endpoints.
- Mobile results reconcile with existing stock trace and audit expectations.

```text
Task: P0-01 Re-run Current Baseline Audits
Date: 2026-06-16
Operator role: audit scripts
Routes tested: compile/source/prelaunch/CRUD/inventory/navigation/direct-access/installer baseline
Data used: packaged local PostgreSQL database
Defect found: PostgreSQL had a stale postmaster.pid from a previous interrupted runtime; after verifying no process owned the PID and no port was listening, the stale PID file was removed and PostgreSQL was started. Visible navigation then exposed a real governance gap for /system/version-updates.
Files changed: services/pilot_permissions.py, MENU_ROLLOUT_CLASSIFICATION.md
Audits run: compileall, source_integrity_audit, erp_prelaunch_audit, audit_erp_crud_completeness, audit_inventory_balance_consistency, audit_trial_visible_navigation, audit_trial_direct_access_matrix, offline_one_click_install /audit
Result: passed after repairing /system/version-updates permission and rollout classification
Remaining risk: browser-level manual operator QA was not run in this batch
Next task: continue P1 loop proof for production, subcontracting, service, and finance
```

```text
Task: P0-02 Create Loop Acceptance Worksheet
Date: 2026-06-16
Operator role: planning/audit
Routes tested: none
Data used: current blueprint, route classification, project runtime defaults
Defect found: none
Files changed: docs/erp_loop_acceptance_worksheet_20260616.md
Audits run: source_integrity_audit after document and P0 fixes
Result: passed
Remaining risk: remaining loops still need operator-level proof beyond available audit scripts
Next task: continue P1 loop proof
```

```text
Task: P1-01 Sales Order To Shipment To Receivable Proof
Date: 2026-06-16
Operator role: pilot sales, pilot production, pilot warehouse
Routes tested: /shipments, /service-cards, /receivables, /projects, /transactions
Data used: project PJ-GT-TRIAL-20260526-001, serial SN-GT-TRIAL-20260526-001
Defect found: none
Files changed: docs/erp_loop_acceptance_worksheet_20260616.md
Audits run: scripts/audit_first_machine_completion_shipment_finance.py
Result: passed
Remaining risk: manual browser workflow for creating a fresh sales order was not run in this batch; audit verified the packaged representative loop
Next task: continue P1-02 and P1-03
```

```text
Task: P1-02 Purchase Request To Receipt To Payable Proof
Date: 2026-06-16
Operator role: pilot purchase, pilot production
Routes tested: /engineering/kitting, /production-enhance/mrp-requirements, /procurement/suggestions, /purchase_request, /purchase-orders, /purchase_receipts, /payables, /projects
Data used: project PJ-GT-TRIAL-20260526-001, serial SN-GT-TRIAL-20260526-001
Defect found: none
Files changed: docs/erp_loop_acceptance_worksheet_20260616.md
Audits run: scripts/audit_first_machine_procurement.py, scripts/audit_first_machine_purchase_to_receipt.py
Result: passed
Remaining risk: manual browser workflow for a new supplier scenario was not run in this batch; audit verified the packaged representative loop
Next task: continue P1-03
```

```text
Task: P1-03 Inventory Posting And Balance Proof
Date: 2026-06-16
Operator role: pilot warehouse, admin
Routes tested: /transfers, /inventory_checks, /adjustments, /transactions, /inventory, /inventory/detail, /projects
Data used: project PJ-GT-TRIAL-20260526-001, serial SN-GT-TRIAL-20260526-001
Defect found: none
Files changed: docs/erp_loop_acceptance_worksheet_20260616.md
Audits run: scripts/audit_first_machine_inventory_execution.py, scripts/audit_first_machine_inventory_trace.py, scripts/audit_inventory_balance_consistency.py
Result: passed
Remaining risk: manual browser workflow for a new inventory movement was not run in this batch; audit verified the packaged representative loop and balance consistency
Next task: P1-04 Engineering BOM To Kitting Readiness Proof
```

```text
Task: P1-04 Engineering BOM To Kitting Readiness Proof
Date: 2026-06-16
Operator role: engineering, production
Routes tested: engineering technical confirmation, engineering drawings, BOM, BOM ECN, routing, work center, kitting readiness, read-only readiness APIs
Data used: current packaged engineering/BOM readiness records
Defect found: none
Files changed: docs/erp_loop_acceptance_worksheet_20260616.md
Audits run: scripts/audit_engineering_bom_routing_readiness.py, scripts/audit_phase2_sales_engineering_bom_kitting.py
Result: passed
Remaining risk: manual browser creation of a fresh technical confirmation was not run in this batch
Next task: P1-05 Work Order To Issue To Completion Proof
```

```text
Task: P1-05 Work Order To Issue To Completion Proof
Date: 2026-06-16
Operator role: production
Routes tested: work order, production issue/return/completion, operation/cost closure APIs, stock transaction evidence
Data used: project PJ-GT-TRIAL-20260526-001, serial SN-GT-TRIAL-20260526-001
Defect found: none
Files changed: docs/erp_loop_acceptance_worksheet_20260616.md
Audits run: scripts/audit_phase4_production_closure.py, scripts/audit_first_machine_work_order_issue.py
Result: passed
Remaining risk: manual browser creation of a fresh work order was not run in this batch
Next task: P1-06 Subcontracting Issue And Receive Proof
```

```text
Task: P1-06 Subcontracting Issue And Receive Proof
Date: 2026-06-16
Operator role: purchase/outsourcing
Routes tested: /subcontract, /subcontract_issue, /subcontract_receive, /payables, /projects, project ledger phase-5 events
Data used: project PJ-GT-TRIAL-20260526-001, serial SN-GT-TRIAL-20260526-001, subcontract OS-GT-TRIAL-20260526-001
Defect found: none
Files changed: docs/erp_loop_acceptance_worksheet_20260616.md
Audits run: scripts/audit_first_machine_subcontract_closure.py, scripts/audit_phase5_delivery_outsourcing_service_closure.py
Result: passed
Remaining risk: manual browser creation of a fresh subcontract issue/receive was not run in this batch
Next task: P1-07 Service Order To RMA Closure Proof
```

```text
Task: P1-07 Service Order To RMA Closure Proof
Date: 2026-06-16
Operator role: service
Routes tested: /service-cards, /service-acceptance, /service-orders, /service-rmas, /projects
Data used: project PJ-GT-TRIAL-20260526-001, serial SN-GT-TRIAL-20260526-001, service order SV-GT-TRIAL-20260526-001
Defect found: none
Files changed: docs/erp_loop_acceptance_worksheet_20260616.md
Audits run: scripts/audit_after_sale_service_boundary.py, scripts/audit_after_sale_boundary.py, scripts/audit_first_machine_service_closure.py
Result: passed
Remaining risk: manual browser creation of a fresh RMA was not run in this batch
Next task: P1-08 Finance AR/AP Reconciliation Proof
```

```text
Task: P1-08 Finance AR/AP Reconciliation Proof
Date: 2026-06-16
Operator role: finance
Routes tested: /receivables, /payables, /finance, /projects, customer AR document routes, supplier AP document routes, /finance/period-close, /finance/financial-statements
Data used: project PJ-GT-TRIAL-20260526-001, serial SN-GT-TRIAL-20260526-001, sales order SO-GT-TRIAL-20260526-001, purchase order PO-PJ-GT-TRIAL-20260526-001
Defect found: finance role could not access /receivables and /payables in the settlement audit; AR/AP formal document routes were not aligned between finance navigation and pilot permission groups.
Files changed: services/pilot_permissions.py, MENU_ROLLOUT_CLASSIFICATION.md, templates/base.html, docs/erp_loop_acceptance_worksheet_20260616.md
Audits run: scripts/audit_first_machine_finance_settlement.py, scripts/audit_first_machine_period_close_readiness.py, scripts/audit_finance_ar_documents.py, scripts/audit_finance_ap_documents.py, scripts/audit_finance_phase1_closure.py, scripts/audit_trial_visible_navigation.py, scripts/audit_trial_direct_access_matrix.py
Result: passed after repairing finance AR/AP permission and navigation governance
Remaining risk: manual browser entry of a fresh receipt/payment document was not run in this batch
Next task: P2-01 Document Entry Grid Consistency
```

```text
Task: P2-01 Document Entry Grid Consistency
Date: 2026-06-16
Operator role: admin, sales, purchase, warehouse, production, finance, service
Routes tested: /sales/new, /purchase_order/new, /inventory/inbound, /inventory/outbound, /transfers/new, /adjustments/new, /inventory_checks/new, inventory bulk document lists, purchase request readiness, report pages
Data used: packaged trial database and existing audit probes
Defect found: none
Files changed: ERP_NEXT_DEVELOPMENT_TASKS.md
Audits run: scripts/audit_document_material_name_entry.py, scripts/audit_trial_core_document_fields.py, scripts/audit_inventory_movement_line_fields.py, scripts/audit_order_edit_execution_quantities.py, scripts/audit_trial_action_boundary.py, scripts/audit_inventory_bulk_list_actions.py, scripts/audit_inventory_bulk_list_runtime.py, scripts/audit_purchase_request_detail_blockers.py, scripts/audit_purchase_request_downpush_readiness.py, scripts/audit_report_print_controls.py
Result: passed
Remaining risk: this batch used automated audits and route-level checks; manual browser keyboard-entry testing for every document grid was not run
Next task: P2-02 List Page Search And Next Action Consistency
```

```text
Task: P2-02 List Page Search And Next Action Consistency
Date: 2026-06-16
Operator role: admin, sales, purchase, warehouse, production, service, finance
Routes tested: homepage task queues, /projects, /sales-orders, /engineering/kitting, /purchase_request, /purchase_receipts, /subcontract_issue, /subcontract_receive, /requisition, /shipments, /receivables, /payables, /service-orders, inventory document lists, purchase/production module roots, report/list pages covered by full audit
Data used: packaged trial database and existing audit probes
Defect found: none
Files changed: ERP_NEXT_DEVELOPMENT_TASKS.md
Audits run: scripts/audit_trial_operator_task_queues.py, scripts/audit_module_root_routes.py, scripts/audit_inventory_bulk_list_runtime.py, scripts/audit_purchase_module_boundary.py, scripts/audit_production_module_closure.py, scripts/audit_homepage_bug_candidates.py, scripts/audit_sales_dashboard_boundary.py, scripts/audit_inventory_operation_gaps.py, scripts/run_full_erp_audit.py
Result: passed
Remaining risk: automated route and marker checks passed; manual operator review of every list filter combination was not run
Next task: P2-03 Report Read-Only Governance Pass
```

```text
Task: P2-03 Report Read-Only Governance Pass
Date: 2026-06-16
Operator role: admin, finance, warehouse, production, purchase, sales, service
Routes tested: report center, finance counterparty reports, inventory return/report pages, subcontract report coverage, visible navigation, direct access matrix
Data used: packaged trial database and existing audit probes
Defect found: finance base navigation missed /finance/reports/payment-request-statistics; report center index missed five inventory subcontract report entries already present in menu/permission/data registration.
Files changed: templates/base.html, routes/report_routes.py, ERP_NEXT_DEVELOPMENT_TASKS.md
Audits run: scripts/audit_finance_counterparty_reports.py, scripts/audit_subcontract_report_coverage.py, scripts/audit_report_print_controls.py, scripts/audit_report_performance.py, scripts/audit_inventory_return_and_reports.py, scripts/source_integrity_audit.py, scripts/erp_prelaunch_audit.py, scripts/audit_erp_crud_completeness.py, scripts/audit_trial_visible_navigation.py, scripts/audit_trial_direct_access_matrix.py, python -m compileall app.py routes services scripts
Result: passed after repairing finance report navigation and subcontract report center registration
Remaining risk: automated route, marker, permission, and read-only checks passed; manual operator review of every report filter combination was not run
Next task: P2-04 Master Data Practicality Pass
```

```text
Task: P2-04 Master Data Practicality Pass
Date: 2026-06-16
Operator role: admin
Routes tested: /material, /customer, /supplier, /warehouse, /locations, /unit, /department, /employee, /categories/product, /categories/customer, /categories/supplier, /categories/warehouse, /project-master, /machine-serial-master and their new/import/download_template entries
Data used: packaged trial database and existing audit probes
Defect found: none
Files changed: ERP_NEXT_DEVELOPMENT_TASKS.md
Audits run: scripts/audit_master_data_completion_scope.py, scripts/check_first_machine_master_data.py, scripts/audit_material_opening_boundary.py, scripts/audit_coding_rules.py, temporary master page practicality probe, scripts/source_integrity_audit.py, scripts/erp_prelaunch_audit.py, scripts/audit_erp_crud_completeness.py, python -m compileall app.py routes services scripts
Result: passed
Remaining risk: automated route, form, import/template, boundary, and coding-rule checks passed; manual operator review of every master-data field combination was not run
Next task: P3-01 Offline Package Refresh Procedure
```

```text
Task: P3-01 Offline Package Refresh Procedure
Date: 2026-06-16
Operator role: package builder
Routes tested: installer package audit, source integrity, prelaunch, CRUD baseline
Data used: existing db/wms_current.dump; database snapshot was not refreshed in this batch
Defect found: build_offline_installer_package.py excluded .venv, pgdata, logs, __pycache__, runtime_local_secrets.cmd, and generated zips, but did not exclude local backups; previous manifest evidence showed backup dumps could be packaged.
Files changed: scripts/build_offline_installer_package.py, docs/offline_package_refresh_procedure_20260616.md, PACKAGE_INFO.txt, release/offline_package_manifest.txt, ERP_NEXT_DEVELOPMENT_TASKS.md
Package built: release/offline_packages/WMS_ERP_Offline_Installer_20260616_020137.zip
Package sha256: 3c2880f9468d6940ed85ed8935c579cff670fe794969cbd1f9cfe4bb8d26196f
Audits run: python -m compileall app.py routes services scripts, scripts/source_integrity_audit.py, scripts/erp_prelaunch_audit.py, scripts/audit_erp_crud_completeness.py, scripts/audit_installer_package.py --deep, offline_one_click_install.cmd /audit, package iterator forbidden-backups probe, zip forbidden-entry probe
Result: package build passed and zip contains no runtime_local_secrets, pgdata, .venv, __pycache__, backups, or logs entries; extracted-package /audit could not be completed because all visible fixed drives reported 0 GB free and extraction failed with no space left on device.
Remaining risk: clean-machine extraction/start/restart verification still needs to be run on a machine or drive with sufficient free space.
Next task: rerun extracted package /audit after freeing disk space, then continue P3-02 Backup And Restore Drill Evidence
```

```text
Task: P3-02 Backup And Restore Drill Evidence
Date: 2026-06-16
Operator role: system administrator
Routes tested: /system/database-backups
Data used: current development PostgreSQL database, controlled temporary restore database wms_restore_drill_20260616
Defect found: operations manual restore drill command did not show the safer PG_DATABASE override to a controlled target, making it too easy to restore over the active database by mistake.
Files changed: docs/backup_restore_drill_evidence_20260616.md, OPERATIONS_MANUAL.md, ERP_NEXT_DEVELOPMENT_TASKS.md
Backup produced: backups/p302_restore_drill_20260616.dump, 1540228 bytes
Restore evidence: backups/backup_log.txt contains RESTORE_OK db=wms_restore_drill_20260616 file=p302_restore_drill_20260616.dump
Restore verification: temporary restore target returned products=23, sales_orders=2, purchase_orders=2, warehouses=5
Cleanup: temporary restore target wms_restore_drill_20260616 was dropped and verified absent
Audits run: scripts/pg_backup.py, scripts/pg_restore.py against controlled target, /system/database-backups test-client probe, python -m compileall app.py routes services scripts, scripts/source_integrity_audit.py, scripts/erp_prelaunch_audit.py, scripts/audit_erp_crud_completeness.py
Result: passed
Remaining risk: this validates local PostgreSQL dump/restore mechanics; a full clean-machine disaster recovery drill should still be repeated before production go-live.
Next task: wait for user-selected next development batch; do not build or refresh installer package until explicitly requested
```

```text
Task: P4-01 Browser Operator Acceptance Evidence
Date: 2026-06-16
Operator role: admin, sales, purchase, warehouse, production, service, finance
Routes tested: /system_settings/form, /system/database-backups, /system/data-health, /sales/new, /sales-orders, /shipments, /purchase_request/new, /purchase-orders, /purchase_receipts, /inventory/detail, /transactions, /transfers/new, /work-orders/new, /work-orders, /production-schedules, /service-orders/new, /service-orders, /service-rmas, /receivables, /payables, /finance/reports/aging, plus visible navigation sampled by role
Data used: current development PostgreSQL database and trial pilot users prepared by scripts/trial_audit_auth.py
Defect found: browser_full_human_acceptance.py could mark slow-but-successful login redirects as failed because it checked the URL too soon after pressing Enter. Its fallback base URL also used port 5001, while the project runtime default is port 5000.
Files changed: scripts/browser_full_human_acceptance.py, ERP_NEXT_DEVELOPMENT_TASKS.md
Browser evidence: logs/browser_full_human_acceptance/report.json and role screenshots under logs/browser_full_human_acceptance/
Audits run: scripts/browser_full_human_acceptance.py
Result: passed after making login wait for actual navigation completion and rerunning against http://127.0.0.1:5000; users=7, nav_checks=69, interaction_checks=21, console_warnings_errors=0
Remaining risk: this is a representative browser acceptance pass, not exhaustive manual entry of every field combination or full document posting workflow.
Next task: select the next development batch from remaining manual acceptance risk, clean-machine recovery drill, or a specific business loop requested by the user; do not build or refresh installer package until explicitly requested.
```

```text
Task: P5-01 Project Serial Data Quality And Lifecycle Trace Pass
Date: 2026-06-16
Operator role: admin, production, warehouse, finance
Routes tested: /projects, /projects/23, /production-enhance/quality-inspections, project/serial trace and first-machine lifecycle ledger audit paths
Data used: current development PostgreSQL database, project PJ-GT-TRIAL-20260526-001, serial SN-GT-TRIAL-20260526-001, quality inspection QI-PJ-GT-TRIAL-20260526-001
Defect found: the database already contained first-machine quality inspection evidence, but the project lifecycle detail event stream did not expose QI events, so the trace page could not show the full production quality step.
Files changed: routes/project_routes.py, templates/project_trace_detail.html, ERP_NEXT_DEVELOPMENT_TASKS.md
Audits run: scripts/verify_project_serial_traceability.py, scripts/audit_fk_validation_readiness.py, scripts/detailed_data_audit.py, scripts/check_first_machine_master_data.py, scripts/audit_inventory_balance_consistency.py, scripts/audit_project_serial_option.py, scripts/audit_inventory_batch_balance.py, scripts/audit_first_machine_lifecycle_ledger.py, python -m compileall app.py routes services scripts, scripts/source_integrity_audit.py, scripts/erp_prelaunch_audit.py, scripts/audit_erp_crud_completeness.py, scripts/audit_trial_visible_navigation.py, scripts/audit_trial_direct_access_matrix.py
Result: passed after adding quality inspection as a read-only project lifecycle event and label; first_machine_lifecycle_ledger_audit=ok checked_items=36, trial_visible_navigation_audit=ok checked_items=1950, trial_direct_access_matrix_audit=ok checked_items=2779 checked_paths=396
Remaining risk: verify_project_serial_traceability.py still reports 6 nonblocking orphan project/serial findings because require_project_serial=0; these should be reviewed before enabling mandatory project/serial control. Clean-machine recovery and installer package refresh were not run.
Next task: continue data-linkage cleanup for nonblocking project/serial orphan findings or run a user-selected business loop; do not build or refresh installer package until explicitly requested.
```

```text
Task: P5-02 Development Project Serial Master Data Backfill
Date: 2026-06-16
Operator role: admin
Routes tested: project/serial traceability audit paths, /project-master, /machine-serial-master through CRUD baseline
Data used: current development PostgreSQL database; audit and verification fixture project/serial pairs from work_orders, subcontract_orders, and production_completion_orders
Defect found: development verification documents contained 9 project/serial pairs without matching project_masters and machine_serial_masters records. These were fixture records from audit and loop verification scripts, not package data.
Files changed: ERP_NEXT_DEVELOPMENT_TASKS.md
Database changes: inserted 9 project_masters rows and 9 machine_serial_masters rows using the existing master-data status convention for ready/enabled/not-installed records.
Audits run: scripts/verify_project_serial_traceability.py, scripts/audit_first_machine_lifecycle_ledger.py, scripts/detailed_data_audit.py, scripts/erp_prelaunch_audit.py, scripts/audit_erp_crud_completeness.py, scripts/audit_fk_validation_readiness.py, scripts/source_integrity_audit.py
Result: baseline passed; first_machine_lifecycle_ledger_audit=ok checked_items=36, postgres_data_audit=ok, core_pages=34 errors=0 warnings=0, erp_crud_targets=46 ok=46 warnings=0 errors=0, fk_validation_readiness=ok, source_integrity=ok.
Remaining risk: scripts/verify_project_serial_traceability.py still reports 6 nonblocking orphan categories because its reference source logic reads projects, machine_service_cards, and sales_orders, but does not read the current master tables project_masters and machine_serial_masters. Per project rule, verify_*.py scripts were not modified in this batch.
Next task: either explicitly approve updating verify_project_serial_traceability.py to recognize project_masters/machine_serial_masters, or continue the next blueprint business-loop pass without changing audit scripts; do not build or refresh installer package until explicitly requested.
```

```text
Task: F1-01 Finance Phase 1 Blueprint Gap Audit And Menu Governance
Date: 2026-06-16
Operator role: finance, admin
Routes tested: finance dashboard, AR/AP workbench, finance master data, receivables, receipts, advance receipts, receipt refunds, other income, payables, payment requests, payments, advance payments, payment refunds, other expenses, AR/AP reports, visible navigation, direct access matrix
Data used: current development PostgreSQL database and existing finance audit probes
Defect found: finance phase 1 document routes existed, but the finance menu still exposed several legacy non-/finance paths for receipts, advance receipts, refunds, advance payments, and other income/expense documents.
Files changed: templates/base.html, docs/finance_phase1_gap_audit_20260616.md, ERP_NEXT_DEVELOPMENT_TASKS.md
Audits run: scripts/audit_finance_kingdee_blueprint_phase1.py, scripts/audit_finance_phase1_closure.py, scripts/audit_finance_ar_documents.py, scripts/audit_finance_ap_documents.py, scripts/audit_trial_visible_navigation.py, scripts/audit_trial_direct_access_matrix.py, python -m compileall app.py routes services scripts, scripts/source_integrity_audit.py, scripts/erp_prelaunch_audit.py, scripts/audit_erp_crud_completeness.py
Result: passed after replacing legacy menu hrefs with canonical /finance/... document entry routes; finance_kingdee_blueprint_phase1_audit=ok checked_paths=78 checked_finance_menu_hrefs=106, finance_phase1_audit=ok, visible navigation and direct access matrix passed.
Remaining risk: browser-level finance operator testing for every AR/AP form combination was not run; canonical /finance document entries currently redirect to existing working document pages instead of replacing every legacy route.
Next task: Finance Phase 1 operator workflow proof for receivable-to-receipt settlement and payable-to-payment settlement; do not build or refresh installer package until explicitly requested.
```

```text
Task: P5-03 Bug Hunter Zero Findings And Development Master Data Cleanup
Date: 2026-06-16
Operator role: admin/audit
Routes tested: frontend audit document entry routes, bug hunter exact GET route scan, /export/project-masters, /export/machine-serial-masters
Data used: current development PostgreSQL database; verification fixture project/serial master rows
Defect found: frontend audit could fail when run directly because project root was not on sys.path and PG_PASSWORD was not defaulted; bug hunter treated expected high-risk 404 routes as failures; 9 project_masters and 9 machine_serial_masters development fixture rows contained dirty ?? placeholders in status/remark fields.
Files changed: scripts/erp_frontend_bug_audit.py, scripts/erp_bug_hunter.py, docs/bug_hunter_zero_findings_evidence_20260616.md, ERP_NEXT_DEVELOPMENT_TASKS.md
Database changes: cleaned development fixture rows in project_masters and machine_serial_masters with clear Chinese status/stage/service/remark values.
Audits run: scripts/erp_frontend_bug_audit.py, scripts/erp_bug_hunter.py, python -m compileall app.py routes services scripts, scripts/source_integrity_audit.py, scripts/audit_database_mojibake.py, scripts/erp_prelaunch_audit.py, scripts/audit_erp_crud_completeness.py
Result: passed; bug_hunter findings=0, frontend findings=0, source_integrity=ok, database_mojibake_findings=0, core_pages=34 errors=0 warnings=0, erp_crud_targets=46 ok=46 warnings=0 errors=0
Remaining risk: verify_project_serial_traceability.py still has older reference-source limitations noted in P5-02; clean-machine installer extraction/recovery was not run.
Next task: continue project/serial traceability audit-source cleanup or run another user-selected blueprint business-loop batch; do not build or refresh installer package until explicitly requested.
```

```text
Task: P5-04 Project Serial Traceability Audit Source Cleanup
Date: 2026-06-16
Operator role: admin/audit
Routes tested: project/serial traceability audit sources, first-machine lifecycle ledger project trace pages
Data used: current development PostgreSQL database, project_masters, machine_serial_masters, first-machine project PJ-GT-TRIAL-20260526-001 and serial SN-GT-TRIAL-20260526-001
Defect found: verify_project_serial_traceability.py did not include project_masters and machine_serial_masters as reference sources, so valid development fixture project/serial master rows were still reported as nonblocking orphans.
Files changed: scripts/verify_project_serial_traceability.py, docs/project_serial_traceability_audit_cleanup_20260616.md, ERP_NEXT_DEVELOPMENT_TASKS.md
Database changes: none in this batch
Audits run: scripts/verify_project_serial_traceability.py, scripts/audit_first_machine_lifecycle_ledger.py, scripts/detailed_data_audit.py, python -m compileall scripts/verify_project_serial_traceability.py scripts/erp_frontend_bug_audit.py scripts/erp_bug_hunter.py, scripts/source_integrity_audit.py, scripts/erp_prelaunch_audit.py, scripts/audit_erp_crud_completeness.py, scripts/erp_bug_hunter.py
Result: passed; project_serial_traceability=ok findings=0 blocking=0, first_machine_lifecycle_ledger_audit=ok checked_items=36, postgres_data_audit=ok, source_integrity=ok, core_pages=34 errors=0 warnings=0, erp_crud_targets=46 ok=46 warnings=0 errors=0, bug_hunter findings=0
Remaining risk: mandatory project/serial control remains disabled with require_project_serial=0; clean-machine installer extraction/recovery was not run.
Next task: run another user-selected blueprint hardening batch or prepare for package/recovery only after explicit user instruction; do not build or refresh installer package until explicitly requested.
```

```text
Task: F1-03 Finance Business Exceptions Semantic Fix
Date: 2026-06-16
Operator role: finance/admin
Routes tested: /finance/business-exceptions, /finance/closing-checks, finance phase-1 menu paths, visible navigation
Data used: current development PostgreSQL database and finance route test client
Defect found: /finance/business-exceptions rendered the closing-check report, mixing business-finance exception review with period-close checks.
Files changed: routes/finance_routes.py, scripts/audit_finance_business_exceptions.py, docs/finance_business_exceptions_semantic_fix_20260616.md, ERP_NEXT_DEVELOPMENT_TASKS.md
Database changes: none
Audits run: scripts/audit_finance_business_exceptions.py, python -m compileall app.py routes services scripts, scripts/source_integrity_audit.py, scripts/audit_finance_kingdee_blueprint_phase1.py, scripts/erp_prelaunch_audit.py, scripts/audit_erp_crud_completeness.py, scripts/erp_bug_hunter.py, scripts/audit_trial_visible_navigation.py
Result: passed; finance_business_exceptions_audit=ok checked_tokens=7, source_integrity=ok, finance_kingdee_blueprint_phase1_audit=ok, core_pages=34 errors=0 warnings=0, erp_crud_targets=46 ok=46 warnings=0 errors=0, bug_hunter findings=0, trial_visible_navigation_audit=ok checked_items=1950 checked_users=7
Remaining risk: bank statement import/automatic bank reconciliation, voucher generation, period close, and statutory finance reports remain later-phase capabilities.
Next task: continue finance hardening from remaining known gaps or run another user-selected blueprint batch; do not build or refresh installer package until explicitly requested.
```

```text
Task: F1-04 Finance Cash/Bank Account Governance Fix
Date: 2026-06-16
Operator role: finance/admin
Routes tested: receipt/payment posting path through finance settlement audit, cash/bank account governance audit, finance phase-1 menu paths
Data used: current development PostgreSQL database; existing cash_bank_accounts rows and first-machine finance settlement fixture
Defect found: receipt/payment posting and cash-bank journal backfill could silently create AUTO-* placeholder cash/bank accounts when the operator entered an unmaintained account label.
Files changed: routes/finance_routes.py, scripts/backfill_cash_bank_journal.py, scripts/audit_finance_cash_bank_account_governance.py, docs/finance_cash_bank_account_governance_fix_20260616.md, ERP_NEXT_DEVELOPMENT_TASKS.md
Database changes: converted placeholder account id=1 to active BANK-DEFAULT / 开发验证默认银行账户; converted placeholder account id=2 to inactive BANK-HISTORY-UNSPECIFIED / 历史未指定资金账户. No rows were deleted.
Audits run: scripts/audit_finance_cash_bank_account_governance.py, python -m compileall app.py routes services scripts, scripts/audit_finance_phase1_closure.py, scripts/audit_first_machine_finance_settlement.py, scripts/source_integrity_audit.py, scripts/audit_finance_kingdee_blueprint_phase1.py, scripts/erp_prelaunch_audit.py, scripts/audit_erp_crud_completeness.py, scripts/erp_bug_hunter.py
Result: passed; finance_cash_bank_account_governance_audit=ok, finance_phase1_audit=ok, first_machine_finance_settlement_audit=ok checked_items=24, source_integrity=ok, finance_kingdee_blueprint_phase1_audit=ok checked_paths=78 checked_finance_menu_hrefs=106, core_pages=34 errors=0 warnings=0, erp_crud_targets=46 ok=46 warnings=0 errors=0, bug_hunter findings=0
Remaining risk: current receipt/payment documents still create one cash-bank journal entry per document while the form can record multiple payment lines; multi-line journal splitting remains a later finance refinement.
Next task: continue finance hardening from remaining known gaps, especially bank reconciliation/import, voucher generation, or multi-line funds journal splitting; do not build or refresh installer package until explicitly requested.
```

```text
Task: F1-05 Finance Cash/Bank Multiline Journal Split
Date: 2026-06-16
Operator role: finance/admin
Routes tested: receipt/payment posting helper, finance phase-1 closure, first-machine finance settlement, finance menu and cash-bank governance audits
Data used: current development PostgreSQL database and synthetic two-line cash/bank journal audit fixture
Defect found: receipt/payment forms supported multiple funds lines, but cash-bank journal posting still persisted only one journal row per document source.
Files changed: routes/finance_routes.py, scripts/backfill_cash_bank_journal.py, scripts/audit_finance_cash_bank_multiline_journal.py, docs/finance_cash_bank_multiline_journal_fix_20260616.md, ERP_NEXT_DEVELOPMENT_TASKS.md
Database changes: none in this batch
Audits run: scripts/audit_finance_cash_bank_multiline_journal.py, scripts/audit_finance_cash_bank_account_governance.py, python -m compileall app.py routes services scripts, scripts/audit_finance_phase1_closure.py, scripts/audit_first_machine_finance_settlement.py, scripts/source_integrity_audit.py, scripts/audit_finance_kingdee_blueprint_phase1.py, scripts/erp_prelaunch_audit.py, scripts/audit_erp_crud_completeness.py, scripts/erp_bug_hunter.py
Result: passed; finance_cash_bank_multiline_journal_audit=ok checked_lines=2, finance_cash_bank_account_governance_audit=ok, finance_phase1_audit=ok, first_machine_finance_settlement_audit=ok checked_items=24, source_integrity=ok, finance_kingdee_blueprint_phase1_audit=ok checked_paths=78 checked_finance_menu_hrefs=106, core_pages=34 errors=0 warnings=0, erp_crud_targets=46 ok=46 warnings=0 errors=0, bug_hunter findings=0
Remaining risk: confirmed receipt/payment edit workflow still is not a full journal rebuild path; this pass focused on new posting and historical backfill behavior.
Next task: continue finance hardening from remaining known gaps, especially bank reconciliation/import, voucher generation, period close checks, or confirmed document edit governance; do not build or refresh installer package until explicitly requested.
```

```text
Task: F1-06 Finance Bank Reconciliation Read-Only Report
Date: 2026-06-16
Operator role: finance/admin
Routes tested: /finance/bank-reconciliation, finance phase-1 menu paths, core prelaunch pages
Data used: current development PostgreSQL database, cash_bank_accounts, cash_bank_journal_entries, customer_receipts, supplier_payments
Defect found: /finance/bank-reconciliation was still a placeholder workflow entry and exposed placeholder wording instead of reconciliation evidence.
Files changed: routes/finance_routes.py, scripts/audit_finance_bank_reconciliation.py, docs/finance_bank_reconciliation_readonly_fix_20260616.md, ERP_NEXT_DEVELOPMENT_TASKS.md
Database changes: none
Audits run: scripts/audit_finance_bank_reconciliation.py, python -m compileall routes/finance_routes.py scripts/audit_finance_bank_reconciliation.py, scripts/audit_finance_kingdee_blueprint_phase1.py, scripts/audit_finance_phase1_closure.py, scripts/source_integrity_audit.py, scripts/erp_prelaunch_audit.py, scripts/audit_erp_crud_completeness.py, scripts/erp_bug_hunter.py
Result: passed; finance_bank_reconciliation_audit=ok checked_tokens=7, finance_kingdee_blueprint_phase1_audit=ok checked_paths=78 checked_finance_menu_hrefs=106, finance_phase1_audit=ok, source_integrity=ok, core_pages=34 errors=0 warnings=0, erp_crud_targets=46 ok=46 warnings=0 errors=0, bug_hunter findings=0
Remaining risk: bank statement import, automatic bank matching, manual tick-off, outstanding item generation, and formal bank balance adjustment statements remain later finance work.
Next task: continue finance hardening from remaining known gaps, especially bank statement import/matching, voucher generation, period close checks, or confirmed document edit governance; do not build or refresh installer package until explicitly requested.
```

```text
Task: F1-07 Finance Voucher Generation Preview
Date: 2026-06-16
Operator role: finance/admin
Routes tested: /finance/vouchers/generate, finance phase-1 menu paths, core prelaunch pages
Data used: current development PostgreSQL database, sales_invoices, purchase_invoices, customer_receipts, supplier_payments, vouchers
Defect found: /finance/vouchers/generate was still a static workflow/rule entry and did not show actual voucher source documents, generated voucher state, or balance state.
Files changed: routes/finance_routes.py, scripts/audit_finance_voucher_generation_preview.py, docs/finance_voucher_generation_preview_fix_20260616.md, ERP_NEXT_DEVELOPMENT_TASKS.md
Database changes: none
Audits run: scripts/audit_finance_voucher_generation_preview.py, python -m compileall routes/finance_routes.py scripts/audit_finance_voucher_generation_preview.py, python -m compileall app.py routes services scripts, scripts/audit_finance_kingdee_blueprint_phase1.py, scripts/audit_finance_phase1_closure.py, scripts/source_integrity_audit.py, scripts/erp_prelaunch_audit.py, scripts/audit_erp_crud_completeness.py, scripts/erp_bug_hunter.py
Result: passed; finance_voucher_generation_preview_audit=ok checked_tokens=7, finance_kingdee_blueprint_phase1_audit=ok checked_paths=78 checked_finance_menu_hrefs=106, finance_phase1_audit=ok, source_integrity=ok, core_pages=34 errors=0 warnings=0, erp_crud_targets=46 ok=46 warnings=0 errors=0, bug_hunter findings=0
Remaining risk: this pass does not add a voucher generation button or automatic posting; controlled generation, review, posting, and reversal remain later finance work.
Next task: continue finance hardening from remaining known gaps, especially controlled voucher generation, period close checks, confirmed document edit governance, or bank statement import/matching; do not build or refresh installer package until explicitly requested.
```

```text
Task: F1-08 Finance Period Close Voucher Date SQL Fix
Date: 2026-06-16
Operator role: finance/admin
Routes tested: /finance/period-close, /finance/financial-statements, finance phase-1 menu paths, core prelaunch pages
Data used: current development PostgreSQL database, vouchers, finance period close snapshot data
Defect found: period-close voucher draft count used vouchers.date, but the voucher schema field is voucher_date.
Files changed: routes/finance_routes.py, scripts/audit_finance_period_close_voucher_date.py, docs/finance_period_close_voucher_date_fix_20260616.md, ERP_NEXT_DEVELOPMENT_TASKS.md
Database changes: none
Audits run: scripts/audit_finance_period_close_voucher_date.py, python -m compileall routes/finance_routes.py scripts/audit_finance_period_close_voucher_date.py, scripts/audit_first_machine_period_close_readiness.py, scripts/audit_finance_phase1_closure.py, scripts/audit_finance_kingdee_blueprint_phase1.py, scripts/source_integrity_audit.py, scripts/erp_prelaunch_audit.py, scripts/audit_erp_crud_completeness.py, scripts/erp_bug_hunter.py
Result: passed; finance_period_close_voucher_date_audit=ok, first_machine_period_close_readiness_audit=ok checked_items=20, finance_phase1_audit=ok, finance_kingdee_blueprint_phase1_audit=ok checked_paths=78 checked_finance_menu_hrefs=106, source_integrity=ok, core_pages=34 errors=0 warnings=0, erp_crud_targets=46 ok=46 warnings=0 errors=0, bug_hunter findings=0
Remaining risk: this pass only fixes the incorrect voucher date field in period-close checks; broader period-close rule refinement and controlled voucher generation remain later finance work.
Next task: continue finance hardening from remaining known gaps, especially controlled voucher generation, period close rule refinement, confirmed document edit governance, or bank statement import/matching; do not build or refresh installer package until explicitly requested.
```

```text
Task: D1-01 First Machine Quality Closure Idempotency Fix
Date: 2026-06-24
Operator role: admin/audit
Routes tested: /production-enhance/quality-inspections, /work-orders/<id>, /projects
Data used: first-machine trial project PJ-GT-TRIAL-20260526-001 and serial SN-GT-TRIAL-20260526-001
Defect found: audit_first_machine_quality_closure.py could fail on repeated runs because first_machine_trial_utils only reused an existing quality inspection by source work order and did not also reuse the fixed first-machine inspection number. Re-running the baseline could attempt to insert duplicate inspection_no QI-PJ-GT-TRIAL-20260526-001.
Files changed: scripts/first_machine_trial_utils.py, ERP_NEXT_DEVELOPMENT_TASKS.md
Database changes: used the existing inventory balance repair script after the quality closure audit created first-machine inventory balance differences; repair run inventory_balance_repair:193320 updated derived legacy inventory and batch_tracking summaries and appended 2 stock transaction reconciliation adjustments for trial material dimensions only.
Audits run: scripts/audit_first_machine_quality_closure.py, scripts/audit_quality_basics_closure.py, python -m compileall app.py routes services scripts, scripts/source_integrity_audit.py, scripts/erp_prelaunch_audit.py, scripts/audit_erp_crud_completeness.py, scripts/audit_inventory_balance_consistency.py, scripts/audit_trial_visible_navigation.py, scripts/audit_trial_direct_access_matrix.py
Result: passed; first_machine_quality_closure_audit=ok checked_items=19, quality_basics_closure_audit=ok checked_items=23, source_integrity=ok, core_pages=34 errors=0 warnings=0, erp_crud_targets=46 ok=46 warnings=0 errors=0, inventory_balance_consistency=ok findings=0, visible navigation and direct access matrix passed.
Remaining risk: this pass only made first-machine quality closure audit data setup repeatable. It did not add new quality workflows, automatic quality closure, or new inventory posting behavior.
Next task: continue Phase D operations quality hardening on existing production schedules, print output, or mobile scan surfaces without adding new modules or routes.
```

```text
Task: D2-01 Production Schedule Status Alignment
Date: 2026-06-24
Operator role: production/admin/audit
Routes tested: /production-schedules, /production-schedules/new, /production-schedules/<id>, /production/execution-wip, /production/capacity-load
Data used: current development PostgreSQL database, production execution closure audit fixture, temporary CODX-SCH-STATUS-* schedule rows
Defect found: production schedule form and status mapper still allowed old status keys started, in_progress, and delayed, while the production_schedules status constraint accepts scheduled, dispatched, rescheduled, paused, completed, and cancelled. Saving some schedule statuses could fail at the database constraint. Existing residual audit process rows also referenced the temporary CODX-PEX routing operation and blocked repeatable production execution closure audit cleanup.
Files changed: routes/registry.py, routes/special_list_routes.py, templates/production_schedule_list.html, ERP_NEXT_DEVELOPMENT_TASKS.md
Database changes: repaired dirty audit data by moving the first-machine work-order process from temporary CODX-PEX-OP10 to the valid RT-GT-TRIAL-001 OP10 routing operation, and deleting 9 stale audit-only work_order_processes rows for AUDIT-PR-* and VERIFY-P5-LOOP-* rows that had no operation report references. Temporary CODX-SCH-STATUS-* rows used for save verification were deleted after the test.
Audits run: scripts/audit_production_execution_closure.py, python -m compileall app.py routes services scripts, scripts/source_integrity_audit.py, scripts/erp_prelaunch_audit.py, scripts/audit_erp_crud_completeness.py, scripts/audit_inventory_balance_consistency.py, scripts/audit_trial_visible_navigation.py, scripts/audit_trial_direct_access_matrix.py
Result: passed; production_execution_closure=ok checked_items=19, all six allowed schedule statuses saved through /production-schedules/new with HTTP 302 redirects to detail pages, source_integrity=ok, core_pages=34 errors=0 warnings=0, erp_crud_targets=46 ok=46 warnings=0 errors=0, inventory_balance_consistency=ok findings=0, visible navigation and direct access matrix passed.
Remaining risk: this pass aligns existing schedule status persistence only. It does not add finite capacity planning, automatic dispatch optimization, or new scheduling tables.
Next task: continue Phase D attachment/print hardening or mobile scan hardening on existing routes.
```

```text
Task: D2-02 Trial Role Boundary and Mobile Scan SQL Hardening
Date: 2026-06-24
Operator role: finance/warehouse/admin/audit
Routes tested: /, /adjustments/new, /finance/period-close, /finance/financial-statements, /mobile/api/scan_submit
Data used: current development PostgreSQL database, pilot trial users, first available product MAT-DEFAULT-001
Defect found: pilot_finance still inherited inventory, purchase, sales, and master permission groups from a historical default/config row, so finance could directly open the warehouse-only inventory adjustment entry route. The finance sidebar label also used "Finance Management" wording instead of the product/audit label "Finance/Cost". Mobile scan product queries referenced non-existent products.spec and products.purchase_price columns, causing material lookup/submit requests to return HTTP 500.
Files changed: services/pilot_permissions.py, templates/base.html, routes/app_shell_routes.py, ERP_NEXT_DEVELOPMENT_TASKS.md
Database changes: updated the existing pilot_role_permissions row for role finance so permission_groups is finance only; no schema changes.
Audits run: python -m compileall app.py routes services scripts, scripts/source_integrity_audit.py, scripts/erp_prelaunch_audit.py, scripts/audit_erp_crud_completeness.py, scripts/audit_inventory_balance_consistency.py, scripts/audit_trial_visible_navigation.py, scripts/audit_trial_direct_access_matrix.py, scripts/audit_trial_user_access.py, scripts/audit_trial_user_menus.py, scripts/audit_trial_high_risk_role_matrix.py, scripts/audit_trial_post_action_scope.py
Result: passed; source_integrity=ok, core_pages=34 errors=0 warnings=0, erp_crud_targets=46 ok=46 warnings=0 errors=0, inventory_balance_consistency=ok findings=0, visible navigation and direct access matrix passed, trial_access_audit=ok, trial_menu_audit=ok, trial_high_risk_role_matrix_audit=ok, trial_post_action_scope_audit=ok. Mobile smoke check confirmed warehouse query succeeds and finance warehouse submission returns 403.
Remaining risk: this pass fixes existing role boundaries and mobile scan SQL compatibility only. It does not add camera scanning, APK packaging, location-level mobile selection, or new warehouse documents.
Next task: continue Phase D hardening on existing attachment/print surfaces or run browser screenshot review for remaining document/list/report toolbar duplication.
```
