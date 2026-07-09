@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion

title 生成ERP Windows离线安装包

cd /d "%~dp0"

echo.
echo ============================================================
echo   ERP系统 Windows离线安装包生成器
echo   目标：Windows Server 2012+
echo ============================================================
echo.

:: 检查管理员权限
net session >nul 2>&1
if errorlevel 1 (
    echo 错误：需要管理员权限
    echo 请右键点击此文件，选择"以管理员身份运行"
    pause
    exit /b 1
)

:: 设置变量
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set datetime=%%I
set "TIMESTAMP=%datetime:~0,8%_%datetime:~8,6%"
set "SOURCE_DIR=%CD%"
set "BUILD_DIR=C:\erp_installer_build_%TIMESTAMP%"
set "OUTPUT_DIR=C:\ERP_Installers"
set "INSTALLER_NAME=ERP_Windows_Installer_%TIMESTAMP%"

echo 源目录: %SOURCE_DIR%
echo 构建目录: %BUILD_DIR%
echo 输出目录: %OUTPUT_DIR%
echo.

:: 创建构建目录
echo [步骤 1/6] 创建构建目录...
if exist "%BUILD_DIR%" (
    echo 清理旧的构建目录...
    rmdir /s /q "%BUILD_DIR%"
)
mkdir "%BUILD_DIR%"
mkdir "%BUILD_DIR%\erp"
mkdir "%BUILD_DIR%\payload"
mkdir "%BUILD_DIR%\scripts"
mkdir "%OUTPUT_DIR%" 2>nul

echo   ✓ 构建目录创建完成
echo.

:: 复制应用文件
echo [步骤 2/6] 复制应用文件...
echo   复制核心文件...

:: 复制主要Python文件
for %%F in (app.py config.py requirements.txt alembic.ini pytest.ini .env.example) do (
    if exist "%%F" (
        echo     - %%F
        copy /Y "%%F" "%BUILD_DIR%\erp\" >nul
    )
)

:: 复制目录
for %%D in (routes services templates static alembic migrations scripts docs) do (
    if exist "%%D" (
        echo     - %%D\
        xcopy /E /I /Y /Q "%%D" "%BUILD_DIR%\erp\%%D\" >nul
    )
)

:: 复制文档
for %%F in (*.md *.txt) do (
    if exist "%%F" (
        copy /Y "%%F" "%BUILD_DIR%\erp\" >nul
    )
)

:: 创建必要的空目录
for %%D in (logs backups uploads reports) do (
    mkdir "%BUILD_DIR%\erp\%%D" 2>nul
    type nul > "%BUILD_DIR%\erp\%%D\.gitkeep"
)

echo   ✓ 应用文件复制完成
echo.

:: 复制PostgreSQL
echo [步骤 3/6] 复制PostgreSQL...
if exist "postgresql-18.4-1-windows-x64-binaries.zip" (
    echo   复制PostgreSQL安装包...
    copy /Y "postgresql-18.4-1-windows-x64-binaries.zip" "%BUILD_DIR%\payload\" >nul
    echo   ✓ PostgreSQL复制完成
) else (
    echo   警告：未找到PostgreSQL安装包
    echo   安装时将需要网络下载
)
echo.

:: 复制Python运行时（如果存在）
echo [步骤 4/6] 复制Python运行时...
if exist "payload\python\python-3.11.9-amd64.exe" (
    mkdir "%BUILD_DIR%\payload\python" 2>nul
    echo   复制Python安装包...
    copy /Y "payload\python\python-3.11.9-amd64.exe" "%BUILD_DIR%\payload\python\" >nul
    echo   ✓ Python安装包复制完成
) else (
    echo   警告：未找到Python安装包
    echo   安装时将需要网络下载
)
echo.

:: 复制Python依赖包（如果存在）
if exist "vendor\wheels" (
    echo   复制Python依赖包...
    xcopy /E /I /Y /Q "vendor\wheels" "%BUILD_DIR%\vendor\wheels\" >nul
    echo   ✓ Python依赖包复制完成
) else if exist ".venv" (
    echo   提示：可以预先下载依赖包以加速安装
    echo   运行: pip download -r requirements.txt -d vendor\wheels
)
echo.

