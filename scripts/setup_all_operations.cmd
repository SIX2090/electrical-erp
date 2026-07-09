@echo off
REM ====================================
REM ERP System Operations Setup
REM ====================================

echo.
echo ========================================
echo    ERP System Operations Setup
echo ========================================
echo.
echo This script will configure:
echo   1. PostgreSQL Auto-Start
echo   2. Daily Auto Backup (2:00 AM)
echo   3. Database Monitor (every 5 minutes)
echo   4. Disk Space Monitor (hourly)
echo.

REM Check admin privileges
net session >nul 2>&1
if %errorLevel% NEQ 0 (
    echo ========================================
    echo ERROR: Administrator privileges required!
    echo ========================================
    echo.
    echo Please follow these steps:
    echo 1. Right-click this script
    echo 2. Select "Run as administrator"
    echo 3. Click "Yes" in the UAC prompt
    echo.
    pause
    exit /b 1
)

echo [OK] Administrator privileges verified
echo.
pause

set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%~dp0..
if "%ERP_TASK_USER%"=="" (
    echo ERROR: ERP_TASK_USER is required. Use a dedicated Windows account for ERP scheduled tasks.
    echo Example: set "ERP_TASK_USER=DOMAIN\erp_ops"
    pause
    exit /b 1
)
set "TASK_CREDENTIAL_ARGS=/RU %ERP_TASK_USER%"
if not "%ERP_TASK_PASSWORD%"=="" set "TASK_CREDENTIAL_ARGS=%TASK_CREDENTIAL_ARGS% /RP %ERP_TASK_PASSWORD%"

echo.
echo ========================================
echo [1/5] Configure PostgreSQL Auto-Start
echo ========================================

set PG_CTL=%PROJECT_ROOT%\pgsql18\pgsql\bin\pg_ctl.exe
set PGDATA=%PROJECT_ROOT%\pgdata

echo Deleting existing task (if any)...
schtasks /Delete /TN "ERP_PostgreSQL_AutoStart" /F >nul 2>&1

echo Creating auto-start task...
schtasks /Create /TN "ERP_PostgreSQL_AutoStart" /TR "\"%PG_CTL%\" -D \"%PGDATA%\" start" /SC ONSTART %TASK_CREDENTIAL_ARGS% /RL HIGHEST /F

if %ERRORLEVEL% EQU 0 (
    echo [OK] PostgreSQL auto-start configured
) else (
    echo [ERROR] Failed to create auto-start task
)

echo.
echo ========================================
echo [2/5] Configure Daily Backup
echo ========================================

set BACKUP_SCRIPT=%SCRIPT_DIR%daily_backup.cmd

echo Deleting existing task (if any)...
schtasks /Delete /TN "ERP_Daily_Backup" /F >nul 2>&1

echo Creating backup task...
schtasks /Create /TN "ERP_Daily_Backup" /TR "\"%BACKUP_SCRIPT%\"" /SC DAILY /ST 02:00 %TASK_CREDENTIAL_ARGS% /RL HIGHEST /F

if %ERRORLEVEL% EQU 0 (
    echo [OK] Daily backup configured (2:00 AM)
) else (
    echo [ERROR] Failed to create backup task
)

echo.
echo ========================================
echo [3/5] Configure Database Monitor
echo ========================================

set DB_MONITOR=%SCRIPT_DIR%monitor_database.cmd

echo Deleting existing task (if any)...
schtasks /Delete /TN "ERP_Monitor_Database" /F >nul 2>&1

echo Creating database monitor task...
schtasks /Create /TN "ERP_Monitor_Database" /TR "\"%DB_MONITOR%\"" /SC MINUTE /MO 5 %TASK_CREDENTIAL_ARGS% /RL HIGHEST /F

if %ERRORLEVEL% EQU 0 (
    echo [OK] Database monitor configured (every 5 minutes)
) else (
    echo [ERROR] Failed to create monitor task
)

echo.
echo ========================================
echo [4/5] Configure Disk Monitor
echo ========================================

set DISK_MONITOR=%SCRIPT_DIR%monitor_disk_space.cmd

echo Deleting existing task (if any)...
schtasks /Delete /TN "ERP_Monitor_Disk" /F >nul 2>&1

echo Creating disk monitor task...
schtasks /Create /TN "ERP_Monitor_Disk" /TR "\"%DISK_MONITOR%\"" /SC HOURLY %TASK_CREDENTIAL_ARGS% /RL HIGHEST /F

if %ERRORLEVEL% EQU 0 (
    echo [OK] Disk monitor configured (hourly)
) else (
    echo [ERROR] Failed to create monitor task
)

echo.
echo ========================================
echo [5/5] Create Backup Directory
echo ========================================

if not exist "%PROJECT_ROOT%\backups\daily" mkdir "%PROJECT_ROOT%\backups\daily"
echo [OK] Backup directory created: backups\daily\

echo.
echo ========================================
echo Configuration Complete!
echo ========================================
echo.
echo Configured tasks:
echo   1. ERP_PostgreSQL_AutoStart - Start DB on system boot
echo   2. ERP_Daily_Backup - Daily backup at 2:00 AM
echo   3. ERP_Monitor_Database - Check DB every 5 minutes
echo   4. ERP_Monitor_Disk - Check disk space hourly
echo.
echo View tasks:
echo   - Run taskschd.msc to open Task Scheduler
echo   - Or run: schtasks /Query /TN "ERP_*" /FO LIST
echo.
echo Log locations:
echo   - logs\db_monitor.log
echo   - logs\disk_monitor.log
echo   - logs\alert_*.txt
echo.
echo Manual testing:
echo   - Backup now: scripts\daily_backup.cmd
echo   - Check DB: scripts\monitor_database.cmd
echo   - Check disk: scripts\monitor_disk_space.cmd
echo.
pause
