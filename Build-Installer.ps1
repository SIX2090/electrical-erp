# ERP Windows Offline Installer Builder
# PowerShell Script

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  ERP Windows Offline Installer Builder" -ForegroundColor Cyan
Write-Host "  Target: Windows Server 2012+" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check admin privileges
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "WARNING: Recommended to run as Administrator" -ForegroundColor Yellow
    Write-Host ""
}

# Set variables
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$SourceDir = $PSScriptRoot
$BuildDir = "C:\erp_installer_build_$Timestamp"
$OutputDir = "C:\ERP_Installers"
$InstallerName = "ERP_Windows_Installer_$Timestamp"

Write-Host "Source Directory: $SourceDir" -ForegroundColor Gray
Write-Host "Build Directory: $BuildDir" -ForegroundColor Gray
Write-Host "Output Directory: $OutputDir" -ForegroundColor Gray
Write-Host ""

# Create build directories
Write-Host "[Step 1/6] Creating build directories..." -ForegroundColor Green
if (Test-Path $BuildDir) {
    Write-Host "  Cleaning old build directory..." -ForegroundColor Gray
    Remove-Item -Path $BuildDir -Recurse -Force
}
New-Item -ItemType Directory -Path $BuildDir -Force | Out-Null
New-Item -ItemType Directory -Path "$BuildDir\erp" -Force | Out-Null
New-Item -ItemType Directory -Path "$BuildDir\payload" -Force | Out-Null
New-Item -ItemType Directory -Path "$BuildDir\scripts" -Force | Out-Null
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

Write-Host "  OK - Build directories created" -ForegroundColor Green
Write-Host ""

# Copy application files
Write-Host "[Step 2/6] Copying application files..." -ForegroundColor Green
Write-Host "  Copying core files..." -ForegroundColor Gray

# Copy main Python files
$coreFiles = @("app.py", "config.py", "requirements.txt", "alembic.ini", "pytest.ini", ".env.example")
foreach ($file in $coreFiles) {
    $srcFile = Join-Path $SourceDir $file
    if (Test-Path $srcFile) {
        Write-Host "    - $file" -ForegroundColor Gray
        Copy-Item -Path $srcFile -Destination "$BuildDir\erp\" -Force
    }
}

# Copy directories
$coreDirs = @("routes", "services", "templates", "static", "alembic", "migrations", "scripts", "docs")
foreach ($dir in $coreDirs) {
    $srcDir = Join-Path $SourceDir $dir
    if (Test-Path $srcDir) {
        Write-Host "    - $dir\" -ForegroundColor Gray
        Copy-Item -Path $srcDir -Destination "$BuildDir\erp\$dir" -Recurse -Force
    }
}

# Copy documentation
Get-ChildItem -Path $SourceDir -Filter "*.md" | ForEach-Object {
    Copy-Item -Path $_.FullName -Destination "$BuildDir\erp\" -Force
}
Get-ChildItem -Path $SourceDir -Filter "*.txt" | Where-Object { $_.Name -notmatch "PACKAGE_INFO" } | ForEach-Object {
    Copy-Item -Path $_.FullName -Destination "$BuildDir\erp\" -Force
}

# Create empty directories
$emptyDirs = @("logs", "backups", "uploads", "reports")
foreach ($dir in $emptyDirs) {
    New-Item -ItemType Directory -Path "$BuildDir\erp\$dir" -Force | Out-Null
    New-Item -ItemType File -Path "$BuildDir\erp\$dir\.gitkeep" -Force | Out-Null
}

Write-Host "  OK - Application files copied" -ForegroundColor Green
Write-Host ""

# Copy PostgreSQL
Write-Host "[Step 3/6] Copying PostgreSQL..." -ForegroundColor Green
$pgZip = Join-Path $SourceDir "postgresql-18.4-1-windows-x64-binaries.zip"
if (Test-Path $pgZip) {
    Write-Host "  Copying PostgreSQL package..." -ForegroundColor Gray
    Copy-Item -Path $pgZip -Destination "$BuildDir\payload\" -Force
    $pgSize = (Get-Item $pgZip).Length / 1MB
    Write-Host "  OK - PostgreSQL copied ($([math]::Round($pgSize, 2)) MB)" -ForegroundColor Green
} else {
    Write-Host "  WARNING: PostgreSQL package not found" -ForegroundColor Yellow
    Write-Host "  Installation will require network download" -ForegroundColor Yellow
}
Write-Host ""

