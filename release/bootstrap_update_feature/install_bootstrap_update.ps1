param(
    [string]$TargetRoot = "C:\erp"
)

$ErrorActionPreference = "Stop"

function Copy-WithBackup {
    param(
        [string]$Source,
        [string]$Target,
        [string]$BackupRoot,
        [string]$RelativePath
    )

    $targetDir = Split-Path -Parent $Target
    if (-not (Test-Path -LiteralPath $targetDir)) {
        New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
    }

    if (Test-Path -LiteralPath $Target) {
        $backupPath = Join-Path $BackupRoot $RelativePath
        $backupDir = Split-Path -Parent $backupPath
        if (-not (Test-Path -LiteralPath $backupDir)) {
            New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
        }
        Copy-Item -LiteralPath $Target -Destination $backupPath -Force
    }

    Copy-Item -LiteralPath $Source -Destination $Target -Force
}

$packageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$target = Resolve-Path -LiteralPath $TargetRoot
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupRoot = Join-Path $target "backups\bootstrap_update_feature_$stamp"

$files = @(
    "services\update_service.py",
    "services\app_runtime.py",
    "routes\system_management_routes.py",
    "templates\base.html",
    "templates\version_updates.html"
)

Write-Host "Installing ERP version update bootstrap..."
Write-Host "Target: $target"
Write-Host "Backup: $backupRoot"

foreach ($relative in $files) {
    $source = Join-Path $packageRoot $relative
    $destination = Join-Path $target $relative
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Missing package file: $relative"
    }
    Copy-WithBackup -Source $source -Target $destination -BackupRoot $backupRoot -RelativePath $relative
    Write-Host "Updated $relative"
}

$updatesDir = Join-Path $target "updates"
if (-not (Test-Path -LiteralPath $updatesDir)) {
    New-Item -ItemType Directory -Force -Path $updatesDir | Out-Null
    Write-Host "Created updates directory: $updatesDir"
}

$python = Join-Path $target ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $python) {
    Push-Location $target
    try {
        & $python -m py_compile "services\update_service.py" "services\app_runtime.py" "routes\system_management_routes.py"
        if ($LASTEXITCODE -ne 0) {
            throw "Python compile check failed."
        }
        Write-Host "Python compile check passed."
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Warning "Python executable not found at $python; skipped compile check."
}

Write-Host ""
Write-Host "Bootstrap update installed."
Write-Host "Next step: run $TargetRoot\restart_erp.cmd"
Write-Host "Then open: http://127.0.0.1:5000/system/version-updates"
