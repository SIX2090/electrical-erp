@echo off
chcp 65001 >nul
setlocal EnableExtensions

cd /d "%~dp0"

if exist "%~dp0runtime_env.cmd" call "%~dp0runtime_env.cmd"
if "%PG_PASSWORD%"=="" (
    ".venv\Scripts\python.exe" scripts\ensure_local_security_env.py
    if errorlevel 1 (
        echo Failed to prepare local security configuration.
        pause
        exit /b 1
    )
    if exist "%~dp0runtime_env.cmd" call "%~dp0runtime_env.cmd"
)
if "%PORT%"=="" set "PORT=5000"
set "ERP_PORT=%PORT%"

echo Restarting ERP on port %ERP_PORT%...

for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%ERP_PORT% .*LISTENING"') do (
    echo Stopping process %%P on port %ERP_PORT%...
    taskkill /F /PID %%P >nul 2>nul
)

timeout /t 2 /nobreak >nul

start "ERP 5000" /min cmd /c "%~dp0start.cmd"

timeout /t 5 /nobreak >nul

echo.
echo Port status:
netstat -ano | findstr /R /C:":%ERP_PORT% .*LISTENING"
netstat -ano | findstr /R /C:":8080 .*LISTENING"

echo.
echo ERP should be available at http://127.0.0.1:%ERP_PORT%
endlocal
