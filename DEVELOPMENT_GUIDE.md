# ERP Development Guide

## 1. Purpose and Product Boundary

This is the maintenance and extension guide for the low-voltage switchgear and distribution-automation ERP. It is intended to help a developer make a scoped change without breaking a document chain, inventory or finance posting, traceability, permissions, navigation, or the Windows offline deployment.

The product is a manufacturing ERP, not a generic SaaS dashboard. Its primary business axis is:

- product family and machine model;
- project number (`project_code`);
- cabinet number (`cabinet_no`);
- material, BOM, routing, work center, drawing, and engineering change;
- procurement, subcontracting, inventory, production, sales, service, finance, and cost reconciliation.

Project and cabinet numbers are recommended traceability dimensions, not universally mandatory fields. They may be blank for make-to-stock work, simplified small-company operation, or early project preparation unless `require_project_cabinet` is enabled.

The preferred operational benchmark is Digiwin-style manufacturing closure: operators must see source document, current status, blocked reason, owner, next action, and downstream impact. Do not copy a proprietary interface. Apply the workflow logic in this product's own dense, conventional Chinese ERP interface.

## 2. Source-of-Truth Order

Read these files before changing application code, in this order:

1. `AGENTS.md` — mandatory scope, encoding, schema, audit, page-type, and material-entry rules.
2. The user's current request — the only authority to add a route, field, page, menu, module, finance rule, or report.
3. `ERP_SCOPE_PLAN.md` — stabilization priorities and automated baseline.
4. `ERP_BOUNDARY_STABILIZATION.md` — open and closed boundary records.
5. `MENU_ROLLOUT_CLASSIFICATION.md` — route exposure and page classification.
6. `ERP_NEXT_DEVELOPMENT_TASKS.md` — ordered proof and hardening backlog.
7. The phase boundary documents under `docs/` — loop-specific acceptance definitions.
8. Application code and protected audit scripts — the executable implementation and acceptance contract.

`CODE_WIKI.md` contains useful historical architecture notes, but parts of its company, industry, path, and inventory descriptions are stale. It must not override `AGENTS.md`, `README.md`, current code, or current audits.

Audit scripts are protected ground truth. Never edit `scripts/audit_*.py`, `scripts/verify_*.py`, `scripts/validate_*.py`, or `scripts/erp_prelaunch_audit.py` unless the user explicitly requests that exact audit change. Fix application behavior when an audit fails.

## 3. System Shape

The application is a Flask/PostgreSQL monolith optimized for Windows local/server installation.

| Area | Main location | Responsibility |
|---|---|---|
| Application assembly | `app.py` | Flask creation, security hooks, dependency construction, route registration |
| Runtime helpers | `services/app_runtime.py` | DB helpers, authentication decorators, template helpers, database initialization |
| Business routes | `routes/` | HTTP parsing, authorization entry, response/redirect, template composition |
| Business services | `services/` | Posting, calculations, transitions, reconciliation, traceability, permissions |
| Schema | `services/schema_migrations.py` | Ordered, idempotent application DDL migrations |
| Route registry | `routes/registry.py` and registration modules | Dependency binding and blueprint registration |
| Route governance | `routes/route_catalog.py` | Route catalogue and classification support |
| UI | `templates/`, `static/css/`, `static/js/` | Jinja pages, ERP layout, document grids, search/select, import/export |
| Verification | `tests/`, `scripts/` | Unit tests, loop audits, runtime audits, release gates |
| Runtime | `waitress_server.py`, `start.cmd`, `runtime_env.cmd` | Production-style WSGI and Windows environment |
| Packaging | installer/build scripts, `vendor/python-wheels/` | Offline installation and deployment packages |

`create_app()` in `app.py` builds database helpers and injects them into route registration functions. The codebase uses both direct `register_routes(app, deps)` modules and Flask blueprints. Follow the pattern already used by the nearest business module; do not introduce a new framework or registration style for a local change.

The normal request flow is:

```text
Browser
  -> Flask security/login/role and data-scope checks
  -> route handler
  -> domain or posting service
  -> PostgreSQL transaction
  -> audit log and security response headers
  -> Jinja page or JSON/redirect response
```

Routes should coordinate HTTP concerns. Reusable business transitions, posting, costing, and reconciliation belong in services. Financial and inventory writes must use their designated posting paths.

## 4. Core Business Loops

Treat every change as part of one or more loops. A page working in isolation is not acceptance.