# Copy Python runtime
Write-Host "[Step 4/6] Copying Python runtime..." -ForegroundColor Green
$pythonExe = Join-Path $SourceDir "payload\python\python-3.11.9-amd64.exe"
if (Test-Path $pythonExe) {
    New-Item -ItemType Directory -Path "$BuildDir\payload\python" -Force | Out-Null
    Write-Host "  Copying Python installer..." -ForegroundColor Gray
    Copy-Item -Path $pythonExe -Destination "$BuildDir\payload\python\" -Force
    Write-Host "  OK - Python installer copied" -ForegroundColor Green
} else {
    Write-Host "  WARNING: Python installer not found" -ForegroundColor Yellow
    Write-Host "  Installation will require network download" -ForegroundColor Yellow
}
Write-Host ""

# Copy Python dependencies
$wheelsDir = Join-Path $SourceDir "vendor\python-wheels"
$wheelsDir2 = Join-Path $SourceDir "vendor\wheels"

if (Test-Path $wheelsDir) {
    Write-Host "  Copying Python dependencies (python-wheels)..." -ForegroundColor Gray
    New-Item -ItemType Directory -Path "$BuildDir\vendor" -Force | Out-Null
    Copy-Item -Path $wheelsDir -Destination "$BuildDir\vendor\wheels" -Recurse -Force
    $wheelCount = (Get-ChildItem -Path $wheelsDir -File).Count
    $wheelSize = [math]::Round(((Get-ChildItem -Path $wheelsDir -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB), 2)
    Write-Host "  OK - Python dependencies copied ($wheelCount files, $wheelSize MB)" -ForegroundColor Green
} elseif (Test-Path $wheelsDir2) {
    Write-Host "  Copying Python dependencies (wheels)..." -ForegroundColor Gray
    New-Item -ItemType Directory -Path "$BuildDir\vendor" -Force | Out-Null
    Copy-Item -Path $wheelsDir2 -Destination "$BuildDir\vendor\wheels" -Recurse -Force
    $wheelCount = (Get-ChildItem -Path $wheelsDir2 -File).Count
    $wheelSize = [math]::Round(((Get-ChildItem -Path $wheelsDir2 -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB), 2)
    Write-Host "  OK - Python dependencies copied ($wheelCount files, $wheelSize MB)" -ForegroundColor Green
} else {
    Write-Host "  WARNING: Python dependencies not bundled" -ForegroundColor Yellow
    Write-Host "  Installation will require internet connection" -ForegroundColor Yellow
}
Write-Host ""

# Create installation scripts
Write-Host "[Step 5/6] Creating installation scripts..." -ForegroundColor Green

# Create install.bat
$installBat = @'
@echo off
chcp 65001 >nul
setlocal EnableExtensions

title ERP System Installer

cd /d "%~dp0"

echo.
echo ============================================================
echo   ERP System Windows Server Installer
echo ============================================================
echo.

:: Check admin privileges
net session >nul 2>&1
if errorlevel 1 (
    echo ERROR: Administrator privileges required
    echo Please right-click this file and select "Run as administrator"
    pause
    exit /b 1
)

set "ROOT=%CD%"
set "LOG=%ROOT%\install.log"

echo Installation started... > "%LOG%"
echo Install directory: %ROOT% >> "%LOG%"
echo.

:: Check PostgreSQL
echo [1/5] Checking PostgreSQL...
if exist "pgdata\PG_VERSION" (
    echo   PostgreSQL already installed
) else (
    if exist "payload\postgresql-18.4-1-windows-x64-binaries.zip" (
        echo   Extracting PostgreSQL...
        powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path 'payload\postgresql-18.4-1-windows-x64-binaries.zip' -DestinationPath '.' -Force" >> "%LOG%" 2>&1

        echo   Initializing database...
        "pgsql\bin\initdb.exe" -D "pgdata" -U postgres -E UTF8 --locale=C >> "%LOG%" 2>&1

        if not exist "pgdata\PG_VERSION" (
            echo   ERROR: Database initialization failed
            echo   Check log: %LOG%
            pause
            exit /b 1
        )

        echo   Configuring PostgreSQL...
        echo port = 5432 >> "pgdata\postgresql.conf"
        echo listen_addresses = 'localhost' >> "pgdata\postgresql.conf"

        echo   Starting PostgreSQL...
        "pgsql\bin\pg_ctl.exe" -D "pgdata" -l "postgres.log" start >> "%LOG%" 2>&1
        timeout /t 5 /nobreak >nul

        echo   Creating database...
        "pgsql\bin\createdb.exe" -U postgres wms >> "%LOG%" 2>&1
        "pgsql\bin\psql.exe" -U postgres -d wms -c "CREATE USER wms_user WITH PASSWORD 'admin';" >> "%LOG%" 2>&1
        "pgsql\bin\psql.exe" -U postgres -d wms -c "GRANT ALL PRIVILEGES ON DATABASE wms TO wms_user;" >> "%LOG%" 2>&1

        echo   OK - PostgreSQL installed
    ) else (
        echo   ERROR: PostgreSQL package not found
        pause
        exit /b 1
    )
)
echo.

:: Check Python
echo [2/5] Checking Python...
where python >nul 2>&1
if errorlevel 1 (
    if exist "payload\python\python-3.11.9-amd64.exe" (
        echo   Installing Python...
        "payload\python\python-3.11.9-amd64.exe" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0 >> "%LOG%" 2>&1
        timeout /t 10 /nobreak >nul
        echo   OK - Python installed
    ) else (
        echo   ERROR: Python installer not found
        echo   Download Python 3.11 from https://www.python.org/downloads/
        pause
        exit /b 1
    )
) else (
    echo   Python already installed
)
echo.

:: Create virtual environment
echo [3/5] Creating Python virtual environment...
if not exist ".venv" (
    python -m venv .venv >> "%LOG%" 2>&1
    if errorlevel 1 (
        echo   ERROR: Failed to create virtual environment
        pause
        exit /b 1
    )
    echo   OK - Virtual environment created
) else (
    echo   Virtual environment exists
)
echo.

:: Install dependencies
echo [4/5] Installing Python dependencies...
if exist "vendor\wheels" (
    echo   Installing from local cache...
    ".venv\Scripts\pip.exe" install --no-index --find-links="vendor\wheels" -r "erp\requirements.txt" >> "%LOG%" 2>&1
) else (
    echo   Installing from PyPI...
    ".venv\Scripts\pip.exe" install -r "erp\requirements.txt" >> "%LOG%" 2>&1
)
if errorlevel 1 (
    echo   ERROR: Failed to install dependencies
    echo   Check log: %LOG%
    pause
    exit /b 1
)
echo   OK - Dependencies installed
echo.

:: Configure environment
echo [5/5] Configuring system...
if not exist "erp\.env" (
    copy /Y "erp\.env.example" "erp\.env" >nul
    echo   OK - Environment configuration created
)
echo.

:: Configure firewall
echo Configuring Windows Firewall...
netsh advfirewall firewall add rule name="ERP HTTP" dir=in action=allow protocol=TCP localport=80 >> "%LOG%" 2>&1
netsh advfirewall firewall add rule name="ERP Flask" dir=in action=allow protocol=TCP localport=5000 >> "%LOG%" 2>&1
echo   OK - Firewall rules added
echo.

echo ============================================================
echo   Installation Complete!
echo ============================================================
echo.
echo To start the system:
echo   Double-click start.bat
echo.
echo Access URLs:
echo   Local: http://localhost
echo   Remote: http://%COMPUTERNAME%
echo   Or use server IP address
echo.
echo Default login:
echo   Username: admin
echo   Password: admin
echo.
echo IMPORTANT:
echo   1. Change password after first login
echo   2. Database password is in erp\.env file
echo   3. Setup regular database backups
echo.
pause
exit /b 0
'@

Set-Content -Path "$BuildDir\install.bat" -Value $installBat -Encoding ASCII

# Create start.bat
$startBat = @'
@echo off
chcp 65001 >nul
setlocal EnableExtensions

title ERP System

cd /d "%~dp0"

:: Check PostgreSQL
if not exist "pgsql\bin\pg_ctl.exe" (
    echo ERROR: PostgreSQL not installed
    echo Please run install.bat first
    pause
    exit /b 1
)

:: Check virtual environment
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Python virtual environment not created
    echo Please run install.bat first
    pause
    exit /b 1
)

:: Start PostgreSQL
echo Starting PostgreSQL...
"pgsql\bin\pg_ctl.exe" -D "pgdata" status >nul 2>&1
if errorlevel 1 (
    "pgsql\bin\pg_ctl.exe" -D "pgdata" -l "postgres.log" start
    timeout /t 3 /nobreak >nul
    echo   OK - PostgreSQL started
) else (
    echo   PostgreSQL already running
)

:: Start Flask application
echo Starting ERP system...
echo.
echo Access URL: http://localhost
echo Press Ctrl+C to stop server
echo.

cd erp
"..\\.venv\\Scripts\\python.exe" -m waitress --host=0.0.0.0 --port=5000 app:app

pause
'@

Set-Content -Path "$BuildDir\start.bat" -Value $startBat -Encoding ASCII

# Create README.md
$readme = @"
# ERP System - Windows Server Offline Installer

## System Requirements

- OS: Windows Server 2012 R2 or higher
- RAM: At least 4GB
- Disk: At least 10GB free space
- .NET Framework 4.5 or higher

## Installation Steps

### 1. Extract Package

Extract the installer package to target directory (recommended: C:\erp)

### 2. Run Installer

1. Right-click install.bat
2. Select "Run as administrator"
3. Wait for installation to complete (5-10 minutes)

The installer will automatically:
- Install PostgreSQL database
- Install Python runtime (if needed)
- Create Python virtual environment
- Install Python dependencies
- Configure database and application
- Configure Windows Firewall rules

### 3. Start System

Double-click start.bat to start the ERP system

### 4. Access System

Open browser and navigate to:
- Local: http://localhost
- Remote: http://server-ip-address

Default credentials:
- Username: admin
- Password: admin

**WARNING: Change password after first login!**

## Service Management

### Start Service

Double-click start.bat or run from command line

### Stop Service

Press Ctrl+C in the running window, then enter Y to confirm

### Restart Service

Stop the service first, then run start.bat again

## Configuration File

Main configuration file: erp\.env

Important settings:
- PG_HOST: Database host (default: 127.0.0.1)
- PG_PORT: Database port (default: 5432)
- PG_DATABASE: Database name (default: wms)
- PG_USER: Database user
- PG_PASSWORD: Database password
- INVENTORY_SECRET_KEY: Application secret key (MUST change in production)

Restart service after configuration changes.

## Database Management

### Manual Backup

``````cmd
pgsql18\pgsql\bin\pg_dump.exe -U postgres -d wms -f backup.sql
``````

### Manual Restore

``````cmd
pgsql18\pgsql\bin\psql.exe -U postgres -d wms -f backup.sql
``````

## Troubleshooting

### 1. Cannot Start PostgreSQL

``````cmd
REM Check PostgreSQL status
pgsql18\pgsql\bin\pg_ctl.exe -D pgdata status

REM View PostgreSQL log
type postgres.log
``````

### 2. Cannot Access Web Page

Check port listening:

``````cmd
netstat -ano | findstr ":5000"
``````

### 3. Database Connection Failed

``````cmd
REM Test database connection
pgsql18\pgsql\bin\psql.exe -U wms_user -d wms -h 127.0.0.1
``````

## Security Recommendations

1. **Change Default Password** - Change admin password after first login
2. **Change Database Password** - Update PG_PASSWORD in erp\.env
3. **Change Application Secret Key** - Update INVENTORY_SECRET_KEY in erp\.env
4. **Regular Backups** - Setup automated backup tasks
5. **Restrict Access** - Configure firewall rules appropriately

## Technical Support

Contact technical support if you encounter issues.

---

Package built: $Timestamp
"@

Set-Content -Path "$BuildDir\README.md" -Value $readme -Encoding UTF8

Write-Host "  OK - Installation scripts created" -ForegroundColor Green
Write-Host ""

# Create package
Write-Host "[Step 6/6] Creating package..." -ForegroundColor Green
$zipFile = Join-Path $OutputDir "$InstallerName.zip"
if (Test-Path $zipFile) {
    Remove-Item -Path $zipFile -Force
}

Write-Host "  Compressing files (this may take a few minutes)..." -ForegroundColor Gray
Compress-Archive -Path "$BuildDir\*" -DestinationPath $zipFile -CompressionLevel Optimal

if (Test-Path $zipFile) {
    $fileSize = (Get-Item $zipFile).Length / 1MB
    Write-Host "  OK - Package created" -ForegroundColor Green
    Write-Host ""

    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  Installation Package Generated Successfully!" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Package Location: $zipFile" -ForegroundColor Green
    Write-Host "Package Size: $([math]::Round($fileSize, 2)) MB" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next Steps:" -ForegroundColor Yellow
    Write-Host "1. Copy package to target server" -ForegroundColor Gray
    Write-Host "2. Extract to desired directory (recommended: C:\erp)" -ForegroundColor Gray
    Write-Host "3. Right-click install.bat and select 'Run as administrator'" -ForegroundColor Gray
    Write-Host "4. After installation, access http://localhost" -ForegroundColor Gray
    Write-Host ""

    # Cleanup build directory
    Write-Host "Cleaning up temporary files..." -ForegroundColor Gray
    Remove-Item -Path $BuildDir -Recurse -Force
    Write-Host "Done!" -ForegroundColor Green
    Write-Host ""

} else {
    Write-Host "  ERROR: Package creation failed" -ForegroundColor Red
    Write-Host "  Check available disk space" -ForegroundColor Red
}

Write-Host "Press any key to exit..."
$null = $host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
