@echo off
REM ====================================
REM Auto Backup Configuration
REM ====================================

echo.
echo ========================================
echo ERP Auto Backup Configuration
echo ========================================
echo.

set SCRIPT_DIR=%~dp0
set TASK_NAME=ERP_Daily_Backup
set BACKUP_SCRIPT=%SCRIPT_DIR%daily_backup.cmd
if "%ERP_TASK_USER%"=="" (
    echo ERROR: ERP_TASK_USER is required. Use a dedicated Windows account for ERP scheduled tasks.
    echo Example: set "ERP_TASK_USER=DOMAIN\erp_ops"
    pause
    exit /b 1
)
set "TASK_CREDENTIAL_ARGS=/RU %ERP_TASK_USER%"
if not "%ERP_TASK_PASSWORD%"=="" set "TASK_CREDENTIAL_ARGS=%TASK_CREDENTIAL_ARGS% /RP %ERP_TASK_PASSWORD%"

echo Task name: %TASK_NAME%
echo Backup script: %BACKUP_SCRIPT%
echo Schedule: Daily at 2:00 AM
echo.

REM Check admin privileges
net session >nul 2>&1
if %errorLevel% NEQ 0 (
    echo ERROR: Administrator privileges required!
    echo Please right-click this script and select "Run as administrator"
    pause
    exit /b 1
)

echo [Step 1/3] Deleting existing task (if any)...
schtasks /Delete /TN "%TASK_NAME%" /F >nul 2>&1

echo [Step 2/3] Creating scheduled task...
schtasks /Create /TN "%TASK_NAME%" /TR "\"%BACKUP_SCRIPT%\"" /SC DAILY /ST 02:00 %TASK_CREDENTIAL_ARGS% /RL HIGHEST /F

if %ERRORLEVEL% EQU 0 (
    echo [Step 3/3] Verifying task creation...
    schtasks /Query /TN "%TASK_NAME%" /FO LIST /V
    echo.
    echo ========================================
    echo Auto Backup Configured Successfully!
    echo ========================================
    echo.
    echo Task details:
    echo - Task name: %TASK_NAME%
    echo - Schedule: Daily at 2:00 AM
    echo - Run as: %ERP_TASK_USER%
    echo - Backup location: backups\daily\
    echo - Retention: 30 days
    echo.
    echo Manage tasks:
    echo 1. Open Task Scheduler (taskschd.msc)
    echo 2. Find task: %TASK_NAME%
    echo 3. Right-click to run now, disable, or delete
    echo.
) else (
    echo ERROR: Task creation failed, error code: %ERRORLEVEL%
    pause
    exit /b %ERRORLEVEL%
)

pause
