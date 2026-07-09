# ERP 正确的部署包生成器
# 不包含虚拟环境，包含wheels用于重新创建

$SourceDir = "U:\erp"
$BuildDir = "C:\erp_deploy_final"
$OutputFile = "C:\ERP_Installers\ERP_Production_Deploy_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".zip"

Write-Host "Building production deployment package..." -ForegroundColor Cyan
Write-Host ""

# Clean build dir
if (Test-Path $BuildDir) { Remove-Item -Path $BuildDir -Recurse -Force }
New-Item -ItemType Directory -Path $BuildDir -Force | Out-Null

# Copy PostgreSQL binaries and data
Write-Host "Copying PostgreSQL..." -ForegroundColor Gray
Copy-Item -Path "$SourceDir\pgsql18" -Destination "$BuildDir\pgsql18" -Recurse -Force
Copy-Item -Path "$SourceDir\pgdata" -Destination "$BuildDir\pgdata" -Recurse -Force

# Copy Python wheels for offline installation
Write-Host "Copying Python dependencies..." -ForegroundColor Gray
New-Item -ItemType Directory -Path "$BuildDir\vendor\wheels" -Force | Out-Null
Copy-Item -Path "$SourceDir\vendor\python-wheels\*" -Destination "$BuildDir\vendor\wheels\" -Force

# Copy application
Write-Host "Copying application code..." -ForegroundColor Gray
$appDirs = @("routes", "services", "templates", "static", "alembic", "migrations", "scripts", "docs")
foreach ($dir in $appDirs) {
    if (Test-Path "$SourceDir\$dir") {
        Copy-Item -Path "$SourceDir\$dir" -Destination "$BuildDir\$dir" -Recurse -Force
    }
}

# Copy core files
$coreFiles = @("app.py", "config.py", "requirements.txt", "alembic.ini", ".env", ".env.example")
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

# Create installation script
Write-Host "Creating installation script..." -ForegroundColor Gray
$installScript = @'
@echo off
chcp 65001 >nul
title ERP 系统首次安装

cd /d "%~dp0"

echo ============================================================
echo   ERP 系统安装程序
echo ============================================================
echo.

:: Check Python
where python >nul 2>&1
if errorlevel 1 (
    echo 错误: 系统未安装Python
    echo 请先安装Python 3.11: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/3] 创建Python虚拟环境...
if not exist ".venv" (
    python -m venv .venv
    echo   ✓ 虚拟环境创建完成
) else (
    echo   虚拟环境已存在
)

echo [2/3] 安装Python依赖（从本地）...
.venv\Scripts\pip.exe install --no-index --find-links=vendor\wheels -r requirements.txt
if errorlevel 1 (
    echo   × 依赖安装失败
    pause
    exit /b 1
)
echo   ✓ 依赖安装完成

echo [3/3] 检查PostgreSQL...
pgsql18\pgsql\bin\pg_ctl.exe -D pgdata status >nul 2>&1
if errorlevel 1 (
    echo PostgreSQL未运行，正在启动...
    pgsql18\pgsql\bin\pg_ctl.exe -D pgdata -l postgres.log start
    timeout /t 3 /nobreak >nul
)
echo   ✓ PostgreSQL已启动

echo.
echo ============================================================
echo   安装完成！
echo ============================================================
echo.
echo 运行 start.bat 启动ERP系统
pause
'@

Set-Content -Path "$BuildDir\install.bat" -Value $installScript -Encoding ASCII

# Create start script
$startScript = @'
@echo off
chcp 65001 >nul
title ERP 系统

cd /d "%~dp0"

:: Start PostgreSQL if needed
pgsql18\pgsql\bin\pg_ctl.exe -D pgdata status >nul 2>&1
if errorlevel 1 (
    echo 启动PostgreSQL...
    pgsql18\pgsql\bin\pg_ctl.exe -D pgdata -l postgres.log start
    timeout /t 3 /nobreak >nul
)

echo 启动ERP系统...
echo 访问: http://localhost:5000
echo.

.venv\Scripts\python.exe -m waitress --host=0.0.0.0 --port=5000 app:app
pause
'@

Set-Content -Path "$BuildDir\start.bat" -Value $startScript -Encoding ASCII

# Create README
$readme = @"
# ERP生产部署包

## 内容
- PostgreSQL 18.4 (含数据)
- Python依赖包 (离线安装)
- ERP应用程序完整代码

## 部署步骤

1. 解压到目标目录 (例如 C:\erp)

2. 确保系统已安装Python 3.11
   下载: https://www.python.org/downloads/

3. 运行 install.bat (首次安装)
   会自动创建虚拟环境并安装依赖

4. 运行 start.bat 启动系统

5. 访问 http://localhost:5000

## 注意
- 首次运行需要执行 install.bat
- 之后直接运行 start.bat 即可
- 数据库数据已包含在 pgdata 目录
"@

Set-Content -Path "$BuildDir\README.txt" -Value $readme -Encoding UTF8

# Compress
Write-Host ""
Write-Host "Compressing..." -ForegroundColor Yellow
Compress-Archive -Path "$BuildDir\*" -DestinationPath $OutputFile -CompressionLevel Optimal

if (Test-Path $OutputFile) {
    $size = [math]::Round((Get-Item $OutputFile).Length / 1MB, 2)
    Write-Host ""
    Write-Host "OK - Package created: $size MB" -ForegroundColor Green
    Write-Host "Location: $OutputFile" -ForegroundColor Green

    Remove-Item -Path $BuildDir -Recurse -Force
} else {
    Write-Host "FAIL" -ForegroundColor Red
}
