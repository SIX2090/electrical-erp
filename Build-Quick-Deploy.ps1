# ERP Quick Deployment Package Builder
# Only pack what's needed for deployment

$ErrorActionPreference = "Stop"

$SourceDir = "U:\erp"
$BuildDir = "C:\erp_deploy_temp"
$OutputFile = "C:\ERP_Installers\ERP_Deploy_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".zip"

Write-Host "Creating deployment package (essentials only)..." -ForegroundColor Cyan
Write-Host ""

# Clean and create build dir
if (Test-Path $BuildDir) { Remove-Item -Path $BuildDir -Recurse -Force }
New-Item -ItemType Directory -Path $BuildDir -Force | Out-Null

# Copy essential directories
Write-Host "Copying PostgreSQL..." -ForegroundColor Gray
Copy-Item -Path "$SourceDir\pgsql18" -Destination "$BuildDir\pgsql18" -Recurse -Force

Write-Host "Copying database data..." -ForegroundColor Gray
Copy-Item -Path "$SourceDir\pgdata" -Destination "$BuildDir\pgdata" -Recurse -Force

Write-Host "Copying Python venv..." -ForegroundColor Gray
Copy-Item -Path "$SourceDir\.venv" -Destination "$BuildDir\.venv" -Recurse -Force

Write-Host "Copying application code..." -ForegroundColor Gray
$appDirs = @("routes", "services", "templates", "static", "alembic", "migrations", "scripts", "docs")
foreach ($dir in $appDirs) {
    if (Test-Path "$SourceDir\$dir") {
        Copy-Item -Path "$SourceDir\$dir" -Destination "$BuildDir\$dir" -Recurse -Force
    }
}

Write-Host "Copying core files..." -ForegroundColor Gray
$coreFiles = @("app.py", "config.py", "requirements.txt", "alembic.ini", ".env", ".env.example", "start.bat", "restart_erp.cmd")
foreach ($file in $coreFiles) {
    if (Test-Path "$SourceDir\$file") {
        Copy-Item -Path "$SourceDir\$file" -Destination "$BuildDir\" -Force
    }
}

# Create empty dirs
$emptyDirs = @("logs", "backups", "reports")
foreach ($dir in $emptyDirs) {
    New-Item -ItemType Directory -Path "$BuildDir\$dir" -Force | Out-Null
}

Write-Host ""
Write-Host "Compressing package..." -ForegroundColor Yellow
Compress-Archive -Path "$BuildDir\*" -DestinationPath $OutputFile -CompressionLevel Optimal

if (Test-Path $OutputFile) {
    $size = [math]::Round((Get-Item $OutputFile).Length / 1MB, 2)
    Write-Host "OK - Package created: $size MB" -ForegroundColor Green
    Write-Host "Location: $OutputFile" -ForegroundColor Green

    # Cleanup
    Remove-Item -Path $BuildDir -Recurse -Force
} else {
    Write-Host "FAIL" -ForegroundColor Red
}
