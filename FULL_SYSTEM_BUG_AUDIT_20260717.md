# Full System Bug Audit — 2026-07-17

## Audit Boundary

This is a read-only defect audit of the ERP source tree. No application code, audit script, schema, business data, permission, navigation, or runtime configuration was changed.

The audit covers Python parse/name errors, route and template integrity, request-time DDL, inventory and finance write ownership, page-side injection risks, product/runtime configuration, and the availability of the mandated verification environment.

Dynamic business-loop verification could not be executed because this workspace contains no `.venv`, bundled Python runtime, usable system Python, PostgreSQL service, or live database. Findings below are therefore divided into confirmed source defects and unexecuted runtime risks. This report does not claim that every data-dependent bug has been discovered.

## Executive Summary

| Severity | Confirmed findings | Release effect |
|---|---:|---|
| Critical | 2 systemic | Schema and posting architecture is not production-safe |
| High | 8 | Runtime crashes, stored/DOM injection, broken material import precheck |
| Medium | 2 | Installer failure masking and inconsistent DB defaults |
| Verification blocker | 1 | Mandatory audits and business-loop acceptance cannot run |

The current source should not be declared release-ready. The first repair batch should remove deterministic runtime failures and DOM injection, followed by moving request-time DDL into `services/schema_migrations.py` and routing stock/finance mutations through designated posting services.

## Repair Status — 2026-07-17

The user authorized a repair pass after this audit. The following source fixes are complete:

- BUG-001: fixed by consuming the validated CSV reader before the precheck/import branch.
- BUG-002: fixed by using the role checker already injected into the registry dependency set.
- BUG-003: fixed by using Flask's `current_app.logger` in both fallback handlers.
- BUG-004: fixed by reporting installer failures to stderr without masking the original exception.
- BUG-005: fixed by escaping notification values, coercing IDs, and allowing only local absolute action paths.
- BUG-006: fixed by escaping journal text and coercing journal/statement IDs before HTML construction.
- BUG-007: fixed by escaping validation issue text before insertion into the warning list.
- BUG-008: the one independently executing attachment-table DDL path was removed; attachment schema already exists in `services/schema_migrations.py`. Registry DDL strings are guarded by `_is_schema_statement` and are currently non-executing compatibility debt. They still require a migration-backed cleanup pass on an auditable database.
- BUG-010: fixed by aligning `config.py` defaults with the established `wms` / `wms_user` runtime, service, installer, backup, and audit defaults.

BUG-009 is not repaired in this pass. It is a cross-loop posting refactor involving inventory, AR/AP, vouchers, general ledger, reversal, and reconciliation semantics. Project rules prohibit guessing accounting behavior, and the required backup/database/audit environment is absent. It requires an explicitly defined loop-by-loop accounting boundary and a pre-change backup before implementation.

### Continued Inventory Repair — 2026-07-17

The user authorized a subsequent repair pass. The inventory portion of BUG-009 is now structurally improved within the boundary recorded in `docs/inventory_posting_stabilization_boundary_20260717.md`:

- the shared registry movement path delegates positive and negative postings to `services.inventory_service.post_inventory_change`;
- the established project/cabinet-to-common-stock fallback is preserved before delegation;
- route validation, transaction wrapping, document status, transaction type, reference number, warehouse, location, lot, project, cabinet, date, cost, and remark values are preserved;
- service-layer posting now owns balance locking, weighted-average inbound cost, outbound protection, legacy inventory synchronization, batch tracking, and stock transaction creation;
- `services.inventory_service.reverse_inventory_change` now owns balance/cost reversal, legacy summary synchronization, batch tracking reversal, strict consistency assertion, and stock transaction deletion;
- route-level later-transaction guards and document status reversal remain unchanged;
- no active `DELETE FROM stock_transactions` statement remains under `routes/`.

The previous registry balance algorithms remain as unreachable comparison code after the new service returns. They should be deleted only after database-backed inventory acceptance confirms equivalence. Ruff critical checks pass and modified files contain no replacement characters or repeated-question-mark corruption.

The finance portion of BUG-009 remains open. AR/AP, voucher, general-ledger, settlement, accrual, and period behavior require an explicit accounting boundary and a pre-change database backup.

Static repair verification passed:

- Ruff critical parser/name rules (`E9`, `F63`, `F7`, `F82`): no findings.
- No request-time `document_attachments` DDL remains under `routes/`.
- Known unsafe notification-title and bank-partner interpolation patterns: no findings.
- Old `electrical_erp` / `electrical_user` defaults in `config.py`: no findings.
- Modified-file replacement-character scan: zero findings.

## Confirmed Findings

### BUG-001 — Material import precheck always references an undefined variable

- Severity: High
- Evidence: `routes/registry.py:2684-2696`
- Trigger: upload a material CSV and choose the `precheck` action.
- Defect: `_build_material_import_precheck_report(rows, validation_errors)` is called at line 2690, but `rows = list(reader)` is not assigned until line 2696.
- Result: `NameError: name 'rows' is not defined`; operators cannot precheck material imports.
- Required fix direction: consume the validated reader before both precheck and import paths, without consuming it twice.
- Acceptance: valid and invalid CSV precheck returns a report without writing master data; subsequent real import still reads all rows once.

