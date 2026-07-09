@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"

echo ========================================
echo ERP local start
echo ========================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: .venv\Scripts\python.exe not found.
    pause
    exit /b 1
)

set "PG_HOST=127.0.0.1"
set "PG_PORT=5432"
set "PG_DATABASE=wms"
set "PG_USER=wms_user"
set "PG_PASSWORD=admin"
set "ERP_HOST=127.0.0.1"
set "PORT=5000"

echo [1/3] Starting PostgreSQL if local data directory exists...
if exist "pgsql18\pgsql\bin\pg_ctl.exe" (
    if exist "pgdata\PG_VERSION" (
        pgsql18\pgsql\bin\pg_ctl.exe -D pgdata -l postgres_new.log start >nul 2>nul
        timeout /t 3 /nobreak >nul
    )
)

echo [2/3] Runtime configuration
echo   PG_HOST=%PG_HOST%
echo   PG_PORT=%PG_PORT%
echo   PG_DATABASE=%PG_DATABASE%
echo   PG_USER=%PG_USER%
echo   PG_PASSWORD=admin
echo   URL=http://127.0.0.1:%PORT%
echo.

echo [3/3] Starting ERP with Waitress...
echo Press Ctrl+C to stop.
echo.

.venv\Scripts\python.exe waitress_server.py

pause
