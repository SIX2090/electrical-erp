# ERP Boundary Stabilization

This file is the single place where every non-trivial code change must
record its boundary **before** application code is edited. This is the
discipline that stops the "dozens of new BUGs every day" cycle.

Rule (from `AGENTS.md`):
> Before writing ERP code, define the boundary first. Do not start
> implementation until the affected business loop, page type, route
> exposure, data owner, upstream source document, downstream impact,
> and acceptance check are clear.

## How to use this file

1. Before editing any route, service, template, or schema, copy the
   **Boundary Block** template below into the "Open Boundaries" section.
2. Fill in every field. If a field is genuinely N/A, write `N/A` and a
   one-line reason. Do not leave fields blank.
3. Only after the block is complete, edit application code.
4. After the change passes `scripts/pre_delivery_gate.py`, move the block
   to "Closed Boundaries" with the gate result and date.

## Boundary Block template

```
### B-<seq> <short title>
- Date: YYYY-MM-DD
- Trigger: <bug id / feature request / refactor goal>
- Business loop: <which end-to-end flow this touches, e.g. purchase request -> PO -> receipt -> inventory -> payable>
- Page type: <workbench | document list | document entry | master data | query list | report | finance | system admin>
- Route exposure:
    - new routes: <list, or "none">
    - changed routes: <list>
    - removed routes: <list>
- Data owner: <which table/column owns the truth, e.g. purchase_orders.status>
- Upstream source document: <what feeds this flow, e.g. purchase_request>
- Downstream impact: <what consumes this flow, e.g. inventory_in, ap_line>
- Schema change: <none | list DDL, must be in services/schema_migrations.py first>
- Permission: <which roles need access, must be in services/pilot_permissions.py>
- Menu classification: <live | fix | readonly | internal | hidden> (for new/changed pages)
- Acceptance check: <the exact operator action + data reconciliation that proves it works, NOT just HTTP 200>
- Rollback plan: <how to undo if it breaks in production>
```

## Definition of Done (DoD)

A change is NOT done until ALL of the following are true:

- [ ] Boundary block filled in above (every field, no blanks)
- [ ] `python scripts/pre_delivery_gate.py` exits 0
- [ ] The exact operator workflow from "Acceptance check" was walked
      through manually (or via an audit script) and produced the
      expected data state
- [ ] If a route was added: it is in `routes/route_catalog.py`,
      `services/pilot_permissions.py`, and `MENU_ROLLOUT_CLASSIFICATION.md`
- [ ] If a route was removed: every dependent menu entry, shortcut,
      return link, redirect, and permission expectation has been audited
- [ ] If schema changed: `scripts/pg_backup.py` was run first, DDL is
      in `services/schema_migrations.py`, and `python -m compileall`
      shows no broken references
- [ ] If Chinese UI text was added/changed: `source_integrity_audit.py`
      shows `source_mojibake_findings=0`
- [ ] No new `except Exception: pass` without `logger.warning/exception`
- [ ] No new route/field/page/menu beyond what the user explicitly
      requested in this session (Scope Freeze rule)

## Open Boundaries

### Engineering/BOM/Routing Readiness Boundary
- Source document: sales order / project code / cabinet number
- Target document: engineering technical confirmation, BOM, routing, work center, kitting readiness
- Status transition: draft -> confirmed -> closed (technical confirmation); planned -> released -> closed (BOM ECN)
- Blocked reason: missing BOM, missing routing, missing drawing, missing inspection standard, missing tooling requirement, open BOM ECN impact, missing process program
- Downstream impact: purchase requisition, work order, kitting shortage, production execution
- Acceptance checks: engineering readiness gate blocks confirmation when BOM/routing/drawing/inspection/tooling/ECN is incomplete; kitting shortage surfaces blocked engineering items; no PLM/PDM module is created
- PLM scope guard: this boundary must not become a generic PLM/PDM module; engineering readiness stays inside the existing ERP engineering pages and must not expand into a new PLM module route

### B-017 Inventory movement toolbar state discipline
- Date: 2026-06-29
- Trigger: user reported inbound/outbound document toolbars are confusing; buttons may disappear on detail pages, entry pages show state actions without clear availability, and operators cannot reliably find audit, reverse-audit, or delete actions after save.
- Business loop: manual other inbound / other outbound document entry -> draft detail -> audit/post to inventory -> reverse audit -> draft deletion.
- Page type: document entry and document detail.
- Route exposure:
    - new routes: none
    - changed routes: `/inventory/inbound/new`, `/inventory/outbound/new`, `/inventory/inbound/<doc_no>`, `/inventory/outbound/<doc_no>` rendering and existing action routes
    - removed routes: none
- Data owner: `inventory_movement_documents.status` owns document lifecycle; `inventory_movement_lines` owns draft lines; `stock_transactions`, `inventory_balances`, and `batch_tracking` own posted inventory impact.
- Upstream source document: manual stock evidence, warehouse operator entry, or later explicit source document selected by the operator.
- Downstream impact: inventory balance, batch tracking, stock transaction ledger, inventory detail/list visibility, and operator document navigation.
- Schema change: none.
- Permission: unchanged for normal navigation; existing inventory document permissions remain in force.
- Menu classification: unchanged; existing pages remain `live`.
- Acceptance check: entry pages keep the full standard toolbar without deleting buttons; unavailable actions are disabled with reasons. Detail pages always show audit, reverse-audit, and delete in stable positions; draft enables audit/delete and disables reverse-audit; posted enables reverse-audit and disables delete; invalid actions do not silently fail. Saving an other-outbound draft with zero available stock creates a searchable draft; audit blocks with a stock-shortage message and no stock transaction. Reverse-audit updates balances and batch tracking without consistency findings.
- Rollback plan: revert the toolbar rendering changes in `templates/inventory_movement_detail.html`, `templates/base.html`, and the status context changes in `routes/registry.py`; no schema rollback is required.