| Loop | Required chain and proof focus | Primary implementation areas |
|---|---|---|
| Sales | sales order -> shipment -> inventory issue -> receivable -> settlement/reconciliation | sales/shipment routes, inventory posting, receivable reports |
| Procurement | purchase request -> purchase order -> receipt -> inventory receipt -> payable -> reconciliation | procurement/purchase receipt routes, payable and inventory posting |
| Production | BOM/routing -> work order -> kitting -> requisition/return -> operation report -> completion/inbound -> cost | BOM, MRP, production services and routes, inventory/cost services |
| Subcontracting | subcontract order -> issue to processor -> receive/scrap/short receipt -> inventory -> payable | subcontract routes, inventory and payable posting |
| Inventory | source document -> movement -> balance/lot/location/project dimensions -> transaction ledger -> reversal/reconciliation | `inventory_service.py`, `inventory_posting_service.py`, inventory routes |
| Engineering | product configuration -> drawing/BOM/routing version -> ECN impact -> work-order snapshot | BOM, drawing, ECN, snapshot services |
| Service | cabinet service card -> acceptance/service order -> RMA -> fee/cost closure | after-sale routes/service, trace and cost services |
| Finance | operational posting -> AR/AP/inventory cost/voucher -> reconciliation -> period close -> statements | designated finance services and finance routes |
| Trace and cost | project/cabinet dimension -> documents, movements, service and finance -> trace ledger/cost summary | trace engine, project/cabinet cost services and reports |

For the exact acceptance chain, consult `docs/erp_loop_acceptance_worksheet_20260616.md` and the relevant phase boundary document. Extend those records only in English.

## 5. Mandatory Boundary Definition

Before writing ERP code, record the following in the issue, task note, or an appropriate boundary file:

```text
Business loop:
Problem and requested outcome:
Page type:
Routes exposed or changed:
Page classification (live/fix/readonly/internal/hidden):
Data owner / posting service:
Source document:
Current and target status transition:
Downstream inventory impact:
Downstream finance impact:
Project/cabinet trace impact:
Permission and navigation impact:
Blocked reason and next action behavior:
Acceptance workflow and reconciliation check:
Explicit non-goals:
```

Stop before implementation when the source document, target state, posting owner, accounting rule, or acceptance result is unclear. Add the boundary to `ERP_BOUNDARY_STABILIZATION.md` or `MENU_ROLLOUT_CLASSIFICATION.md` as appropriate. Do not infer settlement, accrual, allocation, or period-close rules.

## 6. Change Workflow

### 6.1 Discover

1. Read `AGENTS.md` and the relevant scope/boundary documents.
2. Locate the route, template, service, permission, catalogue, menu, migration, and targeted audits with `rg`.
3. Search for the same document type and status in all layers. Route names alone are not the business contract.
4. Check whether the page is normal navigation, direct-access only, read-only, internal, or hidden.
5. Identify downstream stock, AR/AP, voucher, trace, cost, attachment, print, export, and return-link consumers.

### 6.2 Reproduce

For a bug, establish the smallest failing operator workflow and record:

- role and data scope;
- route and page type;
- starting document status and data prerequisites;
- operator actions;
- expected state and actual state;
- affected rows or reconciliation report;
- whether retrying could duplicate a post.

Do not refactor adjacent code during a bug fix. If the minimum fix requires a structural change, stop and request approval for the expanded scope.

### 6.3 Implement

- Keep request parsing, flash/redirect, and rendering in routes.
- Put reusable validation, state transition, calculation, and posting behavior in the existing domain service.
- Reuse transaction helpers and lock the same business rows as the existing posting path.
- Use `Decimal`-based helpers for quantities, prices, tax, and costs; do not introduce binary float arithmetic into financial or stock logic.
- Preserve source type, source ID/number/line, project number, cabinet number, lot, warehouse, and location where the loop requires them.
- Make state transitions explicit and reject invalid, repeated, closed, voided, or downstream-consumed operations.
- Keep reversal symmetrical: reverse the original operational impact through the designated service, with linkage and audit evidence.
- Do not create request-time DDL or table-existence repair behavior.

### 6.4 Verify

Run the mandatory gate in Section 13, then the targeted unit/audit checks for the affected loop. Finally perform the operator workflow through its normal role and navigation, and reconcile database/report outcomes. HTTP 200 is never sufficient.

### 6.5 Handoff

Document:

- boundary and non-goals;
- changed files and behavioral result;
- migration and backup evidence, if applicable;
- exact commands and results;
- operator workflow result and reconciliation evidence;
- known limitations and rollback approach.

## 7. Database and Transaction Rules

### 7.1 Schema changes

All DDL must first be represented in `services/schema_migrations.py`. Migrations are ordered and tracked through the `schema_migrations` table. Keep new migrations:

