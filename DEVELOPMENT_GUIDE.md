# ERP Development Guide

This guide describes how to maintain the packaged ERP without changing the business scope accidentally.

## Project Layout

- `app.py`: Flask application setup and route registration entry point.
- `routes/`: page routes and business-facing handlers.
- `services/`: shared business services, posting services, permissions, and schema migrations.
- `templates/`: Jinja templates for ERP pages.
- `static/`: CSS, JavaScript, and frontend assets.
- `scripts/`: verification, backup, restore, installer, and audit utilities.
- `db/wms_current.dump`: packaged database snapshot used by the offline installer.
- `vendor/python-wheels`: offline dependency wheelhouse.
- `payload/python`: bundled Python installer/runtime.
- `pgsql18`: bundled PostgreSQL runtime.
- `release/offline`: generated offline package staging folders and zip files.

## Local Development Setup

Use the project virtual environment:

```cmd
.venv\Scripts\python.exe -m pip install --no-index --find-links vendor\python-wheels -r requirements.txt
```

Start the local ERP runtime:

```cmd
start.cmd
```

Run the installer package audit without changing the database:

```cmd
.venv\Scripts\python.exe scripts\audit_installer_package.py --deep
```

## Business Scope Rules

Before ERP code changes, define the affected loop and page type. Keep document entry, document list, query/report, master data, workbench, finance, and system admin pages separate.

Do not add routes, database fields, modules, menus, or reports unless the current session explicitly asks for them. Stabilize existing core loops before expanding scope.

## Database Change Rules

All DDL must be added to `services/schema_migrations.py` first. Do not run DDL inside route handlers or request-time services.

Before any schema migration, run:

```cmd
.venv\Scripts\python.exe scripts\pg_backup.py --output backups\pre_migration_description.dump
```

Never drop tables or columns unless the user explicitly names the object to remove.

## Route Change Checklist

For each new route under `routes/`, complete all required registration work before release:

- Register permissions in `services/pilot_permissions.py`.
- Classify the page in `MENU_ROLLOUT_CLASSIFICATION.md`.
- Catalogue the route in `routes/route_catalog.py` or the equivalent registry.
- Confirm normal navigation visibility when the route is a live document entry or document list page.

## Required Verification

Run these after code or package changes:

```cmd
.venv\Scripts\python.exe -m compileall app.py routes services scripts
.venv\Scripts\python.exe scripts\source_integrity_audit.py
.venv\Scripts\python.exe scripts\erp_prelaunch_audit.py
.venv\Scripts\python.exe scripts\audit_erp_crud_completeness.py
```

Expected results:

- Compile: no syntax errors.
- Source integrity: `source_integrity=ok` and `source_mojibake_findings=0`.
- Prelaunch audit: `core_pages=34 errors=0 warnings=0`.
- CRUD audit: `erp_crud_targets=46 ok=46 warnings=0 errors=0`.

For inventory changes:

```cmd
set PG_PASSWORD=admin && .venv\Scripts\python.exe scripts\audit_inventory_balance_consistency.py
```

For permission or navigation changes:

```cmd
set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=admin && .venv\Scripts\python.exe scripts\audit_trial_visible_navigation.py
set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=admin && .venv\Scripts\python.exe scripts\audit_trial_direct_access_matrix.py
```

## Offline Package Maintenance

Before rebuilding the offline zip, refresh the packaged database snapshot:

```cmd
set PG_PASSWORD=admin && .venv\Scripts\python.exe scripts\pg_backup.py --output db\wms_current.dump
```

The offline package must include:

- Installer scripts: `offline_one_click_install.cmd`, `install.cmd`, `start.cmd`, `restart_erp.cmd`, `runtime_env.cmd`.
- ERP code: `app.py`, `routes`, `services`, `templates`, `static`, `scripts`.
- Offline dependencies: `requirements.txt`, `vendor\python-wheels`, `payload\python`, `postgresql-18.4-1-windows-x64-binaries.zip`, `pgsql18`.
- Database snapshot: `db\wms_current.dump`.
- Documentation: `README_INSTALL.txt`, `OPERATIONS_MANUAL.md`, `DEVELOPMENT_GUIDE.md`, `AGENTS.md`, `MENU_ROLLOUT_CLASSIFICATION.md`, `ERP_BOUNDARY_STABILIZATION.md`.

The offline package must exclude:

- `.venv`
- `pgdata`
- `logs`
- `__pycache__`
- `.pytest_cache`
- `runtime_local_secrets.cmd`
- local backup dumps unless explicitly requested

After packaging, run from the extracted package folder:

```cmd
offline_one_click_install.cmd /audit
```

## Encoding Rules

Markdown planning, audit, handoff, and release documents should be written in English. Operator-facing ERP labels may be Chinese, but edits to Chinese text must use the project-approved patch flow and must pass `scripts\source_integrity_audit.py`.

Never leave mojibake, replacement characters, or repeated question-mark text in source, templates, routes, services, navigation, or operator-facing pages.