### B-016 Inventory-impact document line grid unification
- Date: 2026-06-29
- Trigger: user requested all inbound/outbound document line grids to follow the purchase-order line-grid style instead of each document using a different layout.
- Business loop: purchase receipt, manual inbound/outbound, inventory adjustment, transfer, check, assembly/disassembly, production issue/return, and subcontract issue/receive document entry -> inventory posting.
- Page type: document entry.
- Route exposure:
    - new routes: none
    - changed routes: existing document-entry templates only; no route path or HTTP method changes
    - removed routes: none
- Data owner: existing document header and line tables remain the data owners, including `purchase_receipts`, `purchase_receipt_items`, `inventory_movement_documents`, `inventory_movement_lines`, `inventory_adjustments`, `transfer_orders`, `transfer_order_items`, `inventory_check_orders`, `inventory_check_order_items`, `inventory_assembly_orders`, `inventory_assembly_items`, `pick_lists`, `wo_material_items`, `subcontract_issue_orders`, `subcontract_issue_lines`, `subcontract_receive_orders`, and `subcontract_receive_lines`.
- Upstream source document: purchase order, work order, subcontract order, inventory opening sheet, manual stock evidence, transfer/check evidence, or assembly/disassembly instruction according to the existing document type.
- Downstream impact: inventory balances, stock transactions, batch tracking, work-order material quantities, subcontract WIP, project/cabinet trace, and finance cost reports.
- Schema change: none.
- Permission: unchanged; existing warehouse, purchase, production, and subcontract route permissions remain in force.
- Menu classification: unchanged; existing document-entry pages remain `live`.
- Acceptance check: operators opening the existing inbound/outbound-impact document-entry pages see a consistent purchase-order-style dense line grid appearance, including bordered compact tables, light headers, hover rows, horizontal scroll, and existing line toolbar behavior where already present; existing fields, column order, form names, IDs, and save/post behavior remain unchanged; compile, source integrity, prelaunch, CRUD, material-name-entry, inventory consistency, navigation, and direct-access audits pass.
- Rollback plan: revert the template-only changes for the affected document-entry pages; no database rollback is required.

### B-015 Period close guardrails - CLOSED 2026-06-29
- Date: 2026-06-29
- Trigger: user requested continuing to improve the ERP closing function.
- Business loop: system opening period -> finance current period -> period close check -> close execution -> next period.
- Page type: finance.
- Route exposure:
    - new routes: none
    - changed routes:
        - finance period close check and execute routes through `services.period_closing_service`
    - removed routes: none
- Data owner: `system_options.finance_start_period`, `system_options.finance_current_period`, `period_closing.status`, and `accounting_periods.status`.
- Upstream source document: N/A; the source is configured finance period and posted vouchers.
- Downstream impact: finance reports, period close history, voucher lock, and current-period advancement.
- Schema change: none.
- Permission: unchanged; existing finance period-close permissions remain in force.
- Menu classification: unchanged; no new route.
- Acceptance check: closing check blocks invalid periods, periods before finance start, and periods other than the configured current period; the finance start period is accepted as the first close without requiring a prior period; execute close reruns the same check and cannot bypass it.
- Rollback plan: remove the new guardrail checks from `check_period_closing()` and rely on the previous voucher-only checks.
- Delivery verification:
    - `check_period_closing("bad")` blocks invalid period format.
    - `check_period_closing("2025-12")` blocks periods before configured `finance_start_period=2026-01`.
    - `check_period_closing("2026-05")` blocks non-current period when `finance_current_period=2026-06`.
    - `check_period_closing("2026-06")` continues into voucher and previous-period close checks and reports configured start/current period in summary.
    - `execute_period_closing("2026-05")` returns failure from the close-condition check and cannot bypass the guardrail.
    - `python -m compileall app.py routes services scripts`: passed.
    - `python scripts/source_integrity_audit.py`: `source_integrity=ok`, `source_mojibake_findings=0`.
    - `python scripts/erp_prelaunch_audit.py`: `core_pages=34 errors=0 warnings=0`.
    - `python scripts/audit_erp_crud_completeness.py`: `erp_crud_targets=46 ok=46 warnings=0 errors=0`.

### B-014 Opening period control completion - CLOSED 2026-06-29
- Date: 2026-06-29
- Trigger: user requested completing the enabled period setting feature.
- Business loop: opening setup -> opening balance entry -> period close -> next current period.
- Page type: system admin setting consumption plus opening document entry and finance period close.
- Route exposure:
    - new routes: none
    - changed routes:
        - `/inventory/opening/new`
        - `/subcontract/opening/new`
        - `/finance/opening/receivables/new`
        - `/finance/opening/payables/new`
        - period-close execution routes that call `execute_period_closing()`
    - removed routes: none
