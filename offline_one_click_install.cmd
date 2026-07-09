@echo off
chcp 65001 >nul
setlocal EnableExtensions

cd /d "%~dp0"
if /I "%~1"=="/?" goto :help
if /I "%~1"=="-h" goto :help
if /I "%~1"=="--help" goto :help
if /I "%~1"=="/audit" goto :audit
if /I "%~1"=="audit" goto :audit
set "INSTALL_NO_PAUSE=0"
if /I "%~1"=="--no-pause" set "INSTALL_NO_PAUSE=1"
if /I "%~1"=="/no-pause" set "INSTALL_NO_PAUSE=1"
set "INSTALL_LOCK_DIR=%CD%\.install_lock"
mkdir "%INSTALL_LOCK_DIR%" >nul 2>nul
if errorlevel 1 (
    echo Another WMS ERP installation appears to be running in this folder.
    echo Close the other installer window and wait for it to finish before running again.
    if not "%INSTALL_NO_PAUSE%"=="1" pause
    exit /b 1
)
set "POSTGRES_STARTED_BY_INSTALLER=0"
for /f %%T in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "INSTALL_LOG_STAMP=%%T"
if "%INSTALL_LOG_STAMP%"=="" set "INSTALL_LOG_STAMP=latest"
if not exist "logs" mkdir logs >nul 2>nul
set "INSTALL_LOG=%CD%\logs\install_%INSTALL_LOG_STAMP%.log"
set "LATEST_INSTALL_LOG=%CD%\install.log"
for /f %%T in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Date -Format yyyy-MM-ddTHH:mm:ssK"') do set "INSTALL_TS=%%T"
if "%INSTALL_TS%"=="" set "INSTALL_TS=unknown"
echo WMS ERP offline install started at %INSTALL_TS% > "%INSTALL_LOG%"
echo WMS ERP offline install started at %INSTALL_TS% > "%LATEST_INSTALL_LOG%" 2>nul

goto :main

:help
echo WMS ERP offline installer
echo.
echo Usage:
echo   offline_one_click_install.cmd
echo   offline_one_click_install.cmd --no-pause
echo   offline_one_click_install.cmd /audit
echo.
echo /audit checks package completeness without creating databases, services, or virtual environments.
exit /b 0

:audit
echo Running WMS ERP installer package audit...
set "AUDIT_PYTHON="
if exist "payload\python\runtime\python.exe" (
    "payload\python\runtime\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)" >nul 2>nul
    if not errorlevel 1 set "AUDIT_PYTHON=%CD%\payload\python\runtime\python.exe"
)
if "%AUDIT_PYTHON%"=="" if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)" >nul 2>nul
    if not errorlevel 1 set "AUDIT_PYTHON=%CD%\.venv\Scripts\python.exe"
)
if "%AUDIT_PYTHON%"=="" (
    py -3.11 -c "import sys" >nul 2>nul
    if not errorlevel 1 set "AUDIT_PYTHON=py -3.11"
)
if "%AUDIT_PYTHON%"=="" (
    where python >nul 2>nul
    if not errorlevel 1 set "AUDIT_PYTHON=python"
)
if "%AUDIT_PYTHON%"=="" (
    call :install_audit_python
    if errorlevel 1 exit /b 1
    set "AUDIT_PYTHON=%CD%\payload\python\runtime\python.exe"
)
%AUDIT_PYTHON% scripts\audit_installer_package.py --deep
exit /b %ERRORLEVEL%

:install_audit_python
if not exist "payload\python\python-3.11.9-amd64.exe" (
    echo Python is required for installer package audit.
    exit /b 1
)
echo Installing bundled Python runtime for package audit...
if not exist "payload\python\runtime" mkdir "payload\python\runtime" >nul 2>nul
"payload\python\python-3.11.9-amd64.exe" /quiet InstallAllUsers=0 TargetDir="%CD%\payload\python\runtime" Include_launcher=0 PrependPath=0 Include_test=0 Include_doc=0 Include_tcltk=0 /log "%CD%\python_audit_install.log" >nul 2>nul
if not exist "payload\python\runtime\python.exe" (
    echo Bundled Python installation failed for package audit.
    exit /b 1
)
exit /b 0

