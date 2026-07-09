@echo off
setlocal EnableExtensions

set "PROJECT_ROOT=%~dp0.."
if exist "%PROJECT_ROOT%\runtime_env.cmd" call "%PROJECT_ROOT%\runtime_env.cmd"

set "PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" if exist "%PROJECT_ROOT%\payload\python\runtime\python.exe" set "PYTHON_EXE=%PROJECT_ROOT%\payload\python\runtime\python.exe"
set "LOG_FILE=%PROJECT_ROOT%\logs\db_monitor.log"

if "%PG_PASSWORD%"=="" (
    echo [%date% %time%] ERROR: PG_PASSWORD is not configured. >> "%LOG_FILE%"
    echo WARNING: PG_PASSWORD is not configured at %date% %time% > "%PROJECT_ROOT%\logs\alert_db_down.txt"
    exit /b 1
)

"%PYTHON_EXE%" -c "import os, psycopg2; conn = psycopg2.connect(host=os.environ.get('PG_HOST','127.0.0.1'), port=int(os.environ.get('PG_PORT','5432')), database=os.environ.get('PG_DATABASE','wms'), user=os.environ.get('PG_USER','wms_user'), password=os.environ['PG_PASSWORD'], connect_timeout=5); conn.close(); print('OK')" >nul 2>&1

if %ERRORLEVEL% EQU 0 (
    echo [%date% %time%] Database: OK >> "%LOG_FILE%"
) else (
    echo [%date% %time%] ERROR: Database connection failed. >> "%LOG_FILE%"
    echo WARNING: Database connection failed at %date% %time% > "%PROJECT_ROOT%\logs\alert_db_down.txt"
    exit /b 1
)

endlocal