- Data owner: `system_options.opening_data_locked`, `system_options.opening_lock_date`, and `system_options.finance_current_period`.
- Upstream source document: N/A; source is the system-admin opening period setup.
- Downstream impact: material opening, subcontract opening, AR opening, AP opening, period close, and finance report default period.
- Schema change: none.
- Permission: unchanged; existing route permissions remain in force.
- Menu classification: unchanged; no new route.
- Acceptance check: when `opening_data_locked=1`, the four opening-entry routes cannot create new opening records; after closing the configured period, `finance_current_period` is advanced to the next month; audits remain clean.
- Rollback plan: remove the opening lock checks and remove the `finance_current_period` update in `execute_period_closing()`.
- Delivery verification:
    - Flask smoke with `opening_data_locked=1`: `/inventory/opening/new`, `/subcontract/opening/new`, `/finance/opening/receivables/new`, and `/finance/opening/payables/new` all redirect back to their opening lists.
    - Service-level period-close simulation: closing `2026-06` returns `next_period=2026-07` and writes `finance_current_period=2026-07`.
    - `python -m compileall app.py routes services scripts`: passed.
    - `python scripts/source_integrity_audit.py`: `source_integrity=ok`, `source_mojibake_findings=0`.
    - `python scripts/erp_prelaunch_audit.py`: `core_pages=34 errors=0 warnings=0`.
    - `python scripts/audit_erp_crud_completeness.py`: `erp_crud_targets=46 ok=46 warnings=0 errors=0`.
    - `python scripts/audit_trial_visible_navigation.py`: `trial_visible_navigation_audit=ok`, `checked_users=7`.
    - `python scripts/audit_trial_direct_access_matrix.py`: `trial_direct_access_matrix_audit=ok`, `checked_users=7`, `checked_paths=451`.
    - `python scripts/audit_inventory_balance_consistency.py`: `inventory_balance_consistency=ok`, `findings=0`.

### B-013 Finance current period source - CLOSED 2026-06-29
- Date: 2026-06-29
- Trigger: continue the opening period feature so finance period-close and finance reports use the configured enabled/current period instead of the server calendar month.
- Business loop: finance period close and finance reporting default period selection.
- Page type: finance plus system admin setting consumption.
- Route exposure:
    - new routes: none
    - changed routes:
        - routes that call `services.period_closing_service.get_current_period()`
    - removed routes: none
- Data owner: `system_options.finance_current_period` owns the configured current finance period.
- Upstream source document: N/A; the source is the system-admin opening period setting.
- Downstream impact: finance period close page, period-close check/execute API default period, and financial report default period.
- Schema change: none.
- Permission: unchanged; system-admin setting remains restricted, finance routes keep their existing permissions.
- Menu classification: unchanged; no new route.
- Acceptance check: after saving `finance_current_period`, `get_current_period()` returns the configured value; if the value is absent or invalid it falls back to the server month; compile and audits remain clean.
- Rollback plan: restore `get_current_period()` to `datetime.now().strftime('%Y-%m')`.
- Delivery verification:
    - `get_current_period()` returned configured `finance_current_period=2026-06`.
    - `python -m compileall app.py routes services scripts`: passed.
    - `python scripts/source_integrity_audit.py`: `source_integrity=ok`, `source_mojibake_findings=0`.
    - `python scripts/erp_prelaunch_audit.py`: `core_pages=34 errors=0 warnings=0`.
    - `python scripts/audit_erp_crud_completeness.py`: `erp_crud_targets=46 ok=46 warnings=0 errors=0`.

### B-012 System opening period settings - CLOSED 2026-06-29
- Date: 2026-06-29
- Trigger: user requested System Management opening time / enabled period setup.
- Business loop: system go-live baseline for opening balances, finance period control, and future document period checks.
- Page type: system admin.
- Route exposure:
    - new routes:
        - GET /system/opening-period
        - POST /system/opening-period/save
    - changed routes:
        - navigation menu and topbar system tools
        - pilot permission registry
        - route catalog
    - removed routes: none
- Data owner: `system_options.option_key` and `system_options.option_value` own the configured opening period values.
- Upstream source document: N/A; this is a system initialization setting, not a business document.
- Downstream impact: material opening, subcontract opening, AR/AP opening, period close, and future document period validation will read this baseline.
- Schema change: none; reuse existing `system_options`.
- Permission: admin and manager through the existing system-admin route guard and `services/pilot_permissions.py`.
- Menu classification: live system-admin page and live system-admin action.
- Acceptance check: admin can open the page, save system start period, finance start/current period, opening dates, and lock/control flags; the values persist in `system_options`; system menu/topbar expose the page to admin/manager; route catalog and direct-access audits recognize it.
- Rollback plan: remove the two routes, template, menu links, permission feature/path, route catalog entries, and menu classification rows; existing `system_options` rows can remain harmless or be cleared manually by key.
- Delivery verification:
    - `python -m compileall app.py routes services scripts`: passed.
    - `python scripts/source_integrity_audit.py`: `source_integrity=ok`, `source_mojibake_findings=0`.
    - `python scripts/erp_prelaunch_audit.py`: `core_pages=34 errors=0 warnings=0`.
    - `python scripts/audit_erp_crud_completeness.py`: `erp_crud_targets=46 ok=46 warnings=0 errors=0`.
    - `python scripts/audit_trial_visible_navigation.py`: `trial_visible_navigation_audit=ok`, `checked_users=7`.
    - `python scripts/audit_trial_direct_access_matrix.py`: `trial_direct_access_matrix_audit=ok`, `checked_users=7`, `checked_paths=451`.
    - Flask smoke: `pilot_admin` GET `/system/opening-period` returned 200; POST `/system/opening-period/save` redirected to `/system/opening-period`; 8 opening-period keys persisted in `system_options`.