:fail
set "FAILED_CODE=%ERRORLEVEL%"
if "%FAILED_CODE%"=="0" set "FAILED_CODE=1"
echo.
echo Install failed at: %FAILED_STEP%
echo Error code: %FAILED_CODE%
echo Log file: %INSTALL_LOG%
if "%POSTGRES_STARTED_BY_INSTALLER%"=="1" (
    echo Stopping PostgreSQL started by this failed install...
    "pgsql18\pgsql\bin\pg_ctl.exe" -D "pgdata" stop -m fast >> "%INSTALL_LOG%" 2>&1
)
copy /Y "%INSTALL_LOG%" "%LATEST_INSTALL_LOG%" >nul 2>nul
echo.
echo ===== Last log lines =====
powershell -NoProfile -ExecutionPolicy Bypass -Command "if (Test-Path '%INSTALL_LOG%') { Get-Content -LiteralPath '%INSTALL_LOG%' -Tail 80 }"
echo ==========================
echo.
if exist "%INSTALL_LOCK_DIR%" rmdir "%INSTALL_LOCK_DIR%" >nul 2>nul
if not "%INSTALL_NO_PAUSE%"=="1" pause
exit /b %FAILED_CODE%

:main

echo [1/10] Checking package files...
if not exist "postgresql-18.4-1-windows-x64-binaries.zip" (
    echo Missing PostgreSQL package: postgresql-18.4-1-windows-x64-binaries.zip
    set "FAILED_STEP=checking PostgreSQL package"
goto :fail
)
if not exist "vendor\python-wheels" (
    echo Missing offline Python wheels: vendor\python-wheels
    set "FAILED_STEP=checking Python wheels"
goto :fail
)
if not exist "db\wms_current.dump" (
    echo Missing database backup: db\wms_current.dump
    set "FAILED_STEP=checking database backup"
goto :fail
)
if not exist "payload\python\runtime\python.exe" if not exist "payload\python\python-3.11.9-amd64.exe" (
    echo Missing bundled Python runtime or installer under payload\python.
    set "FAILED_STEP=checking bundled Python"
goto :fail
)

echo [2/10] Checking Python...
set "PYTHON_CMD="
set "BUNDLED_PYTHON_DIR=%CD%\payload\python\runtime"
if exist "payload\python\runtime\python.exe" (
    "payload\python\runtime\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=%CD%\payload\python\runtime\python.exe"
)
where python >nul 2>nul
if "%PYTHON_CMD%"=="" if not errorlevel 1 (
    python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=python"
)
if "%PYTHON_CMD%"=="" (
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3.11 -c "import sys" >nul 2>nul
        if not errorlevel 1 set "PYTHON_CMD=py -3.11"
    )
)
if "%PYTHON_CMD%"=="" (
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)" >nul 2>nul
        if not errorlevel 1 set "PYTHON_CMD=py -3"
    )
)
if "%PYTHON_CMD%"=="" (
    echo Installing bundled Python 3.11.9 runtime...
    "payload\python\python-3.11.9-amd64.exe" /quiet InstallAllUsers=0 TargetDir="%BUNDLED_PYTHON_DIR%" Include_launcher=0 PrependPath=0 Include_test=0 Include_doc=0 Include_tcltk=0 /log "%CD%\python_install.log" >> "%INSTALL_LOG%" 2>&1
    if errorlevel 1 (
        echo Bundled Python installation failed.
        set "FAILED_STEP=installing bundled Python"
goto :fail
    )
    if not exist "payload\python\runtime\python.exe" (
        echo Bundled Python installation did not create payload\python\runtime\python.exe.
        if exist "%CD%\python_install.log" type "%CD%\python_install.log" >> "%INSTALL_LOG%"
        set "FAILED_STEP=validating bundled Python runtime"
goto :fail
    )
    "payload\python\runtime\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)" >nul 2>nul
    if errorlevel 1 (
        echo Bundled Python runtime is not Python 3.11.
        set "FAILED_STEP=checking bundled Python version"
goto :fail
    )
    set "PYTHON_CMD=%CD%\payload\python\runtime\python.exe"
)
if "%PYTHON_CMD%"=="" (
    echo Python 3.11 is required because this offline package includes Python 3.11 binary wheels.
    echo If Python is installed, make sure either python.exe or the Python Launcher py.exe is available on PATH.
    set "FAILED_STEP=finding Python 3.11"
goto :fail
)
echo Using Python command: %PYTHON_CMD%