:: 创建安装脚本
echo [步骤 5/6] 创建安装脚本...
call :create_install_script
call :create_start_script
call :create_readme
echo   ✓ 安装脚本创建完成
echo.

:: 打包
echo [步骤 6/6] 打包安装文件...
if exist "%OUTPUT_DIR%\%INSTALLER_NAME%.zip" del /f /q "%OUTPUT_DIR%\%INSTALLER_NAME%.zip"

:: 使用PowerShell压缩（Windows内置）
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path '%BUILD_DIR%\*' -DestinationPath '%OUTPUT_DIR%\%INSTALLER_NAME%.zip' -CompressionLevel Optimal"

if exist "%OUTPUT_DIR%\%INSTALLER_NAME%.zip" (
    echo   ✓ 安装包创建完成

    for %%A in ("%OUTPUT_DIR%\%INSTALLER_NAME%.zip") do set "SIZE=%%~zA"
    set /a "SIZE_MB=!SIZE! / 1048576"

    echo.
    echo ============================================================
    echo   ✓ 安装包生成成功！
    echo ============================================================
    echo.
    echo 安装包位置: %OUTPUT_DIR%\%INSTALLER_NAME%.zip
    echo 安装包大小: !SIZE_MB! MB
    echo.
    echo 后续步骤:
    echo 1. 将安装包复制到目标服务器
    echo 2. 解压安装包到任意目录（推荐 C:\erp）
    echo 3. 右键点击 install.bat，选择"以管理员身份运行"
    echo 4. 安装完成后访问 http://localhost
    echo.

    :: 清理构建目录
    echo 清理临时文件...
    rmdir /s /q "%BUILD_DIR%"

    echo 完成！
    echo.

) else (
    echo   × 打包失败
    echo   请检查是否有足够的磁盘空间
)

pause
exit /b 0