### B-011 Pilot role master-data read baseline - CLOSED 2026-06-29
- Date: 2026-06-29
- Trigger: final direct-access audit found business pilot roles losing read access to master-data paths after the role-permission page save/restore flow.
- Business loop: trial go-live permission readiness for sales, purchase, warehouse, production, and service operators.
- Page type: system admin permission page plus master-data list/query pages.
- Route exposure:
    - new routes: none
    - changed routes:
        - POST /permissions/roles
        - direct GET access evaluation for master-data paths already registered in `services/pilot_permissions.py`
    - removed routes: none
- Data owner: system administrator owns role permission configuration; master data remains owned by each master-data owner.
- Upstream source document: role permission form submission and default pilot role permission definitions.
- Downstream impact: visible navigation and direct access matrix must agree; document-entry operators need read-only access to material, customer, supplier, warehouse, unit, project, and machine cabinet master data.
- Schema change: none.
- Permission: preserve existing role groups and ensure the default read-only `master` group cannot be accidentally removed from business pilot roles by a partial form save.
- Menu classification: existing routes remain `live`; no navigation expansion.
- Acceptance check:
    1. `audit_trial_role_permissions_page.py` can customize and restore role groups.
    2. `audit_trial_direct_access_matrix.py` passes after that flow.
    3. Business pilot roles retain read-only master-data access without gaining admin/system access.
- Verification:
    - `routes/registry.py` now preserves the default read-only `master` group for non-admin business pilot roles during `/permissions/roles` saves.
    - Current `pilot_role_permissions` rows for sales, purchase, warehouse, production, and service include `master`.
    - `audit_trial_role_permissions_page.py`: passed.
    - `audit_trial_direct_access_matrix.py`: passed with `checked_users=7`, `checked_paths=450`.
- Rollback plan: revert the permission-save merge change and restore the previous `pilot_role_permissions` rows from backup if required.

### B-010 Inventory opening and other movement readiness - CLOSED 2026-06-29
- Date: 2026-06-29
- Trigger: user approved proceeding with ERP stabilization; readiness audits found inventory entry visibility gaps.
- Business loop: material opening -> inventory balance; other inbound/outbound document entry -> document list -> detail audit -> inventory posting.
- Page type: document list and document entry.
- Route exposure:
    - new routes: none
    - changed routes:
        - GET /inventory/inbound
        - GET /inventory/outbound
        - GET /inventory/opening/new
    - removed routes: none
- Data owner: `inventory_movement_documents` and `inventory_movement_lines` own other inbound/outbound draft document headers and lines; `stock_transactions` owns posted inventory movement history.
- Upstream source document: manual stock adjustment evidence, physical count sheet, old system opening sheet, supplier/customer return source document where applicable.
- Downstream impact: inventory balance, stock transaction trace, project/cabinet inventory occupation, and inventory cost reports.
- Schema change: none.
- Permission: existing warehouse permissions; no permission expansion.
- Menu classification: existing routes remain `live`.
- Acceptance check:
    1. `/inventory/inbound` and `/inventory/outbound` show document information plus source document, material detail count, inventory cost unit price, lot number, project number, and cabinet number context.
    2. `/inventory/inbound/new` and `/inventory/outbound/new` remain the only normal document-entry routes for manual other movement creation.
    3. `/inventory/opening/new` remains a material-opening form with opening-only labels and a visible save action.
    4. `audit_material_opening_boundary.py` and `audit_trial_core_document_fields.py` pass.
- Verification:
    - Created stabilization plan: `ERP_SCOPE_PLAN.md`.
    - `audit_material_opening_boundary.py`: passed.
    - `audit_trial_core_document_fields.py`: passed.
    - Compileall, source integrity, prelaunch, and CRUD completeness passed.
    - Inventory consistency was repaired after backup `backups\pre_inventory_balance_repair_20260629.dump`; final `audit_inventory_balance_consistency.py` passed with `findings=0`.
    - Trial visible navigation and direct access matrix passed.
- Rollback plan: revert template/list-column changes; no data migration or data deletion involved.

### B-009 Standardize supplier payable document number - CLOSED 2026-06-29
- Date: 2026-06-29
- Trigger: user approved standardizing the payable side after receivable numbers were completed.
- Business loop: purchase receipt/purchase invoice/subcontract receive/opening payable -> supplier payable -> supplier payment settlement.
- Page type: finance document list, finance document detail, system numbering.
- Route exposure:
    - new routes: none
    - changed routes:
        - GET /payables
        - GET /payables/<id>
        - GET /system/doc-rules
    - removed routes: none
- Data owner: `supplier_payables.payable_no` owns the formal payable document number. Existing `doc_no` and `source_no` remain upstream/source compatibility fields.
- Upstream source document: purchase receipt, purchase invoice, subcontract receive, opening payable, and other existing posting sources.
- Downstream impact: supplier payment source selection, payable settlement display, AP reports, project/cabinet cost trace, and system document-number settings.
- Schema change: add nullable `supplier_payables.payable_no`, backfill existing rows as `AP-LEGACY-<id>`, create a unique partial index, and seed a default inactive document-number rule.
- Permission: existing finance/payable/system-admin permissions; no permission expansion.
- Menu classification: existing routes remain `live`.
- Acceptance check:
    1. Existing supplier payables have nonblank `payable_no` after migration.
    2. New supplier payables created by existing posting services receive `payable_no`.
    3. Payable list and detail show `应付单号` while preserving source document references.
    4. Payment settlement source selection can search/display the formal payable number without losing source-number compatibility.
