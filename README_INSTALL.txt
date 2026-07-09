# WMS ERP Offline Installer

This package installs and starts the WMS ERP local trial runtime on Windows without internet access.

## Install

Run either command from this folder:

```cmd
install.cmd
```

or:

```cmd
offline_one_click_install.cmd
```

The installer checks the bundled Python installer/runtime, PostgreSQL archive/runtime, offline Python wheels, and database backup. It then creates `.venv`, initializes local PostgreSQL, restores `db\wms_current.dump` only when the target database is empty, compiles the Python source, runs prelaunch audit checks, and starts the ERP service.

## Audit Package Without Installing

```cmd
offline_one_click_install.cmd /audit
```

The audit checks installer files, bundled Python, PostgreSQL archive contents, extracted PostgreSQL runtime, offline wheels, database dump presence, source integrity hooks, and ERP prelaunch audit wiring without creating a virtual environment or database.

## Start After Install

```cmd
start.cmd
```

Default URL:

```text
http://127.0.0.1:5000
```

To change the application port, edit `runtime_env.cmd` and set `PORT`. To change PostgreSQL port, set `PG_PORT` before first database initialization.

## Reinstall Notes

Running the installer again will not overwrite an existing non-empty local database. To intentionally rebuild the local database from the bundled backup, run:

```cmd
set FORCE_DB_RESTORE=1
offline_one_click_install.cmd
```

## Included Documentation

- `README_INSTALL.txt`: installation quick start.
- `OPERATIONS_MANUAL.md`: operations, backup, restore, health checks, and troubleshooting.
- `DEVELOPMENT_GUIDE.md`: development setup, package maintenance, scope rules, and verification commands.
- `AGENTS.md`: project rules and acceptance constraints.
- `MENU_ROLLOUT_CLASSIFICATION.md`: page rollout classification.
- `ERP_BOUNDARY_STABILIZATION.md`: business boundary records.

## Requirements

- Windows workstation or Windows Server.
- Python 3.11 is bundled as `payload\python\python-3.11.9-amd64.exe` and `payload\python\runtime`.
- Bundled PostgreSQL runtime is included under `pgsql18`.
- Port 5432 available for PostgreSQL unless `PG_PORT` is changed before first initialization.
- Default application port 5000 available unless `PORT` is changed in `runtime_env.cmd`.

## Contents

- ERP source, routes, services, templates, static files, and scripts.
- PostgreSQL archive: `postgresql-18.4-1-windows-x64-binaries.zip`.
- Extracted PostgreSQL runtime: `pgsql18`.
- Python installer/runtime: `payload\python`.
- Offline Python wheels: `vendor\python-wheels`.
- Database backup: `db\wms_current.dump`.
- Installer, start, restart, and runtime command files.

## Intentional Exclusions

The offline zip intentionally excludes machine-local runtime state:

- `.venv`
- `pgdata`
- `logs`
- `runtime_local_secrets.cmd`
- `__pycache__`
- `.pytest_cache`