:: ============================================================
:: 子程序：创建安装脚本
:: ============================================================
:create_install_script
(
echo @echo off
echo chcp 65001 ^>nul
echo setlocal EnableExtensions
echo.
echo title ERP系统安装程序
echo.
echo cd /d "%%~dp0"
echo.
echo echo.
echo echo ============================================================
echo echo   ERP系统 Windows Server 安装程序
echo echo ============================================================
echo echo.
echo.
echo :: 检查管理员权限
echo net session ^>nul 2^>^&1
echo if errorlevel 1 ^(
echo     echo 错误：需要管理员权限
echo     echo 请右键点击此文件，选择"以管理员身份运行"
echo     pause
echo     exit /b 1
echo ^)
echo.
echo set "ROOT=%%CD%%"
echo set "LOG=%%ROOT%%\install.log"
echo.
echo echo 开始安装... ^> "%%LOG%%"
echo echo 安装目录: %%ROOT%% ^>^> "%%LOG%%"
echo echo.
echo.
echo :: 检查PostgreSQL
echo echo [1/5] 检查PostgreSQL...
echo if exist "pgdata\PG_VERSION" ^(
echo     echo   已安装PostgreSQL
echo ^) else ^(
echo     if exist "payload\postgresql-18.4-1-windows-x64-binaries.zip" ^(
echo         echo   解压PostgreSQL...
echo         powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path 'payload\postgresql-18.4-1-windows-x64-binaries.zip' -DestinationPath '.' -Force" ^>^> "%%LOG%%" 2^>^&1
echo
echo         echo   初始化数据库...
echo         "pgsql18\pgsql\bin\initdb.exe" -D "pgdata" -U postgres -E UTF8 --locale=C ^>^> "%%LOG%%" 2^>^&1
echo
echo         if not exist "pgdata\PG_VERSION" ^(
echo             echo   × 数据库初始化失败
echo             echo   请查看日志: %%LOG%%
echo             pause
echo             exit /b 1
echo         ^)
echo
echo         echo   配置PostgreSQL...
echo         echo port = 5432 ^>^> "pgdata\postgresql.conf"
echo         echo listen_addresses = 'localhost' ^>^> "pgdata\postgresql.conf"
echo         echo max_connections = 100 ^>^> "pgdata\postgresql.conf"
echo
echo         echo   启动PostgreSQL...
echo         "pgsql18\pgsql\bin\pg_ctl.exe" -D "pgdata" -l "postgres.log" start ^>^> "%%LOG%%" 2^>^&1
echo         timeout /t 5 /nobreak ^>nul
echo
echo         echo   创建数据库...
echo         "pgsql18\pgsql\bin\createdb.exe" -U postgres wms ^>^> "%%LOG%%" 2^>^&1
echo         "pgsql18\pgsql\bin\psql.exe" -U postgres -d wms -c "CREATE USER wms_user WITH PASSWORD 'admin';" ^>^> "%%LOG%%" 2^>^&1
echo         "pgsql18\pgsql\bin\psql.exe" -U postgres -d wms -c "GRANT ALL PRIVILEGES ON DATABASE wms TO wms_user;" ^>^> "%%LOG%%" 2^>^&1
echo
echo         echo   ✓ PostgreSQL安装完成
echo     ^) else ^(
echo         echo   × 未找到PostgreSQL安装包
echo         pause
echo         exit /b 1
echo     ^)
echo ^)
echo echo.
echo.
echo :: 检查Python
echo echo [2/5] 检查Python...
echo where python ^>nul 2^>^&1
echo if errorlevel 1 ^(
echo     if exist "payload\python\python-3.11.9-amd64.exe" ^(
echo         echo   安装Python...
echo         "payload\python\python-3.11.9-amd64.exe" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0 ^>^> "%%LOG%%" 2^>^&1
echo         timeout /t 10 /nobreak ^>nul
echo
echo         :: 刷新环境变量
echo         call refreshenv.cmd ^>nul 2^>^&1
echo
echo         echo   ✓ Python安装完成
echo     ^) else ^(
echo         echo   × 未找到Python安装包
echo         echo   请从 https://www.python.org/downloads/ 下载Python 3.11
echo         pause
echo         exit /b 1
echo     ^)
echo ^) else ^(
echo     echo   ✓ Python已安装
echo ^)
echo echo.
echo.
echo :: 创建虚拟环境
echo echo [3/5] 创建Python虚拟环境...
echo if not exist ".venv" ^(
echo     python -m venv .venv ^>^> "%%LOG%%" 2^>^&1
echo     if errorlevel 1 ^(
echo         echo   × 虚拟环境创建失败
echo         pause
echo         exit /b 1
echo     ^)
echo     echo   ✓ 虚拟环境创建完成
echo ^) else ^(
echo     echo   虚拟环境已存在
echo ^)
echo echo.
echo.
echo :: 安装依赖
echo echo [4/5] 安装Python依赖...
echo if exist "vendor\wheels" ^(
echo     echo   从本地安装依赖...
echo     ".venv\Scripts\pip.exe" install --no-index --find-links="vendor\wheels" -r "erp\requirements.txt" ^>^> "%%LOG%%" 2^>^&1
echo ^) else ^(
echo     echo   从网络安装依赖...
echo     ".venv\Scripts\pip.exe" install -r "erp\requirements.txt" ^>^> "%%LOG%%" 2^>^&1
echo ^)
echo if errorlevel 1 ^(
echo     echo   × 依赖安装失败
echo     echo   请查看日志: %%LOG%%
echo     pause
echo     exit /b 1
echo ^)
echo echo   ✓ 依赖安装完成
echo echo.
echo.
echo :: 配置环境
echo echo [5/5] 配置系统...
echo if not exist "erp\.env" ^(
echo     copy /Y "erp\.env.example" "erp\.env" ^>nul
echo     echo   ✓ 环境配置文件创建完成
echo ^)
echo echo.
echo.
echo :: 配置防火墙
echo echo 配置Windows防火墙...
echo netsh advfirewall firewall add rule name="ERP HTTP" dir=in action=allow protocol=TCP localport=80 ^>^> "%%LOG%%" 2^>^&1
echo netsh advfirewall firewall add rule name="ERP Flask" dir=in action=allow protocol=TCP localport=5000 ^>^> "%%LOG%%" 2^>^&1
echo echo   ✓ 防火墙规则添加完成
echo echo.
echo.
echo echo ============================================================
echo echo   ✓ 安装完成！
echo echo ============================================================
echo echo.
echo echo 启动方式:
echo echo   方式1: 双击 start.bat
echo echo   方式2: 在命令行运行 start.bat
echo echo.
echo echo 访问地址:
echo echo   本机访问: http://localhost
echo echo   远程访问: http://%%COMPUTERNAME%%
echo echo   或使用服务器IP地址
echo echo.
echo echo 默认登录:
echo echo   用户名: admin
echo echo   密码: admin
echo echo.
echo echo 重要提示:
echo echo   1. 首次登录后请立即修改密码
echo echo   2. 数据库密码在 erp\.env 文件中
echo echo   3. 建议定期备份数据库
echo echo.
echo pause
echo exit /b 0
) > "%BUILD_DIR%\install.bat"

