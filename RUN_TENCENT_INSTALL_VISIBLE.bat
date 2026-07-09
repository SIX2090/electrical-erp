@echo off
setlocal EnableExtensions
chcp 65001 >nul
title WMS ERP Tencent Cloud Install Visible

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"

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
    pause
    exit /b 1
)

if exist ".install_lock" (
    echo Removing stale install lock...
    rmdir /s /q ".install_lock" >nul 2>nul
)

if exist "pgdata" if not exist "pgdata\PG_VERSION" (
    echo Removing incomplete pgdata from previous failed install...
    takeown /F "pgdata" /R /D Y >nul 2>nul
    icacls "pgdata" /grant Administrators:F /T /C >nul 2>nul
    attrib -R -S -H "pgdata" /S /D >nul 2>nul
    rmdir /s /q "pgdata" >nul 2>nul
)

if not exist "offline_one_click_install.cmd" (
    echo ERROR: Missing offline_one_click_install.cmd.
    pause
    exit /b 1
)

echo Starting installer with visible progress...
echo.
call "offline_one_click_install.cmd"
set "RESULT=%ERRORLEVEL%"

echo.
echo Exit code: %RESULT%
if not "%RESULT%"=="0" (
    echo.
    echo ===== Last install.log lines =====
    if exist "%ROOT%\install.log" type "%ROOT%\install.log"
    echo ================================
)
pause
exit /b %RESULT%
