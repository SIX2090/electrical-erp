@echo off
REM ====================================
REM Monitoring Configuration
REM ====================================

echo.
echo ========================================
echo ERP System Monitoring Configuration
echo ========================================
echo.

set SCRIPT_DIR=%~dp0
if "%ERP_TASK_USER%"=="" (
    echo ERROR: ERP_TASK_USER is required. Use a dedicated Windows account for ERP scheduled tasks.
    echo Example: set "ERP_TASK_USER=DOMAIN\erp_ops"
    pause
    exit /b 1
)
set "TASK_CREDENTIAL_ARGS=/RU %ERP_TASK_USER%"
if not "%ERP_TASK_PASSWORD%"=="" set "TASK_CREDENTIAL_ARGS=%TASK_CREDENTIAL_ARGS% /RP %ERP_TASK_PASSWORD%"

REM Check admin privileges
net session >nul 2>&1
if %errorLevel% NEQ 0 (
    echo ERROR: Administrator privileges required!
    echo Please right-click this script and select "Run as administrator"
    pause
    exit /b 1
)

echo [1/2] Configuring database monitor (every 5 minutes)...
schtasks /Delete /TN "ERP_Monitor_Database" /F >nul 2>&1
schtasks /Create /TN "ERP_Monitor_Database" /TR "\"%SCRIPT_DIR%monitor_database.cmd\"" /SC MINUTE /MO 5 %TASK_CREDENTIAL_ARGS% /RL HIGHEST /F
if %ERRORLEVEL% EQU 0 (
    echo     [OK] Database monitor task created
) else (
    echo     [ERROR] Database monitor task creation failed
)

echo.
echo [2/2] Configuring disk space monitor (hourly)...
schtasks /Delete /TN "ERP_Monitor_Disk" /F >nul 2>&1
schtasks /Create /TN "ERP_Monitor_Disk" /TR "\"%SCRIPT_DIR%monitor_disk_space.cmd\"" /SC HOURLY %TASK_CREDENTIAL_ARGS% /RL HIGHEST /F
if %ERRORLEVEL% EQU 0 (
    echo     [OK] Disk monitor task created
) else (
    echo     [ERROR] Disk monitor task creation failed
)

echo.
echo ========================================
echo Monitoring Configuration Complete!
echo ========================================
echo.
echo Created monitoring tasks:
echo - ERP_Monitor_Database: Check DB every 5 minutes
echo - ERP_Monitor_Disk: Check disk space hourly
echo.
echo Alert log locations:
echo - logs\db_monitor.log
echo - logs\disk_monitor.log
echo - logs\alert_*.txt (created on issues)
echo.
pause