exit /b 0

:: ============================================================
:: 子程序：创建启动脚本
:: ============================================================
:create_start_script
(
echo @echo off
echo chcp 65001 ^>nul
echo setlocal EnableExtensions
echo.
echo title ERP系统
echo.
echo cd /d "%%~dp0"
echo.
echo :: 检查PostgreSQL
echo if not exist "pgsql18\pgsql\bin\pg_ctl.exe" ^(
echo     echo 错误：PostgreSQL未安装
echo     echo 请先运行 install.bat
echo     pause
echo     exit /b 1
echo ^)
echo.
echo :: 检查虚拟环境
echo if not exist ".venv\Scripts\python.exe" ^(
echo     echo 错误：Python虚拟环境未创建
echo     echo 请先运行 install.bat
echo     pause
echo     exit /b 1
echo ^)
echo.
echo :: 启动PostgreSQL
echo echo 启动PostgreSQL...
echo "pgsql18\pgsql\bin\pg_ctl.exe" -D "pgdata" status ^>nul 2^>^&1
echo if errorlevel 1 ^(
echo     "pgsql18\pgsql\bin\pg_ctl.exe" -D "pgdata" -l "postgres.log" start
echo     timeout /t 3 /nobreak ^>nul
echo     echo   ✓ PostgreSQL已启动
echo ^) else ^(
echo     echo   PostgreSQL已在运行
echo ^)
echo.
echo :: 启动Flask应用
echo echo 启动ERP系统...
echo echo.
echo echo 访问地址: http://localhost
echo echo 按 Ctrl+C 停止服务器
echo echo.
echo.
echo cd erp
echo "..\\.venv\\Scripts\\python.exe" -m waitress --host=0.0.0.0 --port=5000 app:app
echo.
echo pause
) > "%BUILD_DIR%\start.bat"

exit /b 0