- Verification:
    - Backup completed: `backups\pre_migration_payable_document_number.dump`.
    - Migration applied: `20260629_004_supplier_payable_document_number`.
    - Blank document-number count: `supplier_payables.payable_no=0`.
    - Runtime smoke confirmed `/payables`, `/payables/<id>`, and `/system/doc-rules` render the AP payable number.
    - Audits passed: compileall, source integrity, prelaunch, CRUD completeness, trial visible navigation, and trial direct access matrix.
- Rollback plan: revert route/template/service/query changes and leave the nullable column unused; no data deletion required.

### B-008 Backfill remaining document header numbers - CLOSED 2026-06-29
- Date: 2026-06-29
- Trigger: user requested completing document numbers for the remaining documents that need formal header numbers.
- Business loop: shipped machine/service card -> service order -> return visit/RMA; sales order/invoice/shipment -> receivable -> receipt settlement.
- Page type: document list, document detail, system numbering.
- Route exposure:
    - new routes: none
    - changed routes:
        - GET /service-cards
        - GET /service-cards/<id>
        - POST /service-orders/<id>/return-visit
        - GET /receivables
        - GET /receivables/<id>
    - removed routes: none
- Data owner:
    - `machine_service_cards.card_no` owns the service card document/archive number.
    - `machine_service_return_visits.visit_no` owns the return-visit document number.
    - `customer_receivables.receivable_no` owns the receivable document number; `source_no` remains the upstream document reference.
- Upstream source document: sales shipment/sales order/service order/sales invoice depending on the business event.
- Downstream impact: service trace, service closure check, receivable settlement, customer receipt allocation, project/cabinet trace.
- Schema change: add nullable number columns and unique partial indexes in `services/schema_migrations.py`; backfill existing rows as `SC-LEGACY-<id>`, `SV-LEGACY-<id>`, and `AR-LEGACY-<id>`.
- Permission: existing service and finance permissions; no permission expansion.
- Menu classification: existing routes remain `live`.
- Acceptance check:
    1. Existing service cards, return visits, and receivables have nonblank document numbers after migration.
    2. New service cards, return visits, and receivables generated through existing flows receive document numbers.
    3. Lists and details show the formal document number while preserving upstream source numbers.
    4. Runtime smoke renders service card and receivable pages with the new labels.
- Verification:
    - Backup completed: `backups\pre_migration_remaining_document_numbers.dump`.
    - Migration applied: `20260629_003_remaining_document_header_numbers`.
    - Blank document-number counts: `machine_service_cards.card_no=0`, `machine_service_return_visits.visit_no=0`, `customer_receivables.receivable_no=0`.
    - Runtime smoke confirmed service card, return visit, receivable, and system document-rule pages render the new numbers.
    - Audits passed: compileall, source integrity, prelaunch, CRUD completeness, trial visible navigation, and trial direct access matrix.
- Rollback plan: revert route/template/query changes and leave the nullable columns unused; no data deletion required.

### B-007 Add document number rule settings - CLOSED 2026-06-29
- Date: 2026-06-29
- Trigger: user requested a system management function to customize document numbering rules.
- Business loop: system admin configuration -> document number generation -> new document entry save -> document list/detail trace by generated number.
- Page type: system admin.
- Route exposure:
    - new routes:
        - GET /system/doc-rules
        - POST /system/doc-rules/save
    - changed routes:
        - GET /system_settings/form
        - POST /system_settings/form/save
    - removed routes: none
- Data owner: `erp_code_rules` owns rule definitions; `document_sequences` owns issued sequence counters.
- Upstream source document: none; this is a system configuration page.
- Downstream impact: new document numbers generated through `next_doc_no` can use active document rules; historical numbers are not rewritten.
- Schema change: ensure `erp_code_rules` table and default document rules through `services/schema_migrations.py`.
- Permission: system administrator and manager system-maintenance roles only.
- Menu classification: `/system/doc-rules` and `/system/doc-rules/save` are `live` system-admin routes.
- Acceptance check:
    1. System management shows a dedicated document number settings entry.
    2. Admin can edit prefix, date format, sequence length, separator, reset scope, active flag, manual flag, and remark for known document types.
    3. Active document rules are used by `get_next_doc_no`; inactive rules keep the legacy prefix + four-digit sequence behavior.
    4. Runtime smoke renders the settings page and saves a harmless rule update without corrupt Chinese UI text.
- Verification:
    - Pre-migration backup: `backups/pre_migration_document_number_rules.dump`.
    - Schema migration applied: `20260629_002_document_number_rules`.
    - Runtime smoke: `/system/doc-rules` returns 200, renders `单据编号设置`, and `/system/doc-rules/save` redirects back to the settings page after saving one rule.
    - Numbering service smoke: an active purchase-order rule generated `TPO001`; after disabling the rule, purchase-order numbering fell back to the legacy `PO` prefix.
    - Compile, source integrity, prelaunch, CRUD completeness, visible navigation, and direct access matrix audits passed.
- Rollback plan: hide the navigation entry and leave `erp_code_rules` unused; keep existing legacy numbering fallback.

### B-006 Add service acceptance document number - CLOSED 2026-06-29
- Date: 2026-06-29
- Trigger: user approved fixing document headers that lack document numbers, starting with installation acceptance.
- Business loop: service card by shipped machine cabinet -> installation acceptance -> warranty start/customer acceptance evidence -> service order/RMA follow-up -> project/cabinet trace.
- Page type: document entry, document list, document detail.
- Route exposure:
    - new routes: none
    - changed routes:
        - GET /service-acceptance
        - GET/POST /service-acceptance/new
        - GET /service-acceptance/<id>
        - GET/POST /service-acceptance/<id>/edit
    - removed routes: none
