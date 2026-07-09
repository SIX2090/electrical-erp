@echo off
cd /d "%~dp0"
"%~dp0pgsql18\pgsql\bin\pg_ctl.exe" -D "%~dp0pgdata" -l "%~dp0postgres_runtime.log" -o "-p 5432" start
