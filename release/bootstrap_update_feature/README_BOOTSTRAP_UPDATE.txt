ERP version update bootstrap package

Purpose
This package installs the "Version Updates" page into an existing C:\erp deployment
that does not yet have the update feature.

Files changed in C:\erp
- services\update_service.py
- services\app_runtime.py
- routes\system_management_routes.py
- templates\base.html
- templates\version_updates.html

How to install on the Tencent Cloud Windows server
1. Copy the whole bootstrap_update_feature folder to the server, for example:
   C:\erp\bootstrap_update_feature

2. Open PowerShell as Administrator.

3. Run:
   cd C:\erp\bootstrap_update_feature
   powershell -ExecutionPolicy Bypass -File .\install_bootstrap_update.ps1 -TargetRoot C:\erp

4. Restart ERP:
   C:\erp\restart_erp.cmd

5. Open ERP with an admin or manager account:
   http://127.0.0.1:5000/system/version-updates

Rollback
The installer backs up overwritten files under:
  C:\erp\backups\bootstrap_update_feature_yyyyMMdd_HHmmss

To roll back, copy the files from that backup folder back to C:\erp and run:
  C:\erp\restart_erp.cmd

Future update package format
After this bootstrap is installed, put future update packages under:
  C:\erp\updates

Recommended structure:
  C:\erp\updates\WMS_ERP_Update_20260615\
    update_manifest.json
    install_update.ps1

Example update_manifest.json:
{
  "version": "2026-06-15 10:00:00",
  "package_name": "WMS_ERP_Update_20260615",
  "entry_script": "install_update.ps1",
  "notes": "Describe this update here"
}
