@echo off
REM ====================================
REM ERP System Health Check
REM ====================================

echo.
echo ========================================
echo    ERP System Health Check
echo ========================================
echo.

set PROJECT_ROOT=%~dp0..
set PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\python.exe

echo Running health check...
echo.

"%PYTHON_EXE%" "%PROJECT_ROOT%\scripts\health_check.py"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo System is healthy!
    echo ========================================
) else (
    echo.
    echo ========================================
    echo Issues found - see recommendations above
    echo ========================================
    echo.
    echo To fix issues, run as administrator:
    echo   scripts\setup_all_operations.cmd
)

echo.
pause