### BUG-002 — Document attachment authorization calls an undefined helper

- Severity: High
- Evidence: `routes/registry.py:7563-7568`; the only `_current_role_allowed` definition is local to `create_app()` in `app.py:513` and is not available in `routes.registry`.
- Trigger: any attachment action that evaluates `_document_attachment_access_allowed`.
- Defect: `_current_role_allowed` is undefined in the registry module.
- Result: `NameError`, preventing attachment access checks and the requested operation.
- Required fix direction: inject the established role checker into the registry dependency set or use the existing registry permission helper. Do not duplicate role semantics.
- Acceptance: admin/manager and document owner cases pass; unauthorized users receive 403 without exposing attachment metadata.

### BUG-003 — Work-order change-control fallback crashes while handling a query failure

- Severity: High
- Evidence: `routes/production_routes.py:1006-1059`
- Trigger: a subquery or change-record query fails while rendering work-order change-control data.
- Defect: both exception handlers call undefined `logger` at lines 1011 and 1059.
- Result: the intended graceful fallback raises `NameError`, hiding the original database error and breaking the page.
- Required fix direction: use `current_app.logger` or inject the module logger consistently.
- Acceptance: force each optional query to fail; the page returns controlled fallback data and logs the original exception.

### BUG-004 — Offline installer error path calls an undefined Python function

- Severity: Medium
- Evidence: `build_offline_installer.py:717-746`
- Trigger: any exception during directory creation, copy, dependency download, script generation, or tarball creation.
- Defect: Python calls `log_error(...)` at line 743. The only `log_error` text in the file is embedded shell-script content, not a Python definition.
- Result: the build reports a second `NameError`, masks the original packaging failure, and may provide misleading release evidence.
- Required fix direction: write to stderr or define a Python logger before `main()`.
- Acceptance: inject a controlled failure and verify the original error and nonzero exit are preserved.

### BUG-005 — Notification list renders unescaped database/API values as HTML

- Severity: High
- Evidence: `templates/notifications/list.html:139-186`
- Inputs inserted without escaping: `n.id`, `n.title`, `n.message`, `n.created_at`, `n.action_url` and derived class values.
- Trigger: load a notification containing HTML/event-handler content in a rendered field.
- Result: DOM/stored script injection in an authenticated user's browser; malicious `action_url` may also create an unsafe link.
- Required fix direction: construct DOM nodes with `textContent`, escape all text/attribute values, and allowlist local action URLs.
- Acceptance: payloads containing tags, quotes, `javascript:` and event handlers render as text or are rejected.

### BUG-006 — Bank statement matching modal renders unescaped journal data as HTML

- Severity: High
- Evidence: `templates/finance/bank_statement_detail.html:185-195`
- Inputs inserted without escaping: `entry_date`, `partner_name`, `summary`, and `id`.
- Trigger: open the matching modal for a statement line when a journal record contains HTML in partner or summary data.
- Result: DOM/stored script injection on a finance page.
- Required fix direction: render values with `textContent` or an explicit HTML/attribute escaping helper; validate numeric IDs.
- Acceptance: hostile partner names and summaries cannot create DOM elements or execute script.

### BUG-007 — Product configuration validation renders operator input as HTML

- Severity: High
- Evidence: `templates/product_configuration_form.html:386-401`
- Trigger: enter HTML/event-handler content in an option name or conflict group and trigger client-side validation.
- Defect: messages containing operator input are joined into `warning.innerHTML` without escaping.
- Result: DOM script injection in the current editing session and potentially after reload if values persist.
- Required fix direction: build the warning list with DOM text nodes or escape every issue string.
- Acceptance: hostile option/group text is displayed literally.

### BUG-008 — Routes perform schema DDL during requests

- Severity: Critical (systemic)
- Evidence: at least 39 executable DDL patterns were found under `routes/`; major helpers include:
  - `routes/registry.py:642` — code-rule table creation;
  - `routes/registry.py:2001` — production-routing column changes;
  - `routes/registry.py:3417` — quality columns and constraints;
  - `routes/registry.py:6642` — production schedule table/columns;
  - `routes/registry.py:11612` — document custom-field table;
  - `routes/registry.py:12322` and `19585` — duplicate transfer-item ensure implementations;
  - `routes/registry.py:12654` — subcontract opening columns;
  - `routes/registry.py:12874` — finance opening columns;
  - `routes/registry.py:14939` and `15463` — quote/invoice schema;
  - `routes/registry.py:18336`, `18493`, `19542`, `20443` — inventory movement/workflow/assembly schema;
  - `routes/registry.py:21640` — permission table;
  - `routes/document_attachment_helpers.py:2` — attachment table.
- Trigger: listing, opening, creating, editing, posting, or administering the affected pages.
- Result: request latency and locks, race conditions, failure under restricted production DB roles, partial schema changes, and schema state that is not represented by the migration ledger.
- Rule violated: all DDL must be written to `services/schema_migrations.py` first and never run in routes/services at request time.
- Required fix direction: inventory every helper and its callers, add missing ordered migrations after a pre-migration backup, then make request helpers read-only capability checks or remove them. Do not edit audits to accept request DDL.
- Acceptance: `rg` finds no executable DDL in routes or request-time services; a clean database migrates once; all affected pages work with an application DB role that has no DDL privilege.