- Data owner: `machine_service_acceptance_checks.acceptance_no` owns the formal installation acceptance document number.
- Upstream source document: machine service card created from shipped machine cabinet / sales shipment.
- Downstream impact: warranty start evidence, customer acceptance follow-up, service order/RMA trace, project/cabinet ledger.
- Schema change: add `machine_service_acceptance_checks.acceptance_no` and a unique index in `services/schema_migrations.py`; backfill existing rows from id as `SA-LEGACY-<id>`.
- Permission: existing service acceptance permissions in `services/pilot_permissions.py`; no permission change.
- Menu classification: existing `/service-acceptance` and `/service-acceptance/new` remain `live`.
- Acceptance check:
    1. Creating an installation acceptance generates an `SA` document number and stores it in `machine_service_acceptance_checks.acceptance_no`.
    2. The service acceptance list can search by acceptance number and shows the number as the first document column.
    3. The detail and edit pages display the acceptance number instead of using database id as the operator-facing document number.
    4. Project/cabinet trace uses the acceptance number for service acceptance events.
- Verification:
    - Pre-migration backup: `backups/pre_migration_service_acceptance_no.dump`.
    - Schema migration applied: `20260629_001_service_acceptance_document_number`.
    - Existing rows backfilled as `SA-LEGACY-<id>` with zero blank `acceptance_no` values.
    - Runtime smoke: `/service-acceptance`, `/service-acceptance/new`, and `/service-acceptance/<id>` return 200 and render `验收单号`.
    - Compile, source integrity, prelaunch, CRUD completeness, visible navigation, and direct access matrix audits passed.
- Rollback plan: revert the route/template/catalog changes and leave the nullable `acceptance_no` column unused; no data deletion required.

### B-004 Improve kitting estimated readiness dates - CLOSED 2026-06-27
- Date: 2026-06-27
- Trigger: continuation of material kitting completion
- Business loop: BOM/MRP -> kitting readiness -> supply commitment date -> purchase/subcontract/production follow-up -> work order picking readiness
- Page type: query list
- Route exposure:
    - new routes: none
    - changed routes:
        - GET /mrp/kitting
        - GET /requisition
    - removed routes: none
- Data owner: read-only dates from `purchase_requisition_items.need_date`, `purchase_order_items.expected_date`, `purchase_orders.expected_date`, `subcontract_orders.required_date`, and `work_orders.planned_end_date`
- Upstream source document: production work order, purchase requisition, purchase order, subcontract order, and lower-level production work order
- Downstream impact: kitting gate date, shortage owner follow-up, work order issue readiness, project delivery readiness
- Schema change: none
- Permission: existing permissions; no permission change
- Menu classification: existing pages remain unchanged
- Acceptance check:
    1. `/mrp/kitting?work_order_id=<existing work order>` returns 200 and renders estimated readiness dates without dirty text.
    2. `/requisition` and `/requisition?status=cannot_start` return 200 and keep estimated readiness date visible.
    3. MRP validation, production module closure, source integrity, and pre-delivery gate pass.
- Rollback plan: revert changes in `services/mrp_engine.py` and `routes/work_order_requisition_routes.py`; no data rollback needed because this is read-only.

### B-003 Extend kitting readiness into requisition query - CLOSED 2026-06-27
- Date: 2026-06-27
- Trigger: continuation of material kitting completion
- Business loop: BOM/MRP -> kitting readiness -> work order material query -> picking readiness and shortage follow-up
- Page type: query list
- Route exposure:
    - new routes: none
    - changed routes:
        - GET /requisition
    - removed routes: none
- Data owner: read-only calculation from `work_orders`, `wo_material_items`, `inventory_balances`, and `mrp_requirements`; no new source-of-truth table
- Upstream source document: production work order material requirements
- Downstream impact: production issue document readiness, inventory transfer planning, purchase shortage handling, MRP follow-up
- Schema change: none
- Permission: existing production permission for `/requisition`; no permission change
- Menu classification: existing `/requisition` remains `live` query list
- Acceptance check:
    1. `/requisition` returns 200 and shows kitting gate, owner, next action, downstream impact, action link, and estimated readiness date.
    2. `/requisition?status=cannot_start` still filters blocked work orders.
    3. Production module closure audit, navigation audits, source integrity, and pre-delivery gate still pass.
- Rollback plan: revert changes in `routes/work_order_requisition_routes.py` and `templates/work_order_requisition.html`; no data rollback needed because this is read-only.

### B-005 Enforce kitting gate before production issue posting - CLOSED 2026-06-27
- Date: 2026-06-27
- Trigger: user request to raise material kitting capability to 9/10
- Business loop: work order BOM -> kitting analysis -> production issue document -> inventory posting -> work order material and cost update
- Page type: document entry and document detail action
- Route exposure:
    - new routes: none
    - changed routes:
        - POST /production-issues/<id>/post
        - POST /production-issues/<id>/submit_post
        - POST /production-issues/new when save_action=post
    - removed routes: none
