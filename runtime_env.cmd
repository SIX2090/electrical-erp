@echo off
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
if "%PG_HOST%"=="" set "PG_HOST=127.0.0.1"
if "%PG_PORT%"=="" set "PG_PORT=5432"
if "%PG_DATABASE%"=="" set "PG_DATABASE=wms"
if "%PG_USER%"=="" set "PG_USER=wms_user"
if "%PORT%"=="" set "PORT=5000"
if "%ERP_HOST%"=="" set "ERP_HOST=0.0.0.0"
if "%INVENTORY_ENV%"=="" set "INVENTORY_ENV=production"
if "%INVENTORY_COOKIE_SECURE%"=="" set "INVENTORY_COOKIE_SECURE=0"
if "%INVENTORY_INIT_DB_ON_CREATE%"=="" set "INVENTORY_INIT_DB_ON_CREATE=0"
if exist "%~dp0runtime_local_secrets.cmd" call "%~dp0runtime_local_secrets.cmd"


























