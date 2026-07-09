# Backend Security and Malware Indicator Audit

Date: 2026-06-10
Scope: `app.py`, `routes/`, `services/`, `scripts/`, startup/install command files, runtime configuration, scheduled tasks, and active ERP-related processes in `C:\WMS1_ERP_OneClick_Package`.

## Executive Summary

No direct evidence of AI-generated malware, hidden payloads, remote downloader execution, credential exfiltration, antivirus tampering, registry persistence, or command-and-control network activity was found in the project-owned ERP code reviewed in this pass.

The ERP package does contain legitimate high-privilege operational scripts for PostgreSQL startup, daily backup, and monitoring. These are not malware indicators by themselves, but they must be controlled because they run through Windows Task Scheduler as `SYSTEM`.

The main go-live security concerns are operational hardening items rather than confirmed malicious code: LAN exposure on port 5000, one stale duplicate `waitress_server.py` process, upload handling without file-size and malware scanning enforcement, and a legacy monitoring script that still contains the default database password literal.

## Audit Coverage

Reviewed areas:

- Flask app factory, startup entry points, and Waitress entry point.
- Route and service source files under `routes/` and `services/`.
- Operational scripts under `scripts/`.
- Offline installer and runtime command files.
- Runtime local secrets file presence and current non-default values.
- Windows scheduled tasks for ERP names.
- Current ERP Python/PostgreSQL process command lines and listening sockets.
- Static search for encoded payloads, suspicious dynamic execution, outbound networking, persistence, and shell execution patterns.

Excluded from malware judgement:

- Third-party bundled runtimes and dependencies under `.venv/`, `payload/python/runtime/`, `pgsql18/`, `static/cdn/`, and `release/` were treated as vendor/runtime artifacts unless referenced by project-owned execution paths.

## Malware Indicator Findings

### M-01: No encoded payloads found

Severity: Informational

Evidence: A repository scan for long Base64 and long hex-escaped blobs in project-owned app, route, service, script, static, and template files returned `encoded_blob_findings=0`.

Impact: No evidence was found of hidden encoded malware payloads in reviewed project-owned files.

Fix: None required.

### M-02: No remote downloader execution pattern found

Severity: Informational

Evidence: Searches for `Invoke-Expression`, `EncodedCommand`, `DownloadString`, `DownloadFile`, `certutil`, `bitsadmin`, `mshta`, antivirus tampering commands, registry startup modification, and script-based download-and-execute patterns found no project-owned malicious execution chain. Matches in `offline_one_click_install.cmd` were local PowerShell operations for timestamps, safe local cleanup, sleeps, and writing local runtime configuration.

Impact: No evidence was found that the ERP installs or runs code fetched from an external remote source.

Fix: None required.

### M-03: No suspicious outbound ERP process activity found

Severity: Informational

Evidence: Active TCP connections for ERP Python processes showed only loopback connections for process `378700`; no external `Established` connection was present. PostgreSQL listens on `127.0.0.1` and `::1` port `5432`; ERP web listens on `0.0.0.0:5000`.

Impact: Runtime network evidence did not show outbound exfiltration behavior during this audit window.

Fix: Continue monitoring in production with firewall logs or EDR if available.

## Security Findings

### S-01: ERP scheduled tasks run as SYSTEM

Severity: Medium

Location: `scripts/setup_all_operations.cmd`, `scripts/setup_auto_backup.cmd`, `scripts/setup_monitoring.cmd`, `scripts/setup_pg_autostart.cmd`

Evidence:

- `scripts/setup_pg_autostart.cmd:29` creates `ERP_PostgreSQL_AutoStart` as `SYSTEM`.
- `scripts/setup_auto_backup.cmd:34` creates the daily backup task as `SYSTEM`.
- `scripts/setup_monitoring.cmd:25` and `scripts/setup_monitoring.cmd:35` create monitoring tasks as `SYSTEM`.

Impact: These are legitimate operations tasks, but if script files are modified by an unauthorized user, the next scheduled run executes modified code with high privileges.

