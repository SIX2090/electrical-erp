@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title ERP 腾讯云服务器部署 - Windows Server 2012

REM ========================================
REM  ERP系统腾讯云Windows Server 2012部署脚本
REM  适用于：Windows Server 2012 R2及以上版本
REM ========================================

set "DEPLOY_ROOT=%~dp0"
set "DEPLOY_ROOT=%DEPLOY_ROOT:~0,-1%"
set "DEPLOY_LOG=%DEPLOY_ROOT%\deploy_tencent_cloud.log"
set "RECOMMENDED_PATH=C:\erp"

echo ========================================
echo  ERP系统 - 腾讯云服务器部署向导
echo ========================================
echo.
echo 当前安装路径: %DEPLOY_ROOT%
echo 推荐安装路径: %RECOMMENDED_PATH%
echo.

REM 检查管理员权限
fltmc >nul 2>&1
if errorlevel 1 (
    echo [错误] 需要管理员权限！
    echo [错误] 请右键点击此文件，选择"以管理员身份运行"
    echo.
    pause
    exit /b 1
)

echo [OK] 管理员权限验证通过
echo.

REM 初始化日志
echo ======================================== > "%DEPLOY_LOG%"
echo ERP系统腾讯云部署日志 >> "%DEPLOY_LOG%"
echo 开始时间: %DATE% %TIME% >> "%DEPLOY_LOG%"
echo 安装路径: %DEPLOY_ROOT% >> "%DEPLOY_LOG%"
echo ======================================== >> "%DEPLOY_LOG%"
echo. >> "%DEPLOY_LOG%"

REM 步骤1: 检查服务器环境
echo [1/8] 检查服务器环境...
echo [1/8] 检查服务器环境... >> "%DEPLOY_LOG%"

systeminfo | findstr /C:"OS Name" /C:"OS Version" >> "%DEPLOY_LOG%"
systeminfo | findstr /C:"System Type" >> "%DEPLOY_LOG%"

ver | findstr /C:"Windows Server" >nul
if errorlevel 1 (
    echo [警告] 未检测到Windows Server系统
    echo [警告] 建议使用Windows Server 2012 R2或更高版本
    echo [警告] 未检测到Windows Server系统 >> "%DEPLOY_LOG%"
)

REM 检查磁盘空间（至少需要2GB）
for /f "tokens=3" %%a in ('dir "%DEPLOY_ROOT%" ^| findstr /C:"bytes free"') do set FREE_SPACE=%%a
echo 可用磁盘空间: %FREE_SPACE% bytes >> "%DEPLOY_LOG%"

REM 步骤2: 检查防火墙设置
echo [2/8] 检查防火墙配置...
echo [2/8] 检查防火墙配置... >> "%DEPLOY_LOG%"

netsh advfirewall show currentprofile state >> "%DEPLOY_LOG%" 2>&1

echo [提示] 配置防火墙规则（允许ERP应用端口5000和PostgreSQL端口5432）...
echo [提示] 配置防火墙规则... >> "%DEPLOY_LOG%"

netsh advfirewall firewall show rule name="ERP Application" >nul 2>&1
if errorlevel 1 (
    netsh advfirewall firewall add rule name="ERP Application" dir=in action=allow protocol=TCP localport=5000 >> "%DEPLOY_LOG%" 2>&1
    if not errorlevel 1 (
        echo [OK] 已添加ERP应用端口5000防火墙规则
    ) else (
        echo [警告] 防火墙规则添加失败，可能需要手动配置
    )
) else (
    echo [OK] ERP应用防火墙规则已存在
)

netsh advfirewall firewall show rule name="ERP PostgreSQL" >nul 2>&1
if errorlevel 1 (
    netsh advfirewall firewall add rule name="ERP PostgreSQL" dir=in action=allow protocol=TCP localport=5432 >> "%DEPLOY_LOG%" 2>&1
    if not errorlevel 1 (
        echo [OK] 已添加PostgreSQL端口5432防火墙规则
    )
) else (
    echo [OK] PostgreSQL防火墙规则已存在
)

REM 步骤3: 检查必需文件
echo [3/8] 验证安装包完整性...
echo [3/8] 验证安装包完整性... >> "%DEPLOY_LOG%"