- uniquely versioned and append-only;
- safe to run once and safe to detect as already applied;
- compatible with the application code deployed with them;
- free of `DROP TABLE` and `DROP COLUMN` unless the user explicitly names the object.

Before running any migration:

```cmd
.venv\Scripts\python.exe scripts\pg_backup.py --output backups\pre_migration_<description>.dump
```

After the schema change, at minimum run:

```cmd
.venv\Scripts\python.exe -m compileall app.py routes services
```

Then run the complete verification gate. A schema change is not complete until the deployed target is migrated and the affected workflow is exercised.

Alembic files exist for baseline/legacy compatibility, but application DDL governance is `services/schema_migrations.py`. Do not choose a second migration path without an explicit project decision.

### 7.2 Transactions and concurrency

Posting is a unit of work. Header status, lines, stock movement, balances, trace links, cost/AR/AP effects, and audit evidence must not be left partially committed. Use the repository's cursor/transaction helpers and row-locking patterns. Preserve idempotency guards so double-clicks, retries, and concurrent workers cannot post twice or drive stock negative unexpectedly.

Never use dynamic SQL identifiers from untrusted input. Use parameters for values and existing allowlist/identifier helpers for the few places where identifiers are unavoidable.

### 7.3 Data repair

Do not hide a code defect with a one-off data repair. First fix the posting rule, then use an explicitly scoped repair/backfill script, preview affected rows, back up the database, execute against the intended target, and reconcile afterward. Repair scripts are operational tools, not substitutes for migrations or request-time business logic.

## 8. Inventory and Finance Safety

Inventory is owned by `services/inventory_posting_service.py` and `services/inventory_service.py` or the equivalent established posting path. Business routes must not independently update balances and transaction ledgers. A valid inventory change must keep product, warehouse, location, lot, project, cabinet, quantity, unit cost, amount, direction, source type, source document, and source line consistent where applicable.

Finance records such as AR lines, AP lines, cost lines, vouchers, and period summaries must be written only by designated posting services. Never insert or update finance tables directly in a route handler. Do not change settlement, accrual, allocation, exchange, voucher, or period-close semantics without an explicit accounting rule from the user.

Before any period-close table work, run a backup. For a cross-domain document, identify both owners explicitly; for example, purchase receipt owns receipt state while the posting services own stock and payable effects.

## 9. Routes, Permissions, Navigation, and Page Classification

Every new route requires all of the following:

1. Explicit user authorization for the new scope.
2. Registration in the application's established route/blueprint path.
3. Permission registration in `services/pilot_permissions.py` for every intended role.
4. Classification in `MENU_ROLLOUT_CLASSIFICATION.md` as `live`, `fix`, `readonly`, `internal`, or `hidden`.
5. Catalogue registration in `routes/route_catalog.py` or the current equivalent.
6. Normal navigation reachability for live document-entry and document-list routes.
7. Visible-navigation and direct-access matrix verification.

If a route or page is removed or hidden, audit every menu item, shortcut, return link, redirect, permission expectation, deep link, print/export action, and automated audit. Do not reuse a deleted workbench root as a compatibility entrance.

Role permission and data scope are separate. A user may have permission for a page but still be limited by organization/project/warehouse scope. Enforce both in server-side reads and writes; hiding a button is not authorization.

## 10. ERP Page and UI Rules

Keep these page types separate:

- workbench: pending/exception queues, blocked reason, owner, next action, downstream impact; never a full record list;
- document list/query: filters, status, next action, sorting, batch print/export, links to entry/detail;
- document entry/detail: one voucher with header, line grid, source, status and controlled actions;
- master data: archive attributes, category, status, import/export/template, trace drill-down;
- report/ledger: read-only aggregation or detail, refresh/export/print and source drill-down only;
- finance: controlled posting, reconciliation, period, ledger and statement behavior;
- system admin: users, permissions, configuration, monitoring and operational controls.

A business voucher requires an independent entry route and detail route. Do not implement it as a list-page modal or drawer. List, query, report, and workbench pages must not expose standalone new-document actions.

Document pages should follow dense Chinese ERP conventions: compact toolbar, status-aware actions, search/reference selection, refresh, print, export, return/exit, keyboard-friendly grids, and source/detail drill-down. Do not dilute high-frequency pages into decorative cards.

In every document-entry line grid, the operator selects a material from the material-name field only. Keep `product_id` hidden and populate code, specification, unit, price/cost, tax, and snapshots after selection. Do not expose a second editable material selector column.