echo [3/10] Running source integrity gate...
%PYTHON_CMD% scripts\source_integrity_audit.py >> "%INSTALL_LOG%" 2>&1
if errorlevel 1 (
    echo Source integrity gate failed. Fix source mojibake or contaminated source files before installation.
    set "FAILED_STEP=source integrity audit"
    goto :fail
)
%PYTHON_CMD% scripts\check_windows_postgres_runtime.py >> "%INSTALL_LOG%" 2>&1
if errorlevel 1 (
    echo Bundled PostgreSQL runtime is not supported on this Windows version.
    set "FAILED_STEP=checking Windows PostgreSQL runtime support"
    goto :fail
)
%PYTHON_CMD% scripts\audit_installer_package.py >> "%INSTALL_LOG%" 2>&1
if errorlevel 1 (
    echo Installer package audit failed.
    set "FAILED_STEP=installer package audit"
    goto :fail
)
%PYTHON_CMD% scripts\check_install_disk_space.py 1200 >> "%INSTALL_LOG%" 2>&1
if errorlevel 1 (
    echo Not enough free disk space for local PostgreSQL restore.
    echo Move this installer folder to a larger local drive, or free at least 1.2 GB, then run again.
    set "FAILED_STEP=checking install disk space"
goto :fail
)

echo [4/10] Creating virtual environment and installing dependencies offline...
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys; print(sys.executable)" >nul 2>nul
    if errorlevel 1 (
        echo Existing virtual environment is not usable in this folder. Recreating .venv...
        echo Existing virtual environment is not usable in this folder. Recreating .venv... >> "%INSTALL_LOG%"
        powershell -NoProfile -ExecutionPolicy Bypass -Command "$target=(Resolve-Path -LiteralPath '.').Path; $venv=Join-Path $target '.venv'; if ((Resolve-Path -LiteralPath $venv -ErrorAction SilentlyContinue).Path -eq (Join-Path $target '.venv')) { Remove-Item -LiteralPath $venv -Recurse -Force }" >> "%INSTALL_LOG%" 2>&1
        if errorlevel 1 (
            echo Failed to remove unusable .venv.
            set "FAILED_STEP=repairing Python virtual environment"
goto :fail
        )
    )
)
if not exist ".venv\Scripts\python.exe" (
    %PYTHON_CMD% -m venv .venv >> "%INSTALL_LOG%" 2>&1
    if errorlevel 1 (
        echo Failed to create .venv.
        set "FAILED_STEP=creating Python virtual environment"
goto :fail
    )
)
".venv\Scripts\python.exe" -c "import sys; print(sys.executable)" >> "%INSTALL_LOG%" 2>&1
if errorlevel 1 (
    echo Python virtual environment is still unusable after repair.
    set "FAILED_STEP=validating Python virtual environment"
goto :fail
)
".venv\Scripts\python.exe" -m pip install --no-index --find-links vendor\python-wheels -r requirements.txt >> "%INSTALL_LOG%" 2>&1
if errorlevel 1 (
    echo Offline Python dependency installation failed.
    set "FAILED_STEP=installing offline Python dependencies"
goto :fail
)

echo [5/10] Extracting PostgreSQL...
if exist "pgsql18" if not exist "pgsql18\pgsql\bin\pg_ctl.exe" (
    echo Existing PostgreSQL extraction is incomplete. Re-extracting...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Remove-Item -LiteralPath 'pgsql18' -Recurse -Force" >> "%INSTALL_LOG%" 2>&1
    if errorlevel 1 (
        echo Failed to remove incomplete PostgreSQL extraction.
        set "FAILED_STEP=cleaning incomplete PostgreSQL extraction"
goto :fail
    )
)
if not exist "pgsql18\pgsql\bin\pg_ctl.exe" (
    %PYTHON_CMD% scripts\extract_postgres_runtime.py postgresql-18.4-1-windows-x64-binaries.zip pgsql18 >> "%INSTALL_LOG%" 2>&1
    if errorlevel 1 (
        echo Failed to extract PostgreSQL zip.
        set "FAILED_STEP=extracting PostgreSQL"
goto :fail
    )
)
if not exist "pgsql18\pgsql\bin\initdb.exe" (
    echo PostgreSQL runtime extraction is missing initdb.exe.
    set "FAILED_STEP=validating PostgreSQL runtime extraction"
goto :fail
)
if not exist "pgsql18\pgsql\bin\pg_restore.exe" (
    echo PostgreSQL runtime extraction is missing pg_restore.exe.
    set "FAILED_STEP=validating PostgreSQL runtime extraction"
goto :fail
)