set "PACKAGE_OK=1"

if not exist "offline_one_click_install.cmd" (
    echo [错误] 缺少主安装脚本: offline_one_click_install.cmd
    echo [错误] 缺少主安装脚本 >> "%DEPLOY_LOG%"
    set "PACKAGE_OK=0"
)

if not exist "postgresql-18.4-1-windows-x64-binaries.zip" (
    echo [错误] 缺少PostgreSQL安装包
    echo [错误] 缺少PostgreSQL安装包 >> "%DEPLOY_LOG%"
    set "PACKAGE_OK=0"
)

if not exist "vendor\python-wheels" (
    echo [错误] 缺少Python依赖包
    echo [错误] 缺少Python依赖包 >> "%DEPLOY_LOG%"
    set "PACKAGE_OK=0"
)

if not exist "db\wms_current.dump" (
    echo [错误] 缺少数据库备份文件
    echo [错误] 缺少数据库备份文件 >> "%DEPLOY_LOG%"
    set "PACKAGE_OK=0"
)

if not exist "app.py" (
    echo [错误] 缺少应用主文件
    echo [错误] 缺少应用主文件 >> "%DEPLOY_LOG%"
    set "PACKAGE_OK=0"
)

if "%PACKAGE_OK%"=="0" (
    echo.
    echo [错误] 安装包不完整，无法继续安装
    echo [错误] 请检查所有文件是否已正确上传到服务器
    echo.
    pause
    exit /b 1
)

echo [OK] 安装包完整性验证通过

REM 步骤4: 清理旧的安装残留
echo [4/8] 清理旧安装残留...
echo [4/8] 清理旧安装残留... >> "%DEPLOY_LOG%"

if exist ".install_lock" (
    echo [提示] 清除安装锁...
    rmdir /s /q ".install_lock" >> "%DEPLOY_LOG%" 2>&1
)

if exist "pgdata" if not exist "pgdata\PG_VERSION" (
    echo [提示] 清除不完整的pgdata目录...
    echo [提示] 清除不完整的pgdata目录... >> "%DEPLOY_LOG%"

    takeown /F "pgdata" /R /D Y >> "%DEPLOY_LOG%" 2>&1
    icacls "pgdata" /grant Administrators:F /T /C >> "%DEPLOY_LOG%" 2>&1
    attrib -R -S -H "pgdata" /S /D >> "%DEPLOY_LOG%" 2>&1
    rmdir /s /q "pgdata" >> "%DEPLOY_LOG%" 2>&1

    if exist "pgdata" (
        echo [警告] 无法完全清除pgdata，可能需要重启服务器后再试
        echo [警告] 无法完全清除pgdata >> "%DEPLOY_LOG%"
    )
)

REM 步骤5: 配置运行环境变量
echo [5/8] 配置生产环境参数...
echo [5/8] 配置生产环境参数... >> "%DEPLOY_LOG%"

if not exist ".env" (
    echo [提示] 创建生产环境配置文件...
    copy /Y ".env.example" ".env" >nul 2>&1

    REM 获取服务器内网IP
    for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /C:"IPv4"') do (
        set SERVER_IP=%%a
        set SERVER_IP=!SERVER_IP: =!
        goto :got_ip
    )
    :got_ip

    if not "!SERVER_IP!"=="" (
        echo [OK] 检测到服务器IP: !SERVER_IP!
        echo 检测到服务器IP: !SERVER_IP! >> "%DEPLOY_LOG%"

        REM 更新.env配置为生产环境
        powershell -NoProfile -ExecutionPolicy Bypass -Command "$env=Get-Content '.env'; $env=$env -replace 'FLASK_RUN_HOST=127.0.0.1','FLASK_RUN_HOST=0.0.0.0'; $env=$env -replace 'FLASK_DEBUG=1','FLASK_DEBUG=0'; $env=$env -replace 'FLASK_ENV=development','FLASK_ENV=production'; Set-Content '.env' $env" >> "%DEPLOY_LOG%" 2>&1

        echo [OK] 已配置为生产环境（监听所有IP）
    )
) else (
    echo [OK] .env配置文件已存在
)

REM 步骤6: 运行主安装程序
echo [6/8] 运行主安装程序（这可能需要几分钟）...
echo [6/8] 运行主安装程序... >> "%DEPLOY_LOG%"
echo.

