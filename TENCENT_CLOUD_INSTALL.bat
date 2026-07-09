@echo off
setlocal EnableExtensions
chcp 65001 >nul
title WMS ERP Tencent Cloud Install

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "LOG=%ROOT%\tencent_cloud_install.log"

echo WMS ERP Tencent Cloud Install
echo Folder: %ROOT%
echo.

cd /d "%ROOT%"
if errorlevel 1 (
    echo ERROR: Cannot enter installer folder.
    pause
    exit /b 1
)

fltmc >nul 2>&1
if errorlevel 1 (
    echo ERROR: Please right-click this file and choose Run as administrator.
    echo ERROR: Administrator permission is required.
    pause
    exit /b 1
)

echo Started: %DATE% %TIME% > "%LOG%"
echo Folder: %ROOT% >> "%LOG%"

for %%D in ("%ROOT%") do set "DRIVE=%%~dD"
if /I not "%DRIVE%"=="C:" (
    echo WARNING: Recommended install path is C:\erp.
    echo WARNING: Current path is %ROOT%.
    echo WARNING: Recommended install path is C:\erp. >> "%LOG%"
)

if not exist "offline_one_click_install.cmd" (
    echo ERROR: Missing offline_one_click_install.cmd in this folder.
    echo ERROR: Missing offline_one_click_install.cmd >> "%LOG%"
    pause
    exit /b 1
)

if exist ".install_lock" (
    echo Removing stale install lock...
    echo Removing stale install lock... >> "%LOG%"
    rmdir /s /q ".install_lock" >> "%LOG%" 2>&1
)

if exist "pgdata" if not exist "pgdata\PG_VERSION" (
    echo Removing incomplete pgdata from previous failed install...
    echo Removing incomplete pgdata from previous failed install... >> "%LOG%"
    takeown /F "pgdata" /R /D Y >> "%LOG%" 2>&1
    icacls "pgdata" /grant Administrators:F /T /C >> "%LOG%" 2>&1
    attrib -R -S -H "pgdata" /S /D >> "%LOG%" 2>&1
    rmdir /s /q "pgdata" >> "%LOG%" 2>&1
)

if exist "pgdata" if not exist "pgdata\PG_VERSION" (
    echo ERROR: Could not remove incomplete pgdata.
    echo ERROR: Close all cmd windows and PostgreSQL processes, then run this file again.
    echo ERROR: Could not remove incomplete pgdata >> "%LOG%"
    pause
    exit /b 1
)

echo Running installer...
echo Running installer... >> "%LOG%"
call "offline_one_click_install.cmd"
set "RESULT=%ERRORLEVEL%"

echo.
if not "%RESULT%"=="0" (
    echo ===== Tencent cloud install log tail =====
    if exist "%LOG%" type "%LOG%"
    if exist "%ROOT%\install.log" type "%ROOT%\install.log"
    echo =========================================
)
echo.
echo Log saved to: %LOG%
echo Exit code: %RESULT%
echo.

pause
exit /b %RESULT%
