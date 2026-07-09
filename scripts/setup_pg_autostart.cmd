@echo off
REM ====================================
REM PostgreSQL Auto-Start Configuration
REM ====================================

echo.
echo ========================================
echo PostgreSQL Auto-Start Configuration
echo ========================================
echo.

set PROJECT_ROOT=%~dp0..
set PG_CTL=%PROJECT_ROOT%\pgsql18\pgsql\bin\pg_ctl.exe
set PGDATA=%PROJECT_ROOT%\pgdata
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

echo [Step 1/2] Deleting existing task (if any)...
schtasks /Delete /TN "ERP_PostgreSQL_AutoStart" /F >nul 2>&1

echo [Step 2/2] Creating auto-start task...
schtasks /Create /TN "ERP_PostgreSQL_AutoStart" /TR "\"%PG_CTL%\" -D \"%PGDATA%\" start" /SC ONSTART %TASK_CREDENTIAL_ARGS% /RL HIGHEST /F

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo PostgreSQL Auto-Start Configured!
    echo ========================================
    echo.
    echo Database will auto-start on system boot
    echo Task name: ERP_PostgreSQL_AutoStart
    echo.
    echo Checking current database status...
    "%PG_CTL%" -D "%PGDATA%" status
    echo.
) else (
    echo ERROR: Task creation failed, error code: %ERRORLEVEL%
    pause
    exit /b %ERRORLEVEL%
)

pause