echo [6/10] Preparing runtime configuration...
if exist runtime_env.cmd call runtime_env.cmd
if "%PG_PASSWORD%"=="" (
    ".venv\Scripts\python.exe" scripts\ensure_local_security_env.py >> "%INSTALL_LOG%" 2>&1
    if errorlevel 1 (
        echo Failed to prepare runtime secrets.
        set "FAILED_STEP=preparing runtime secrets"
goto :fail
    )
    call runtime_env.cmd
)
if "%PG_HOST%"=="" set "PG_HOST=127.0.0.1"
if "%PG_PORT%"=="" set "PG_PORT=5432"
if "%PG_DATABASE%"=="" set "PG_DATABASE=wms"
if "%PG_USER%"=="" set "PG_USER=wms_user"
if "%PORT%"=="" set "PORT=5000"
set "POSTGRES_ALREADY_RUNNING=0"

echo Checking PostgreSQL port %PG_PORT%...
"pgsql18\pgsql\bin\pg_isready.exe" -h %PG_HOST% -p %PG_PORT% >nul 2>> "%INSTALL_LOG%"
if not errorlevel 1 (
    echo PostgreSQL is already accepting connections on port %PG_PORT%.
    set "POSTGRES_ALREADY_RUNNING=1"
)
netstat -ano | findstr /R /C:":%PG_PORT% .*LISTENING" >nul
if not errorlevel 1 if not "%POSTGRES_ALREADY_RUNNING%"=="1" (
    if exist "pgdata\postmaster.pid" (
        echo PostgreSQL port %PG_PORT% is already running for this local data directory.
        set "POSTGRES_ALREADY_RUNNING=1"
    ) else (
        echo PostgreSQL port %PG_PORT% is already in use. Trying fallback port 55432.
        set "PG_PORT=55432"
    )
)
if not "%POSTGRES_ALREADY_RUNNING%"=="1" (
    netstat -ano | findstr /R /C:":%PG_PORT% .*LISTENING" >nul
    if not errorlevel 1 (
        echo PostgreSQL fallback port %PG_PORT% is also in use.
        set "FAILED_STEP=finding available PostgreSQL port"
        goto :fail
    )
)
if exist runtime_env.cmd call :write_runtime_pg_port

