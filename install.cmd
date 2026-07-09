@echo off
setlocal EnableExtensions
chcp 65001 >nul

cd /d "%~dp0"

if not exist "offline_one_click_install.cmd" (
    echo Missing ERP installer: offline_one_click_install.cmd
    exit /b 1
)

call "%~dp0offline_one_click_install.cmd" %*
exit /b %ERRORLEVEL%
