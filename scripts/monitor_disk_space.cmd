@echo off
REM ====================================
REM 磁盘空间监控脚本 - 每小时检查一次
REM ====================================

setlocal enabledelayedexpansion

set PROJECT_ROOT=%~dp0..
set LOG_FILE=%PROJECT_ROOT%\logs\disk_monitor.log
set ALERT_FILE=%PROJECT_ROOT%\logs\alert_disk_space.txt
set MIN_FREE_GB=5

REM 获取当前驱动器剩余空间（GB）
for /f "tokens=3" %%a in ('dir /-c "%PROJECT_ROOT%" ^| find "bytes free"') do set FREE_BYTES=%%a
set FREE_BYTES=%FREE_BYTES:,=%
set /a FREE_GB=%FREE_BYTES% / 1073741824

echo [%date% %time%] Disk free space: %FREE_GB% GB >> "%LOG_FILE%"

if %FREE_GB% LSS %MIN_FREE_GB% (
    echo [%date% %time%] WARNING: Low disk space! Only %FREE_GB% GB remaining >> "%LOG_FILE%"
    echo WARNING: Low disk space at %date% %time% > "%ALERT_FILE%"
    echo Free space: %FREE_GB% GB >> "%ALERT_FILE%"
    echo Minimum required: %MIN_FREE_GB% GB >> "%ALERT_FILE%"
    exit /b 1
) else (
    echo [%date% %time%] Disk space: OK >> "%LOG_FILE%"
)

endlocal
