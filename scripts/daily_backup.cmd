@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0.."
set "PROJECT_ROOT=%CD%"
set "PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\python.exe"
set "BACKUP_SCRIPT=%PROJECT_ROOT%\scripts\pg_backup.py"
set "BACKUP_DIR=%PROJECT_ROOT%\backups\daily"

if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

for /f "tokens=2 delims==" %%a in ('wmic OS Get localdatetime /value') do set "dt=%%a"
set "YY=%dt:~0,4%"
set "MM=%dt:~4,2%"
set "DD=%dt:~6,2%"
set "HH=%dt:~8,2%"
set "Min=%dt:~10,2%"
set "Sec=%dt:~12,2%"
set "BACKUP_FILE=%BACKUP_DIR%\backup_%YY%%MM%%DD%_%HH%%Min%%Sec%.dump"

echo [%date% %time%] Starting daily backup...
"%PYTHON_EXE%" "%BACKUP_SCRIPT%" --output "%BACKUP_FILE%"

if %ERRORLEVEL% EQU 0 (
    echo [%date% %time%] Backup completed successfully: %BACKUP_FILE%
    forfiles /P "%BACKUP_DIR%" /M *.dump /D -30 /C "cmd /c del @path" 2>nul
    echo [%date% %time%] Old backups cleaned up
) else (
    echo [%date% %time%] ERROR: Backup failed with code %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)

endlocal