### BUG-009 — Inventory and finance tables are mutated directly in route code

- Severity: Critical (systemic)
- Evidence:
  - direct inventory balance/legacy inventory/stock transaction writes appear throughout `routes/registry.py`, including `7725-7804`, `9374-9401`, `19229-19451`, and multiple workflow blocks;
  - direct AR/AP writes appear in `routes/registry.py`, including `6067`, `6141`, `6177`, `10033`, `11797`, `11880`, `12614`, `12956`, `13084`, `13241`, `15763-15923`, and `16338`;
  - voucher/general-ledger and AR/AP mutations also appear directly in `routes/finance_routes.py`, including `543-598`, `2070-2089`, `2734-2876`, `5544-5590`, and `5896`.
- Result: business routes can bypass locking, idempotency, source-link, reversal, costing, reconciliation, and audit invariants owned by posting services. Equivalent operations may follow different accounting or stock semantics.
- Rule violated: financial records must only be written by designated posting services; inventory posting must use the established posting path.
- Required fix direction: classify each direct write as document-header maintenance versus financial/stock posting, then move posting mutations into the designated services one business loop at a time. This is a structural change and requires explicit implementation scope plus backups for finance/period data.
- Acceptance: each loop posts and reverses through one service transaction; retry/concurrency tests do not duplicate effects; inventory and AR/AP/ledger reconciliation audits pass.

### BUG-010 — Runtime database defaults disagree

- Severity: Medium
- Evidence:
  - `runtime_env.cmd:6-7` defaults to database `wms` and user `wms_user`;
  - `config.py:7-10` defaults to database `electrical_erp` and user `electrical_user`.
- Trigger: starting through different entry points or running tools without `runtime_env.cmd` loaded.
- Result: application, scripts, audits, and maintenance commands can silently target different databases or fail authentication, invalidating test/backup evidence.
- Required fix direction: establish one documented default source or require explicit environment values in every entry point.
- Acceptance: Flask, Waitress, audit, backup, restore, and installer health checks report the same effective host/database/user.

## Verification Blocker

### BLOCK-001 — Mandated audit environment is absent

- No `.venv/Scripts/python.exe` exists.
- The only `python.exe` on PATH is the nonfunctional WindowsApps alias.
- No bundled Python runtime directory is present in this source tree.
- No PostgreSQL Windows service is installed or running.

The following mandatory checks were not executable:

```cmd
python -m compileall app.py routes services scripts
python scripts\source_integrity_audit.py
python scripts\erp_prelaunch_audit.py
python scripts\audit_erp_crud_completeness.py
python scripts\audit_inventory_balance_consistency.py
python scripts\audit_trial_visible_navigation.py
python scripts\audit_trial_direct_access_matrix.py
```

This blocks claims about runtime route registration, schema compatibility, database mojibake, role matrices, inventory consistency, and end-to-end business-loop closure.

## Checks That Passed Statically

- Ruff parser/name analysis completed from the repository's offline Ruff wheel.
- All literal `render_template(...)` references found in `app.py` and `routes/*.py` resolve to existing files: 132 references, zero missing templates.
- 224 literal route decorators were parsed. Two repeated literal paths were legitimate: GET/POST methods for invoice red flush and `/` under distinct blueprint prefixes.
- No actual duplicate literal route conflict was established by the static scan.
- The newly written development guide contains no replacement character or repeated-question-mark corruption.
- The replacement character found in `static/js/xlsx.full.min.js` is inside a third-party minified vendor asset and must be evaluated by the official source-integrity allowlist rather than edited manually.

## Recommended Repair Order

1. Fix BUG-001 through BUG-004 and add narrow regressions.
2. Fix BUG-005 through BUG-007 and test hostile text/URL payloads in the browser.
3. Restore an approved Python/PostgreSQL audit environment and run the complete mandated baseline before further code changes.
4. Define and approve a schema-stabilization boundary for BUG-008; back up before migration work.
5. Define and approve one business-loop posting boundary at a time for BUG-009, starting with inventory movements and purchase/sales AR/AP closure.
6. Resolve BUG-010 before generating backup, restore, or release evidence.
7. Run all targeted loop audits and operator simulation; add newly discovered runtime/data defects to this report rather than weakening audits.

## Required Release Gate After Repairs

```cmd
python -m compileall app.py routes services scripts
python scripts\source_integrity_audit.py
python scripts\erp_prelaunch_audit.py
python scripts\audit_erp_crud_completeness.py
set PG_PASSWORD=<controlled-password> && python scripts\audit_inventory_balance_consistency.py
set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=<controlled-password> && python scripts\audit_trial_visible_navigation.py
set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=<controlled-password> && python scripts\audit_trial_direct_access_matrix.py
```

Then execute and reconcile the sales, procurement, production, subcontracting, inventory, service, finance, trace, and cost workflows with their normal pilot roles. HTTP success alone is not acceptance.
