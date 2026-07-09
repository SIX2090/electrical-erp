@echo off
setlocal EnableExtensions
chcp 65001 >nul

cd /d "%~dp0"

if exist "%~dp0runtime_env.cmd" call "%~dp0runtime_env.cmd"

if not exist ".venv\Scripts\python.exe" (
    echo Python virtual environment is missing.
    echo Run offline_one_click_install.cmd first.
    set "FAILED_CODE=1"
    goto :fail
)

if not exist "logs" mkdir "logs" >nul 2>nul

if "%PG_PASSWORD%"=="" (
    ".venv\Scripts\python.exe" scripts\ensure_local_security_env.py
    if errorlevel 1 (
        echo Failed to prepare local security configuration.
        set "FAILED_CODE=1"
        goto :fail
    )
    if exist "%~dp0runtime_env.cmd" call "%~dp0runtime_env.cmd"
)

call :ensure_postgres
if errorlevel 1 (
    set "FAILED_CODE=%ERRORLEVEL%"
    goto :fail
)

".venv\Scripts\python.exe" scripts\source_integrity_audit.py
if errorlevel 1 (
    echo Source integrity gate failed. Fix source mojibake or contaminated source files before startup.
    set "FAILED_CODE=1"
    goto :fail
)

if "%PORT%"=="" set "PORT=5000"
if "%ERP_HOST%"=="" set "ERP_HOST=0.0.0.0"

echo Starting WMS ERP on %ERP_HOST%:%PORT%
".venv\Scripts\python.exe" waitress_server.py
set "FAILED_CODE=%ERRORLEVEL%"
if not "%FAILED_CODE%"=="0" goto :fail
exit /b 0

:fail
if "%FAILED_CODE%"=="" set "FAILED_CODE=1"
echo.
echo WMS ERP failed to start. Exit code: %FAILED_CODE%
echo Check logs:
echo   %CD%\install.log
echo   %CD%\logs\postgres_runtime.log
echo   %CD%\logs
echo.
pause
exit /b %FAILED_CODE%

:ensure_postgres
if "%PG_HOST%"=="" set "PG_HOST=127.0.0.1"
if "%PG_PORT%"=="" set "PG_PORT=5432"
if "%PG_DATABASE%"=="" set "PG_DATABASE=wms"
if "%PG_USER%"=="" set "PG_USER=wms_user"
set "PG_CTL=%CD%\pgsql18\pgsql\bin\pg_ctl.exe"
set "PG_ISREADY=%CD%\pgsql18\pgsql\bin\pg_isready.exe"
set "PG_LOG_FILE=%CD%\logs\postgres_runtime.log"

if exist "%PG_ISREADY%" (
    "%PG_ISREADY%" -h %PG_HOST% -p %PG_PORT% -U %PG_USER% -d %PG_DATABASE% >nul 2>nul
    if not errorlevel 1 exit /b 0
)

if /I not "%PG_HOST%"=="127.0.0.1" if /I not "%PG_HOST%"=="localhost" (
    echo PostgreSQL is not ready on %PG_HOST%:%PG_PORT%.
    exit /b 1
)

if not exist "%PG_CTL%" (
    echo PostgreSQL runtime is missing. Run offline_one_click_install.cmd first.
    exit /b 1
)
if not exist "pgdata\PG_VERSION" (
    echo PostgreSQL data directory is missing. Run offline_one_click_install.cmd first.
    exit /b 1
)

".venv\Scripts\python.exe" scripts\check_windows_postgres_runtime.py
if errorlevel 1 (
    echo Local PostgreSQL cannot run on this Windows version.
    echo Use Windows Server 2019 or newer, or set PG_HOST to an external PostgreSQL server.
    exit /b 1
)

if exist "pgdata\postmaster.pid" powershell -NoProfile -ExecutionPolicy Bypass -Command "$pidFile = Join-Path (Get-Location) 'pgdata\postmaster.pid'; if (Test-Path $pidFile) { $lines = Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue; if ($lines.Count -ge 2) { $serverPid = [int]$lines[0]; $dataDir = $lines[1].Trim(); $expected = (Resolve-Path -LiteralPath 'pgdata').Path; try { $proc = Get-Process -Id $serverPid -ErrorAction Stop; if ($proc.ProcessName -ne 'postgres' -or ($dataDir -ne $expected -and $dataDir -ne $expected.Replace('\','/'))) { Remove-Item -LiteralPath $pidFile -Force; Write-Output 'Removed stale postmaster.pid' } } catch { Remove-Item -LiteralPath $pidFile -Force; Write-Output 'Removed stale postmaster.pid' } } }"

powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process -Filter \"Name='postgres.exe'\" | Where-Object { $_.ExecutablePath -and $_.ExecutablePath -like '*\\pgsql18\\pgsql\\bin\\postgres.exe' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

> "%PG_LOG_FILE%" type nul
echo Starting local PostgreSQL on %PG_HOST%:%PG_PORT%...
"%PG_CTL%" -D "pgdata" -l "%PG_LOG_FILE%" -o "-p %PG_PORT%" start >nul

for /L %%I in (1,1,15) do (
    "%PG_ISREADY%" -h %PG_HOST% -p %PG_PORT% -U %PG_USER% -d %PG_DATABASE% >nul 2>nul
    if not errorlevel 1 exit /b 0
    timeout /t 1 /nobreak >nul
)

echo PostgreSQL did not become ready. See %PG_LOG_FILE%.
if exist "%PG_LOG_FILE%" powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Content -LiteralPath '%PG_LOG_FILE%' -Tail 40"
exit /b 1