:: ============================================================
:: 子程序：创建README
:: ============================================================
:create_readme
(
echo # ERP系统 Windows Server 离线安装包
echo.
echo ## 系统要求
echo.
echo - 操作系统：Windows Server 2012 R2 或更高版本
echo - 内存：至少 4GB RAM
echo - 磁盘：至少 10GB 可用空间
echo - .NET Framework 4.5 或更高版本
echo.
echo ## 安装步骤
echo.
echo ### 1. 解压安装包
echo.
echo 将安装包解压到目标目录，推荐使用 `C:\erp`
echo.
echo ### 2. 运行安装程序
echo.
echo 1. 右键点击 `install.bat`
echo 2. 选择"以管理员身份运行"
echo 3. 等待安装完成（约5-10分钟）
echo.
echo 安装程序会自动完成：
echo - 安装PostgreSQL数据库
echo - 安装Python运行时（如果需要）
echo - 创建Python虚拟环境
echo - 安装Python依赖包
echo - 配置数据库和应用
echo - 配置Windows防火墙规则
echo.
echo ### 3. 启动系统
echo.
echo 双击 `start.bat` 启动ERP系统
echo.
echo ### 4. 访问系统
echo.
echo 在浏览器中访问：
echo - 本机访问：http://localhost
echo - 远程访问：http://服务器IP地址
echo.
echo 默认登录信息：
echo - 用户名：`admin`
echo - 密码：`admin`
echo.
echo **⚠️ 首次登录后请立即修改密码！**
echo.
echo ## 服务管理
echo.
echo ### 启动服务
echo.
echo ```cmd
echo start.bat
echo ```
echo.
echo ### 停止服务
echo.
echo 在运行窗口按 `Ctrl+C`，然后输入 `Y` 确认
echo.
echo ### 重启服务
echo.
echo 先停止服务，然后重新运行 `start.bat`
echo.
echo ## 配置文件
echo.
echo 主配置文件位于：`erp\.env`
echo.
echo 重要配置项：
echo - `PG_HOST`：数据库主机（默认 127.0.0.1）
echo - `PG_PORT`：数据库端口（默认 5432）
echo - `PG_DATABASE`：数据库名（默认 wms）
echo - `PG_USER`：数据库用户
echo - `PG_PASSWORD`：数据库密码
echo - `INVENTORY_SECRET_KEY`：应用密钥（生产环境必须修改）
echo.
echo 修改配置后需要重启服务。
echo.
echo ## 数据库管理
echo.
echo ### 手动备份
echo.
echo ```cmd
echo pgsql18\pgsql\bin\pg_dump.exe -U postgres -d wms -f backup_%%date:~0,4%%%%date:~5,2%%%%date:~8,2%%.sql
echo ```
echo.
echo ### 手动还原
echo.
echo ```cmd
echo pgsql18\pgsql\bin\psql.exe -U postgres -d wms -f backup.sql
echo ```
echo.
echo ### 自动备份
echo.
echo 建议使用Windows任务计划程序创建每日备份任务：
echo.
echo 1. 打开"任务计划程序"
echo 2. 创建基本任务
echo 3. 触发器：每天凌晨2点
echo 4. 操作：启动程序
echo 5. 程序：`C:\erp\scripts\backup_database.bat`
echo.
echo ## 故障排查
echo.
echo ### 1. 无法启动PostgreSQL
echo.
echo ```cmd
echo :: 检查PostgreSQL状态
echo pgsql18\pgsql\bin\pg_ctl.exe -D pgdata status
echo.
echo :: 查看PostgreSQL日志
echo type postgres.log
echo.
echo :: 手动启动PostgreSQL
echo pgsql18\pgsql\bin\pg_ctl.exe -D pgdata -l postgres.log start
echo ```
echo.
echo ### 2. 无法访问网页
echo.
echo 检查防火墙规则：
echo.
echo ```cmd
echo netsh advfirewall firewall show rule name="ERP HTTP"
echo netsh advfirewall firewall show rule name="ERP Flask"
echo ```
echo.
echo 检查端口监听：
echo.
echo ```cmd
echo netstat -ano ^| findstr ":5000"
echo netstat -ano ^| findstr ":80"
echo ```
echo.
echo ### 3. 数据库连接失败
echo.
echo 检查数据库配置：
echo.
echo ```cmd
echo :: 测试数据库连接
echo pgsql18\pgsql\bin\psql.exe -U wms_user -d wms -h 127.0.0.1
echo.
echo :: 检查 erp\.env 文件中的数据库配置
echo type erp\.env ^| findstr "PG_"
echo ```
echo.
echo ### 4. 查看应用日志
echo.
echo ```cmd
echo type erp\logs\flask_app.log
echo ```
echo.
echo ## 安全建议
echo.
echo 1. **修改默认密码**
echo    - 应用管理员密码
echo    - 数据库密码（修改 erp\.env 中的 PG_PASSWORD）
echo.
echo 2. **修改应用密钥**
echo    - 生成新密钥：
echo      ```cmd
echo      .venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
echo      ```
echo    - 更新 erp\.env 中的 INVENTORY_SECRET_KEY
echo.
echo 3. **配置HTTPS**（可选）
echo    - 使用IIS作为反向代理
echo    - 配置SSL证书
echo.
echo 4. **定期备份**
echo    - 配置自动备份任务
echo    - 备份文件保存到其他磁盘或服务器
echo.
echo 5. **限制访问**
echo    - 配置防火墙规则，只允许特定IP访问
echo    - 使用强密码策略
echo.
echo ## 卸载
echo.
echo 1. 停止服务（Ctrl+C）
echo 2. 停止PostgreSQL：
echo    ```cmd
echo    pgsql18\pgsql\bin\pg_ctl.exe -D pgdata stop
echo    ```
echo 3. 删除防火墙规则：
echo    ```cmd
echo    netsh advfirewall firewall delete rule name="ERP HTTP"
echo    netsh advfirewall firewall delete rule name="ERP Flask"
echo    ```
echo 4. 删除安装目录
echo.
echo ## 技术支持
echo.
echo 如有问题，请联系技术支持。
echo.
echo ---
echo.
echo 安装包生成时间：%TIMESTAMP%
) > "%BUILD_DIR%\README.md"

exit /b 0