- Data owner: production planning owns kitting decision; warehouse owns production issue posting; existing `trace_snapshots` stores the kitting gate evidence for the post attempt.
- Upstream source document: production work order and its BOM-derived material requirement.
- Downstream impact: blocks inventory issue, work order issued quantity, production material cost, assembly start, and project delivery when kitting has unresolved shortages.
- Schema change: none; reuse `trace_snapshots`.
- Permission: existing production issue permissions; no permission change.
- Menu classification: existing production issue pages remain live; no classification change.
- Acceptance check:
    1. Draft production issue creation remains allowed from an open work order.
    2. Posting a production issue recalculates `/mrp/kitting` readiness for the source work order.
    3. If the kitting gate is not `can_start`, posting is blocked before inventory movement or work order material quantity update.
    4. The blocked or passed post attempt writes a `production_issue_kitting_gate` snapshot to `trace_snapshots`.
    5. Production return posting is not affected by the kitting gate.
- Rollback plan: revert B-005 changes in `routes/production_pick_routes.py`; no data rollback required because snapshots are append-only evidence.
- Gate result:
    - `python -m compileall app.py routes services scripts` passed.
    - `scripts/source_integrity_audit.py` passed with `source_integrity=ok`, `source_mojibake_findings=0`.
    - `scripts/erp_prelaunch_audit.py` passed with `core_pages=34 errors=0 warnings=0`.
    - `scripts/audit_erp_crud_completeness.py` passed with `erp_crud_targets=46 ok=46 warnings=0 errors=0`.
    - `scripts/audit_inventory_balance_consistency.py` passed with `findings=0`.
    - `scripts/audit_trial_visible_navigation.py` passed with `trial_visible_navigation_audit=ok`, `checked_users=7`.
    - `scripts/audit_trial_direct_access_matrix.py` passed with `trial_direct_access_matrix_audit=ok`, `checked_users=7`, `checked_paths=449`.
- Targeted acceptance:
    1. A shortage production issue post attempt was blocked by the kitting gate before inventory posting.
    2. Blocked post left `stock_transactions=0` and work order issued quantity `0`.
    3. `trace_snapshots` recorded `snapshot_event='production_issue_kitting_gate'` with `gate_status='cannot_start'`.
    4. For work orders without an expandable BOM but with maintained work-order material lines, the gate falls back to those material lines instead of blocking solely on missing BOM.

### B-002 Complete material kitting readiness - CLOSED 2026-06-27
- Date: 2026-06-27
- Trigger: user request to complete the material kitting feature
- Business loop: BOM/MRP -> kitting readiness -> shortage action -> purchase request / work order / subcontract / transfer -> work order picking readiness
- Page type: query list
- Route exposure:
    - new routes: none
    - changed routes:
        - GET /mrp/kitting
    - removed routes: none
- Data owner: read-only calculation from `work_orders`, `boms`, `bom_items`, `inventory_balances`, `purchase_requisition_items`, `purchase_order_items`, `subcontract_orders`, and related production work orders; no new source-of-truth table
- Upstream source document: production work order and its BOM snapshot/default BOM
- Downstream impact: purchase requisition conversion, production/subcontract suggestions, inventory transfer planning, work order issue readiness, project delivery readiness
- Schema change: none
- Permission: existing production/planning permission for `/mrp/kitting`; no permission change
- Menu classification: existing `/mrp/kitting` remains `readonly`
- Acceptance check:
    1. Login as production/planning user and open `/mrp/kitting?work_order_id=<existing work order>`.
    2. Page shows gate status, kitting rate, shortage line count, earliest readiness date or blocker.
    3. Each shortage line shows owner role, blocked reason, next action, downstream impact, and a route to the correct existing follow-up page.
    4. Existing MRP run, suggestions list, work order requisition page, navigation audit, and source integrity still pass.
- Rollback plan: revert changes in `services/mrp_engine.py` and `templates/mrp/kitting.html`; no data rollback needed because this is read-only.
- Gate result: `scripts/pre_delivery_gate.py` 7/7 PASS on 2026-06-27.
- Targeted acceptance:
    1. `/mrp/kitting?work_order_id=174` returned 200 and rendered gate status, earliest readiness date, owner role, next action, and kitting detail text.
    2. `scripts/validate_mrp_engine.py` passed and rendered `/mrp/kitting?work_order_id=5`.
    3. `scripts/audit_production_module_closure.py` passed.
- Files changed: `services/mrp_engine.py`, `templates/mrp/kitting.html`, `ERP_BOUNDARY_STABILIZATION.md`.

### B-001 (historical reference - CLOSED 2026-06-27, see Closed Boundaries)
- Date: 2026-06-27
- Trigger: `pre_delivery_gate.py` direct_access gate caught 8 failures (4 paths x 2 roles)
- Business loop: finance report query loop (project cost summary / gross profit analysis / account detail ledger / trial balance) - read-only reporting, no write actions
- Page type: report (finance)
- Route exposure:
    - new routes: none (these routes already have definitions and permissions, just not wired into Flask)
    - changed routes:
        - GET /finance/reports/account-detail-ledger  (currently 404, should 200)
        - GET /finance/reports/trial-balance          (currently 404, should 200)
        - GET /finance/project-cost/summary           (currently 404, should 200)
        - GET /finance/project-cost/gross-profit      (currently 404, should 200)
    - removed routes: none
- Data owner: read-only queries against `chart_of_accounts`, `project_cost_ledger` tables; no writes
- Upstream source document: posted vouchers (for trial balance / account detail), project_cost_ledger entries (for project cost reports)
- Downstream impact: none (pure display reports; no downstream document consumes their output)
- Schema change: none
- Permission: already registered in `services/pilot_permissions.py` for `pilot_admin` and `pilot_finance` (done in prior BUG-H fix); no permission change needed
- Menu classification: `live` (these are standard finance report pages already linked from finance report home)
- Acceptance check:
    1. `python scripts/pre_delivery_gate.py` exits 0 (direct_access gate passes)
    2. Login as `pilot_finance`, GET each of the 4 paths returns 200 (not 404)
    3. Each page renders its template without Jinja TemplateNotFound / UndefinedError
    4. `/finance/reports/account-balance` and `/finance/project-cost/detail` still return 200 (the 2 already-working routes must NOT regress)