call "offline_one_click_install.cmd" --no-pause
set "INSTALL_RESULT=%ERRORLEVEL%"

echo. >> "%DEPLOY_LOG%"
echo 主安装程序退出码: %INSTALL_RESULT% >> "%DEPLOY_LOG%"

if not "%INSTALL_RESULT%"=="0" (
    echo.
    echo [错误] 安装失败！退出码: %INSTALL_RESULT%
    echo [错误] 请查看日志文件: %DEPLOY_LOG%
    echo [错误] 以及 install.log 文件获取详细信息
    echo.

    if exist "install.log" (
        echo ========== 安装日志摘要 ==========
        powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Content 'install.log' -Tail 50"
        echo ==================================
    )

    pause
    exit /b %INSTALL_RESULT%
)

echo [OK] 主安装程序执行成功

REM 步骤7: 创建Windows服务（可选）
echo [7/8] 配置系统服务...
echo [7/8] 配置系统服务... >> "%DEPLOY_LOG%"

REM 检查是否已有ERP服务
sc query "WMSERP" >nul 2>&1
if not errorlevel 1 (
    echo [提示] ERP服务已存在，跳过创建
    echo [提示] ERP服务已存在 >> "%DEPLOY_LOG%"
) else (
    echo [提示] 如需配置为Windows服务，请参考文档手动配置
    echo [提示] 或使用NSSM工具将ERP配置为系统服务
    echo [提示] 建议配置为Windows服务以实现开机自启 >> "%DEPLOY_LOG%"
)

REM 步骤8: 生成快速启动脚本
echo [8/8] 生成快速操作脚本...
echo [8/8] 生成快速操作脚本... >> "%DEPLOY_LOG%"

REM 创建快速启动脚本
echo @echo off > "启动ERP.bat"
echo cd /d "%DEPLOY_ROOT%" >> "启动ERP.bat"
echo call start.cmd >> "启动ERP.bat"

REM 创建快速停止脚本
echo @echo off > "停止ERP.bat"
echo taskkill /F /IM python.exe /FI "WINDOWTITLE eq WMS ERP*" 2^>nul >> "停止ERP.bat"
echo taskkill /F /IM postgres.exe 2^>nul >> "停止ERP.bat"
echo echo ERP已停止 >> "停止ERP.bat"
echo pause >> "停止ERP.bat"

REM 创建查看日志脚本
echo @echo off > "查看日志.bat"
echo cd /d "%DEPLOY_ROOT%" >> "查看日志.bat"
echo if exist postgres.log type postgres.log >> "查看日志.bat"
echo echo. >> "查看日志.bat"
echo if exist install.log type install.log >> "查看日志.bat"
echo pause >> "查看日志.bat"

echo [OK] 已创建快速操作脚本

REM 完成部署
echo.
echo ========================================
echo  部署完成！
echo ========================================
echo.
echo 安装路径: %DEPLOY_ROOT%
echo.
echo 访问方式:
echo   - 本地访问: http://localhost:5000
echo   - 内网访问: http://服务器内网IP:5000
echo   - 公网访问: http://服务器公网IP:5000
echo.
echo 重要提示:
echo   1. 请在腾讯云控制台的安全组中开放5000端口
echo   2. 默认管理员账号请查看初始化文档
echo   3. 生产环境请修改.env中的SECRET_KEY和数据库密码
echo   4. 建议配置SSL证书以启用HTTPS访问
echo.
echo 快速操作:
echo   - 启动ERP: 双击"启动ERP.bat"
echo   - 停止ERP: 双击"停止ERP.bat"
echo   - 查看日志: 双击"查看日志.bat"
echo.
echo 详细日志: %DEPLOY_LOG%
echo.

REM 询问是否立即打开浏览器
echo 是否立即在浏览器中打开ERP系统？(Y/N)
set /p OPEN_BROWSER=请选择:

if /I "%OPEN_BROWSER%"=="Y" (
    echo [提示] 正在打开浏览器...
    start http://localhost:5000
)

echo.
echo 部署完成时间: %DATE% %TIME% >> "%DEPLOY_LOG%"
echo.
pause

endlocal
exit /b 0