echo [7/10] Initializing and starting PostgreSQL...
if not exist "pgdata\PG_VERSION" (
    if exist "pgdata" (
        echo Existing pgdata directory is incomplete. Removing it before PostgreSQL initdb... >> "%INSTALL_LOG%" 2>&1
        powershell -NoProfile -ExecutionPolicy Bypass -Command "$target=(Resolve-Path -LiteralPath '.').Path; $pg=Join-Path $target 'pgdata'; $resolved=(Resolve-Path -LiteralPath $pg -ErrorAction SilentlyContinue).Path; if ($resolved -and $resolved -eq (Join-Path $target 'pgdata')) { Remove-Item -LiteralPath $resolved -Recurse -Force }" >> "%INSTALL_LOG%" 2>&1
        if errorlevel 1 (
            echo Failed to remove incomplete pgdata directory.
            echo Close any process using this folder, or manually remove pgdata, then run the installer again.
            set "FAILED_STEP=cleaning incomplete PostgreSQL data directory"
goto :fail
        )
    )
    "pgsql18\pgsql\bin\initdb.exe" -D "pgdata" -U postgres --encoding=UTF8 --locale=C >> "%INSTALL_LOG%" 2>&1
    if errorlevel 1 (
        echo PostgreSQL initdb failed.
        set "FAILED_STEP=initializing PostgreSQL data directory"
goto :fail
    )
)
if not "%POSTGRES_ALREADY_RUNNING%"=="1" (
    echo Starting bundled PostgreSQL on port %PG_PORT%... >> "%INSTALL_LOG%" 2>&1
    "pgsql18\pgsql\bin\pg_ctl.exe" -D "pgdata" -l "postgres.log" -o "-p %PG_PORT%" start > "%TEMP%\wms_pg_ctl_start_%INSTALL_LOG_STAMP%.log" 2>&1
    set "POSTGRES_STARTED_BY_INSTALLER=1"
    if errorlevel 1 (
        echo PostgreSQL start returned a warning or non-zero status. Verifying readiness...
        if exist "%TEMP%\wms_pg_ctl_start_%INSTALL_LOG_STAMP%.log" type "%TEMP%\wms_pg_ctl_start_%INSTALL_LOG_STAMP%.log" >> "%INSTALL_LOG%" 2>&1
    )
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 3" >> "%INSTALL_LOG%" 2>&1
for /L %%I in (1,1,10) do (
    "pgsql18\pgsql\bin\pg_isready.exe" -h %PG_HOST% -p %PG_PORT% >> "%INSTALL_LOG%" 2>&1
    if not errorlevel 1 goto :postgres_ready
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 1" >> "%INSTALL_LOG%" 2>&1
)
:postgres_not_ready
echo PostgreSQL did not become ready.
if exist postgres.log type postgres.log >> "%INSTALL_LOG%"
set "FAILED_STEP=starting PostgreSQL"
goto :fail
:postgres_ready

echo [8/10] Creating database and restoring backup...
set "PGPASSWORD=%PG_PASSWORD%"
".venv\Scripts\python.exe" scripts\ensure_local_postgres_database.py >> "%INSTALL_LOG%" 2>&1
if errorlevel 1 (
    set "FAILED_STEP=creating PostgreSQL user/database"
    goto :fail
)

set "RESTORE_DB=0"
if /I "%FORCE_DB_RESTORE%"=="1" set "RESTORE_DB=1"
if "%RESTORE_DB%"=="0" (
    set "TABLE_COUNT=0"
    "pgsql18\pgsql\bin\psql.exe" -h %PG_HOST% -p %PG_PORT% -U %PG_USER% -d %PG_DATABASE% -Atq -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';" > "%TEMP%\wms_table_count.txt" 2>> "%INSTALL_LOG%"
    if errorlevel 1 (
        set "FAILED_STEP=checking target database table count"
        goto :fail
    )
    set /p TABLE_COUNT=<"%TEMP%\wms_table_count.txt"
    del "%TEMP%\wms_table_count.txt" >nul 2>nul
    if "%TABLE_COUNT%"=="" set "TABLE_COUNT=0"
    if "%TABLE_COUNT%"=="0" set "RESTORE_DB=1"
)
if "%RESTORE_DB%"=="0" (
    "pgsql18\pgsql\bin\psql.exe" -h %PG_HOST% -p %PG_PORT% -U %PG_USER% -d %PG_DATABASE% -Atq -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('products','stock_transactions','inventory_balances','purchase_orders','sales_orders','work_orders');" > "%TEMP%\wms_core_table_count.txt" 2>> "%INSTALL_LOG%"
    if errorlevel 1 (
        set "FAILED_STEP=checking target database core tables"
        goto :fail
    )
    set "CORE_TABLE_COUNT=0"
    set /p CORE_TABLE_COUNT=<"%TEMP%\wms_core_table_count.txt"
    del "%TEMP%\wms_core_table_count.txt" >nul 2>nul
    if "%CORE_TABLE_COUNT%"=="" set "CORE_TABLE_COUNT=0"
    if not "%CORE_TABLE_COUNT%"=="6" (
        echo Existing database is missing core ERP tables. Restoring bundled backup.
        set "RESTORE_DB=1"
    )
)
if "%RESTORE_DB%"=="1" (
    echo Recreating target database before restore... >> "%INSTALL_LOG%" 2>&1
    "pgsql18\pgsql\bin\psql.exe" -h %PG_HOST% -p %PG_PORT% -U postgres -d postgres -v ON_ERROR_STOP=1 -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='%PG_DATABASE%' AND pid <> pg_backend_pid();" >> "%INSTALL_LOG%" 2>&1
    if errorlevel 1 (
        echo Failed to terminate existing database sessions.
        set "FAILED_STEP=preparing database restore"
goto :fail
    )
    "pgsql18\pgsql\bin\psql.exe" -h %PG_HOST% -p %PG_PORT% -U postgres -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS %PG_DATABASE%;" >> "%INSTALL_LOG%" 2>&1
    if errorlevel 1 (
        echo Failed to drop existing target database.
        set "FAILED_STEP=preparing database restore"
goto :fail
    )
    "pgsql18\pgsql\bin\psql.exe" -h %PG_HOST% -p %PG_PORT% -U postgres -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE %PG_DATABASE% OWNER %PG_USER% ENCODING 'UTF8';" >> "%INSTALL_LOG%" 2>&1
    if errorlevel 1 (
        echo Failed to create target database.
        set "FAILED_STEP=preparing database restore"
goto :fail
    )
    "pgsql18\pgsql\bin\pg_restore.exe" -h %PG_HOST% -p %PG_PORT% -U %PG_USER% -d %PG_DATABASE% --no-owner "db\wms_current.dump" >> "%INSTALL_LOG%" 2>&1
    if errorlevel 1 (
        echo Database restore reported warnings or non-zero status. Verifying restored core tables...
        "pgsql18\pgsql\bin\psql.exe" -h %PG_HOST% -p %PG_PORT% -U %PG_USER% -d %PG_DATABASE% -Atq -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('products','stock_transactions','inventory_balances','purchase_orders','sales_orders','work_orders');" > "%TEMP%\wms_core_table_restore_count.txt" 2>> "%INSTALL_LOG%"
        if errorlevel 1 (
            echo Database restore failed.
            set "FAILED_STEP=restoring database backup"
goto :fail
        )
        set "RESTORE_CORE_TABLE_COUNT=0"
        set /p RESTORE_CORE_TABLE_COUNT=<"%TEMP%\wms_core_table_restore_count.txt"
        del "%TEMP%\wms_core_table_restore_count.txt" >nul 2>nul
        if "%RESTORE_CORE_TABLE_COUNT%"=="" set "RESTORE_CORE_TABLE_COUNT=0"
        if not "%RESTORE_CORE_TABLE_COUNT%"=="6" (
            echo Database restore failed.
            set "FAILED_STEP=restoring database backup"
goto :fail
        )
        echo Database restore completed with non-fatal warnings; core ERP tables are present.
    )
) else (
    echo Existing database is not empty. Skipping restore.
    echo Set FORCE_DB_RESTORE=1 before running this installer if you intentionally want to overwrite local data.
)

echo [9/10] Verifying ERP source...
".venv\Scripts\python.exe" -m compileall app.py services routes scripts waitress_server.py >> "%INSTALL_LOG%" 2>&1
if errorlevel 1 (
    echo Python compile check failed.
    set "FAILED_STEP=compiling ERP source"
goto :fail
)

echo [10/10] Running ERP prelaunch audit and starting ERP...
set "INSTALLER_PRELAUNCH=1"
".venv\Scripts\python.exe" scripts\erp_prelaunch_audit.py >> "%INSTALL_LOG%" 2>&1
if errorlevel 1 (
    echo ERP prelaunch audit failed.
    set "FAILED_STEP=ERP prelaunch audit"
goto :fail
)
start "WMS ERP" cmd /k ""%~dp0start.cmd""

echo.
echo Install finished.
echo ERP: http://127.0.0.1:%PORT%
copy /Y "%INSTALL_LOG%" "%LATEST_INSTALL_LOG%" >nul 2>nul
if exist "%INSTALL_LOCK_DIR%" rmdir "%INSTALL_LOCK_DIR%" >nul 2>nul
if not "%INSTALL_NO_PAUSE%"=="1" pause
endlocal
exit /b 0


goto :eof

:write_runtime_pg_port
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p='runtime_env.cmd'; $s=Get-Content -Raw -LiteralPath $p; if ($s -match 'set \"PG_PORT=') { $s=$s -replace 'set \"PG_PORT=[0-9]+\"','set \"PG_PORT=%PG_PORT%\"' } else { $s += \"`r`nset \"\"PG_PORT=%PG_PORT%\"\"`r`n\" }; Set-Content -LiteralPath $p -Value $s -Encoding ASCII" >> "%INSTALL_LOG%" 2>&1
exit /b %ERRORLEVEL%