- Rollback plan: re-comment the 2 registration lines in `app.py` (lines ~71 and ~73); the 4 routes go back to 404 but the system returns to prior state

#### Conflict analysis (why they were disabled)

`app.py` line 69 comment says "FIXED 20260617: Comment out duplicate route registrations to avoid conflicts". Investigation shows the conflict is on exactly 2 paths, NOT all routes in the 2 modules:

| Path | general_ledger_routes.py | project_cost_reports_routes.py | finance_routes.py | project_cost_routes.py | Active server |
|------|--------------------------|--------------------------------|-------------------|------------------------|---------------|
| /finance/reports/account-balance | line 26 (disabled) | - | line 7572 (active) | - | finance_routes |
| /finance/reports/account-detail-ledger | line 62 (disabled) | - | - | - | NONE -> 404 |
| /finance/reports/trial-balance | line 109 (disabled) | - | - | - | NONE -> 404 |
| /finance/project-cost/detail | - | line 54 (disabled) | - | line 535 (active) | project_cost_routes |
| /finance/project-cost/summary | - | line 112 (disabled) | - | - | NONE -> 404 |
| /finance/project-cost/gross-profit | - | line 167 (disabled) | - | - | NONE -> 404 |

So:
- 2 paths have duplicates across active + disabled modules (account-balance, project-cost/detail) - these WORK today via the active module
- 4 paths exist ONLY in the disabled modules - these 404 today (the bug)

Flask behavior: two routes with same path but different endpoint names do NOT raise AssertionError; the LATER-registered one wins routing. If we re-enable the disabled modules as-is, the disabled modules register AFTER the active ones (app.py line 71/73 come after line 61/62), so the disabled modules would OVERRIDE the active ones for the 2 duplicate paths. That changes behavior for those 2 paths - undesirable regression risk.

#### Trade-off options

**Option A (RECOMMENDED): Selective re-enable with duplicate routes commented out inside disabled modules.**
- Action: uncomment app.py lines 71 and 73; inside general_ledger_routes.py comment out the `account_balance_report` route (lines 26-60); inside project_cost_reports_routes.py comment out the `project_cost_detail_report` route (lines 54-110).
- Effect: 4 missing routes restored; 2 duplicate paths keep using their active module (no behavior change).
- Risk: low. 2 commented routes inside disabled modules are dead code anyway; if someone re-enables them later they'll see the comment.
- Scope Freeze compliance: only restores what was already permitted by permissions; no new route/field/page beyond the fix.

**Option B: Re-enable both modules fully, accept override of 2 duplicate paths.**
- Action: uncomment app.py lines 71 and 73 only.
- Effect: 4 missing routes restored; /finance/reports/account-balance and /finance/project-cost/detail now served by the disabled modules instead of active ones.
- Risk: medium. The two modules may render different templates or use different query logic; behavior change for 2 working routes. Need to verify both active-module versions and disabled-module versions produce equivalent output.
- Scope Freeze compliance: questionable - changes behavior of 2 routes not mentioned in the bug.

**Option C: Move the 4 missing routes into the active modules.**
- Action: copy the 4 route handlers from disabled modules into finance_routes.py (for the 2 ledger routes) and project_cost_routes.py (for the 2 cost report routes); leave disabled modules commented.
- Effect: 4 missing routes restored; no override risk.
- Risk: medium-high. Code duplication; the disabled modules become permanently dead; future maintenance confusion. More invasive than Option A.
- Scope Freeze compliance: adds code to active modules; larger diff.

**Decision: Option A.** Minimum change, no regression risk on working routes, no code duplication.

#### Implementation (2026-06-27)

Applied Option A. Three edits:
1. `app.py` lines 71, 73: uncommented the two imports.
2. `app.py` lines 976-998: uncommented the two registration calls, added B-001 comments explaining the duplicate-route suppression.
3. `routes/general_ledger_routes.py` lines 26-60: commented out the `account_balance_report` route handler (duplicate of finance_routes.py:7572). Kept `account_detail_ledger_report` and `trial_balance_report` active.
4. `routes/project_cost_reports_routes.py` lines 54-110: commented out the `project_cost_detail_report` route handler (duplicate of project_cost_routes.py:535). Kept `project_cost_summary_report`, `project_gross_profit_report`, and the 3 AJAX routes active.

#### Acceptance result (2026-06-27)

- `python scripts/pre_delivery_gate.py` -> 7/7 gates PASS, exit 0
- Login as pilot_finance, GET each of the 4 restored paths -> 200 (no 404, no 500, no TemplateNotFound)
- GET the 2 already-working paths (/finance/reports/account-balance, /finance/project-cost/detail) -> 200 (no regression)
- Flask app started without route-conflict AssertionError

**Status: CLOSED.**

## Closed Boundaries

### B-001 Restore 4 disabled finance routes returning 404 - CLOSED 2026-06-27
- Gate result: 7/7 PASS
- See full boundary block above under "Open Boundaries" history (kept there for reference).
- Files changed: app.py, routes/general_ledger_routes.py, routes/project_cost_reports_routes.py