Fix: Restrict write permissions on the ERP installation directory and scripts, record task definitions during deployment, and monitor changes to `scripts/*.cmd` and `scripts/*.py`.

False positive notes: The currently observed task `ERP_Daily_Backup` runs `C:\WMS1_ERP_OneClick_Package\scripts\daily_backup.cmd` and last result was `0`; this is expected backup behavior.

### S-02: ERP web server listens on all interfaces

Severity: Medium

Location: `waitress_server.py:12`

Evidence: `serve(app, host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), threads=8)`.

Impact: The ERP is reachable from other machines if the OS firewall or network allows access to port `5000`. This is not malware, but it increases attack surface.

Fix: For local-only deployment, bind to `127.0.0.1`. For LAN deployment, restrict Windows Firewall inbound rules and place authentication/reverse proxy controls in front as needed.

### S-03: Duplicate Waitress ERP process observed

Severity: Low

Location: Runtime process list

Evidence: Two Python processes were running `waitress_server.py`: process `384180` from `.venv\Scripts\python.exe` and process `378700` from `payload\python\runtime\python.exe`. Only process `378700` owned the listening socket on port `5000` during the check.

Impact: A stale duplicate process can confuse operations and may retain old code/config in memory, although no malicious behavior was observed.

Fix: Stop the non-listening duplicate process after confirming it is not handling traffic, then restart ERP using one standard startup path.

### S-04: Legacy database monitor contains default password literal

Severity: Medium

Location: `scripts/monitor_database.cmd:13`

Evidence: Historical versions contained a hardcoded local database password in an inline Python health check.

Impact: Current runtime secrets use a strong non-default `PG_PASSWORD`, so this appears stale. However, a hard-coded default password in an operations script can cause false monitoring failures and normalizes insecure defaults.

Fix: Change the monitor script to load `runtime_env.cmd` and use `%PG_PASSWORD%` rather than the literal default. Run audits after the change.

### S-05: Uploaded attachments are extension-filtered but not malware-scanned

Severity: Medium

Location: `routes/registry.py:267`, `routes/registry.py:7790`, `routes/registry.py:7865`, `routes/attachment_routes.py:49`

Evidence: Uploads are restricted by extension and saved with generated names; downloads are served as attachments with `application/octet-stream` and `X-Content-Type-Options: nosniff`. The allowed extensions include `.zip`.

Impact: There is no evidence that uploaded files are executed by the ERP, but users can store and later download potentially unsafe files. This is common for ERP attachments but should be controlled before production.

Fix: Add maximum upload size, optional antivirus scan/quarantine, and stricter extension rules for production. Keep forced-download behavior.

## Positive Security Controls Observed

- CSRF protection is registered through `CSRFProtect(app)` in `app.py`.
- Production mode refuses default database passwords and weak/default inventory secret keys in `services/env_config.py`.
- Current `runtime_local_secrets.cmd` contains non-default database password and inventory secret key values.
- Login protection includes rate limiting and lockout helpers.
- Attachment downloads are restricted to `static/uploads` and use path normalization plus `relative_to` checks.
- Python installer signature is valid and signed by the Python Software Foundation.
- PostgreSQL listens only on loopback for database access.

## Verification Commands Run

- Static suspicious command and persistence scans with `rg`.
- Static dangerous Python/JavaScript sink scans with `rg` and AST import enumeration.
- Encoded payload scan for long Base64 and hex blobs.
- Windows scheduled task checks for ERP task names.
- ERP process command line inspection via `Get-CimInstance Win32_Process`.
- TCP listener and established connection checks via `Get-NetTCPConnection`.
- SHA256 hash capture for bundled Python installer and PostgreSQL zip.
- Authenticode signature check for bundled Python installer.

## Limitations

- Windows Defender PowerShell cmdlet `Get-MpThreatDetection` was unavailable in this environment, so antivirus detection history could not be read through that interface.
- This audit is not a full binary reverse-engineering pass over vendor runtimes.
- Runtime network observation only covers the audit window, not historical network activity.
