# ERP Operations Manual

This manual covers the offline Windows runtime delivered in the one-click installer package.

## Runtime Boundary

- Operating system: Windows workstation or Windows Server.
- Application entry point: `waitress_server.py`, started by `start.cmd`.
- Database: bundled local PostgreSQL runtime under `pgsql18` with data stored in `pgdata` after installation.
- Default URL: `http://127.0.0.1:5000`.
- Runtime secrets: generated locally by `scripts/ensure_local_security_env.py` into `runtime_local_secrets.cmd`; this file is intentionally not included in the offline zip.

## First Install

1. Extract the offline zip to a local directory with enough free disk space.
2. Run `offline_one_click_install.cmd` from the extracted directory.
3. Wait for the installer to finish dependency setup, PostgreSQL initialization, database restore, compile check, and prelaunch audit.
4. Open `http://127.0.0.1:5000` in a browser.

To audit the package without installing anything, run:

```cmd
offline_one_click_install.cmd /audit
```

## Daily Start And Stop

Start the ERP:

```cmd
start.cmd
```

Restart the ERP application process:

```cmd
restart_erp.cmd
```

Stop the application by closing the console window or pressing `Ctrl+C`. Stop the bundled PostgreSQL runtime only when maintenance is required:

```cmd
pgsql18\pgsql\bin\pg_ctl.exe -D pgdata stop
```

## Database Backup

Production operations must run a daily PostgreSQL backup through Windows Task Scheduler or an equivalent scheduler.

Manual backup:

```cmd
.venv\Scripts\python.exe scripts\pg_backup.py --output backups\manual_backup.dump
```

Pre-migration backup:

```cmd
.venv\Scripts\python.exe scripts\pg_backup.py --output backups\pre_migration_description.dump
```

## Restore Drill

Before go-live, perform a restore drill against a controlled restore target. Do not test restore against the only production copy.

```cmd
pgsql18\pgsql\bin\psql.exe -h %PG_HOST% -p %PG_PORT% -U %PG_USER% -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE wms_restore_drill OWNER wms_user;"
cmd /c "call runtime_env.cmd && set PG_DATABASE=wms_restore_drill&& .venv\Scripts\python.exe scripts\pg_restore.py --input backups\manual_backup.dump --force"
```

The restore command replaces the target database content. Confirm the target before running it, and never point `PG_DATABASE` at the active production or development database during a drill.

The system backup page reads `backups\backup_log.txt` and shows the latest restore drill status. A valid go-live drill should leave a `RESTORE_OK` record from `scripts\pg_restore.py` against the controlled restore target.

## System Parameter Review

Before changing production parameters, open `System -> Parameters` and review the parameter effect matrix.

Required review points:

- Confirm the affected business area and data owner.
- Confirm the parameter keys being changed.
- Confirm the downstream workflow that must be tested after saving.
- Re-run navigation and direct-access audits after permission, navigation, or system-control changes.

Parameters must not be treated as decorative settings. A parameter is accepted only when the affected workflow can be completed and reconciled after the change.

## Operation Log Retention

Operation logs are system audit records. Admin and manager users may delete selected log rows or clear keyword-filtered log rows from the operation log page.

When no keyword filter is provided, the clear action uses `operation_log_retention_days` from system parameters and deletes only logs older than that retention period. The default retention is 180 days, with a minimum accepted value of 30 days.

Do not clear all operation logs before go-live or acceptance handoff. Export or archive important audit evidence before any cleanup.

## Rebuild From Bundled Snapshot

The installer will not overwrite a non-empty existing local database by default. To intentionally restore from `db\wms_current.dump`, run:

```cmd
set FORCE_DB_RESTORE=1
offline_one_click_install.cmd
```

## Health Checks

Run these checks after installation, after package updates, and before acceptance handoff:

```cmd
.venv\Scripts\python.exe -m compileall app.py routes services scripts
.venv\Scripts\python.exe scripts\source_integrity_audit.py
.venv\Scripts\python.exe scripts\erp_prelaunch_audit.py
.venv\Scripts\python.exe scripts\audit_erp_crud_completeness.py
```

Expected results:

- `source_integrity=ok`
- `source_mojibake_findings=0`
- `core_pages=34 errors=0 warnings=0`
- `erp_crud_targets=46 ok=46 warnings=0 errors=0`

For inventory-related releases, also run:

```cmd
set PG_PASSWORD=admin && .venv\Scripts\python.exe scripts\audit_inventory_balance_consistency.py
```

Expected result: `findings=0`.

## Troubleshooting

### Package Audit Fails

Run:

```cmd
offline_one_click_install.cmd /audit
```

Check that the extracted directory contains `db\wms_current.dump`, `vendor\python-wheels`, `payload\python`, `pgsql18`, and `postgresql-18.4-1-windows-x64-binaries.zip`.

### Application Cannot Connect To Database

Check PostgreSQL status:

```cmd
pgsql18\pgsql\bin\pg_ctl.exe -D pgdata status
```

Start PostgreSQL if needed:

```cmd
pgsql18\pgsql\bin\pg_ctl.exe -D pgdata start
```

### Port Conflict

The default application port is configured in `runtime_env.cmd` as `PORT`. PostgreSQL uses `PG_PORT`. Change only when the target machine already uses the default port.

### Source Integrity Fails

Do not bypass the audit. Repair corrupt source literals, mojibake, replacement characters, or invalid Chinese labels before release.

## Security Notes

- Change default local credentials before production use.
- Keep `runtime_local_secrets.cmd` machine-local and out of release zips.
- Restrict database and application ports to trusted machines.
- Keep backup dumps protected; they contain business data.
- Do not run schema migrations without a pre-migration backup.