Reports are read-only except for refresh, export, print, and drill-down. State the metric basis precisely: untaxed, tax-included, tax, cost, stock value, receivable, payable, balance, settled, or pending.

## 11. Status, Traceability, and Auditability

Use the status vocabulary and transition model already established for that document. Do not add a synonymous status string locally. Normalize legacy English/Chinese values only through the existing boundary helpers, and do not preserve corrupt text as aliases.

For each action define:

- allowed source status;
- target status;
- role and data-scope requirement;
- prerequisite and blocked reason;
- source/downstream quantity guard;
- inventory and finance effects;
- reversal/void behavior;
- audit log description;
- next action after success.

Project and cabinet trace fields should flow when present. Preserve the original source linkage instead of reconstructing it from remarks. Traceability must support drill-down from a business document to its source, downstream documents, movement, finance/cost effect, and service history.

## 12. Encoding and Editing Safety

Operator-facing labels, statuses, and business terms remain clean Chinese. Planning, audit, release, and handoff Markdown documents must be English.

Use `apply_patch` for every manual edit involving Chinese or mixed Chinese/English ERP text. Do not write such content through PowerShell redirection, Python write scripts, heredocs, or console pipelines. If corrupt text already exists, repair or remove the literal; never add a compatibility alias that preserves mojibake.

Always run the source integrity audit after a code or UI change.

## 13. Verification Matrix

Run the mandatory checks in this order after every code change:

```cmd
.venv\Scripts\python.exe -m compileall app.py routes services scripts
.venv\Scripts\python.exe scripts\source_integrity_audit.py
.venv\Scripts\python.exe scripts\erp_prelaunch_audit.py
.venv\Scripts\python.exe scripts\audit_erp_crud_completeness.py
```

Expected results:

| Check | Expected result |
|---|---|
| Compile | no syntax errors |
| Source integrity | `source_integrity=ok`, `source_mojibake_findings=0` |
| Prelaunch | `errors=0`, `warnings=0`, `core_pages=34` |
| CRUD completeness | `targets=46`, `OK=46`, `errors=0` |

For inventory changes:

```cmd
set PG_PASSWORD=admin && .venv\Scripts\python.exe scripts\audit_inventory_balance_consistency.py
```

Expected: `findings=0`.

For permission or navigation changes:

```cmd
set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=admin && .venv\Scripts\python.exe scripts\audit_trial_visible_navigation.py
set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=admin && .venv\Scripts\python.exe scripts\audit_trial_direct_access_matrix.py
```

Expected: visible navigation checks seven users with no unexpected routes; the direct-access matrix passes.

Also run:

- the closest unit tests under `tests/`;
- the loop-specific `audit_*`, `verify_*`, or `validate_*` scripts;
- the exact role-based browser/operator flow;
- a reconciliation query or report that proves downstream data.

Do not declare completion when a required script is unavailable, fails, or reports values outside the expected range. Report the blocker and preserve the evidence.

## 14. Local Development and Runtime

Install from the offline wheelhouse when available:

```cmd
.venv\Scripts\python.exe -m pip install --no-index --find-links vendor\python-wheels -r requirements.txt
```

Start the normal local runtime:

```cmd
start.cmd
```

Or run Flask directly for local development:

```cmd
.venv\Scripts\python.exe app.py
```

The Waitress entry point is `waitress_server.py`. Runtime host/port use `ERP_HOST` and `PORT`. PostgreSQL uses `PG_HOST`, `PG_PORT`, `PG_DATABASE`, `PG_USER`, and `PG_PASSWORD`; legacy `DB_*` fallbacks also exist in `config.py`. Note that defaults in `runtime_env.cmd` and `config.py` differ, so always inspect the effective runtime environment when diagnosing connection problems.

Production mode rejects default database passwords and weak/default `INVENTORY_SECRET_KEY` values. Do not commit local secrets. Use the existing security bootstrap and health-check scripts.

## 15. Testing Strategy

The `tests/` suite provides focused coverage for decimal behavior, inventory concurrency and consistency, MRP, traceability, and cost calculation. Script-based audits cover much broader route, navigation, loop, runtime, and release behavior.

Use three levels of proof:

1. Unit: pure calculation, validation, normalization, and concurrency invariants.
2. Integration/audit: schema, route, permission, posting, reconciliation, and cross-document contracts.
3. Operator acceptance: normal login, visible navigation, document workflow, status actions, print/export where relevant, and downstream reconciliation.

When fixing a defect, add or run the narrowest regression that fails before the fix and passes after it. Do not weaken global audits or change their thresholds.

## 16. Backup, Restore, Release, and Rollback

Production must run a daily scheduled backup:

```cmd
.venv\Scripts\python.exe scripts\pg_backup.py
```

Before go-live, perform a restore drill against a controlled target:

```cmd
.venv\Scripts\python.exe scripts\pg_restore.py --input <dump_file>
```

Record backup path, timestamp, size, restore target, restore result, and validation evidence. Never test restoration over the live database.

Before building an offline package, refresh its intended database snapshot only with explicit release scope, then run:

```cmd
.venv\Scripts\python.exe scripts\audit_installer_package.py --deep
```

The package must include application code, templates/static assets, scripts, required documentation, offline dependencies, startup/installer scripts, and the approved database snapshot. Exclude virtual environments, live PostgreSQL data, logs, caches, local secrets, and unintended backup dumps.

Rollback planning must distinguish code rollback from data reversal. A code rollback cannot undo posted inventory or finance data. Use business reversal services or a controlled database restore chosen before release; do not improvise destructive SQL after failure.

## 17. Debugging Guide

### Route returns 404 or disappears from navigation

Check registration, blueprint binding, route catalogue, rollout classification, permission registry, environment navigation mode, normal-menu template data, and redirect targets. Then run both navigation audits.

### Route returns 403 for one role

Check page permission, action permission, high-risk route guards, data-scope rules, organization/project/warehouse ownership, and direct-access expectations. Verify server-side enforcement, not only button visibility.

### Document status is correct but balances are wrong

Trace the posting service call, transaction boundary, source identity, duplicate guard, unit cost, direction, warehouse/location/lot/project/cabinet dimensions, and reversal path. Run the inventory consistency audit and reconcile movement ledger to balance and source lines.

### AR/AP or statements disagree with operations

Identify the designated posting event, source document number/ID, tax-included basis, settlement or void history, voucher link, posting period, and reconciliation report. Do not repair finance rows from a route or guess an accounting rule.

### Migration succeeds locally but runtime fails

Confirm effective database/environment, migration version row, deployment order, optional/legacy columns, packaged snapshot age, and application/schema compatibility. Restore the pre-migration backup on a controlled target when diagnosis requires rollback.

### Chinese labels are corrupted

Stop editing through console pipelines. Locate the source literal with the integrity audit, repair it with `apply_patch`, and rerun source integrity plus the exact rendered-page check.

## 18. Current Development Priorities

Unless the user changes scope, development order is:

1. Re-prove the automated baseline and route classification.
2. Prove sales, procurement, inventory, engineering/MRP, production, subcontracting, service, and finance loops end to end.
3. Harden document grids, list search/next-action behavior, read-only reports, and practical master-data maintenance.
4. Complete offline package, backup/restore drill, and trial-operation evidence.
5. Only after core stabilization, consider advanced after-sale, quality, payroll, assets, logistics, marketing, custom documents, or custom reports.

Use `ERP_NEXT_DEVELOPMENT_TASKS.md` for the detailed task order. Do not interpret a large number of existing routes/templates as proof that every module is production-ready; rollout classification and loop acceptance determine readiness.

## 19. Definition of Done

A change is done only when:

- its boundary and non-goals were explicit before coding;
- the correct page type and route classification were preserved;
- permissions, data scope, navigation, catalogue, links, redirects, print/export, and audits were updated where affected;
- schema and posting ownership rules were followed;
- invalid/repeated/downstream-blocked status actions are protected;
- source, project, cabinet, inventory, finance, and cost linkage is preserved where applicable;
- mandatory and targeted checks pass exactly;
- an operator can complete the workflow through normal navigation;
- downstream data reconciles, not merely renders;
- migration backup, restore/rollback, and release evidence exists when applicable;
- no corrupt Chinese text, placeholder workflow, or hidden audit failure remains.

## 20. Developer Quick Checklist

```text
[ ] Read AGENTS.md and current boundary/classification documents.
[ ] Confirm the user explicitly authorized every new route/field/page/menu/report.
[ ] Define loop, page type, source, target, owner, posting effects, and acceptance.
[ ] Find route + service + template + permission + catalogue + menu + audits.
[ ] Make the minimum scoped change using existing patterns.
[ ] Use migration + pre-migration backup for DDL.
[ ] Use designated inventory/finance posting services.
[ ] Preserve status, source, project/cabinet, lot, warehouse/location, and audit links.
[ ] Run compile, source integrity, prelaunch, and CRUD checks in order.
[ ] Run inventory and/or permission/navigation checks when affected.
[ ] Run targeted tests and the exact operator workflow.
[ ] Reconcile downstream inventory/finance/trace/cost results.
[ ] Record evidence, limitations, and rollback method.
```
