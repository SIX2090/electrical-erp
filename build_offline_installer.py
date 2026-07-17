#!/usr/bin/env python3
"""
ERP系统离线安装包生成器
生成适用于腾讯云Linux服务器的一键安装包
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

# 配置
PROJECT_ROOT = Path(__file__).parent
BUILD_DIR = PROJECT_ROOT / "installer_build"
OUTPUT_DIR = PROJECT_ROOT / "release"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
INSTALLER_NAME = f"ERP_Linux_Installer_{TIMESTAMP}"

# 需要排除的目录和文件
EXCLUDE_DIRS = {
    '__pycache__', '.pytest_cache', '.venv', 'venv',
    'pgdata', 'pgsql18', 'logs', 'backups', 'updates',
    '.git', '.codebuddy', '.claude', 'memory', 'installer_build',
    'release', 'node_modules'
}

EXCLUDE_FILES = {
    '*.pyc', '*.pyo', '*.log', '*.db',
    'postgresql-18.4-1-windows-x64-binaries.zip',
    '*.exe', '*.dll', '.DS_Store', 'Thumbs.db'
}


def print_step(msg):
    """打印步骤信息"""
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}\n")


def create_directory_structure():
    """创建构建目录结构"""
    print_step("创建目录结构")

    # 清理并重建构建目录
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)

    BUILD_DIR.mkdir(parents=True)
    (BUILD_DIR / "erp").mkdir()
    (BUILD_DIR / "scripts").mkdir()
    (BUILD_DIR / "wheels").mkdir()
    (BUILD_DIR / "config").mkdir()

    print("✓ 目录结构创建完成")


def copy_application_files():
    """复制应用文件"""
    print_step("复制应用文件")

    target_dir = BUILD_DIR / "erp"

    # 复制所有需要的文件和目录
    items_to_copy = [
        'app.py', 'config.py', 'requirements.txt', 'alembic.ini',
        '.env.example', 'pytest.ini',
        'routes', 'services', 'templates', 'static',
        'alembic', 'migrations', 'scripts', 'docs',
        '*.md', '*.txt'
    ]

    for item in PROJECT_ROOT.iterdir():
        # 跳过排除的目录
        if item.is_dir() and item.name in EXCLUDE_DIRS:
            continue

        # 跳过排除的文件
        if item.is_file() and any(item.match(pattern) for pattern in EXCLUDE_FILES):
            continue

        # 复制文件或目录
        if item.is_dir():
            if item.name in ['routes', 'services', 'templates', 'static', 'alembic', 'migrations', 'docs']:
                print(f"  复制目录: {item.name}")
                shutil.copytree(item, target_dir / item.name,
                              ignore=shutil.ignore_patterns(*EXCLUDE_DIRS, *EXCLUDE_FILES))
        elif item.is_file():
            if item.suffix in ['.py', '.txt', '.md', '.ini', '.example']:
                print(f"  复制文件: {item.name}")
                shutil.copy2(item, target_dir / item.name)

    # 创建必要的空目录
    for dir_name in ['logs', 'backups', 'uploads', 'reports']:
        (target_dir / dir_name).mkdir(exist_ok=True)
        (target_dir / dir_name / '.gitkeep').touch()

    print("✓ 应用文件复制完成")


def download_python_dependencies():
    """下载Python依赖包"""
    print_step("下载Python依赖包")

    wheels_dir = BUILD_DIR / "wheels"
    requirements_file = PROJECT_ROOT / "requirements.txt"

    if not requirements_file.exists():
        print("⚠ requirements.txt 不存在，跳过依赖下载")
        return

    # 使用pip download下载wheel包
    cmd = [
        sys.executable, "-m", "pip", "download",
        "-r", str(requirements_file),
        "-d", str(wheels_dir),
        "--platform", "manylinux2014_x86_64",
        "--python-version", "311",
        "--only-binary", ":all:",
        "--no-deps"
    ]

    print(f"执行命令: {' '.join(cmd)}")

    try:
        subprocess.run(cmd, check=True, cwd=PROJECT_ROOT)
        print("✓ Python依赖包下载完成")
    except subprocess.CalledProcessError as e:
        print(f"⚠ 部分依赖下载失败: {e}")
        print("  尝试不限制平台下载...")

        # 降级方案：下载所有平台
        cmd_fallback = [
            sys.executable, "-m", "pip", "download",
            "-r", str(requirements_file),
            "-d", str(wheels_dir)
        ]
        subprocess.run(cmd_fallback, check=True, cwd=PROJECT_ROOT)
        print("✓ Python依赖包下载完成（包含多平台）")


def create_install_script():
    """创建安装脚本"""
    print_step("创建安装脚本")

    install_script = BUILD_DIR / "install.sh"

    script_content = '''#!/bin/bash
# ERP系统一键安装脚本 - 适用于腾讯云Linux服务器
# 支持：CentOS 7/8, Ubuntu 18.04/20.04/22.04, Debian 10/11

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
INSTALL_DIR="/opt/erp"
VENV_DIR="$INSTALL_DIR/venv"
SERVICE_USER="erp"
DB_NAME="wms"
DB_USER="wms_user"
DB_PASSWORD="$(openssl rand -base64 32)"

# 颜色输出
RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
NC='\\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "请使用root权限运行此脚本"
        exit 1
    fi
}

detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
        OS_VERSION=$VERSION_ID
    else
        log_error "无法检测操作系统版本"
        exit 1
    fi
    log_info "检测到操作系统: $OS $OS_VERSION"
}

install_dependencies() {
    log_info "安装系统依赖..."

    if [[ "$OS" == "centos" ]] || [[ "$OS" == "rhel" ]]; then
        yum install -y epel-release
        yum install -y python3 python3-pip python3-venv \\
            postgresql postgresql-server postgresql-contrib \\
            nginx gcc python3-devel postgresql-devel

        # 初始化PostgreSQL
        if [ ! -d "/var/lib/pgsql/data" ]; then
            postgresql-setup --initdb
        fi

        systemctl enable postgresql
        systemctl start postgresql

    elif [[ "$OS" == "ubuntu" ]] || [[ "$OS" == "debian" ]]; then
        apt-get update
        apt-get install -y python3 python3-pip python3-venv \\
            postgresql postgresql-contrib \\
            nginx gcc python3-dev libpq-dev

        systemctl enable postgresql
        systemctl start postgresql

    else
        log_error "不支持的操作系统: $OS"
        exit 1
    fi

    log_info "✓ 系统依赖安装完成"
}

setup_database() {
    log_info "配置PostgreSQL数据库..."

    # 创建数据库用户和数据库
    sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';" 2>/dev/null || true
    sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" 2>/dev/null || true
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"

    # 配置PostgreSQL允许本地连接
    PG_HBA=$(sudo -u postgres psql -t -P format=unaligned -c "SHOW hba_file;")
    if ! grep -q "$DB_NAME.*$DB_USER" "$PG_HBA"; then
        echo "host    $DB_NAME    $DB_USER    127.0.0.1/32    md5" >> "$PG_HBA"
        systemctl restart postgresql
    fi

    log_info "✓ 数据库配置完成"
    log_info "  数据库名: $DB_NAME"
    log_info "  数据库用户: $DB_USER"
    log_info "  数据库密码: $DB_PASSWORD"
}

create_service_user() {
    log_info "创建服务用户..."

    if ! id "$SERVICE_USER" &>/dev/null; then
        useradd -r -s /bin/false -d "$INSTALL_DIR" "$SERVICE_USER"
        log_info "✓ 用户 $SERVICE_USER 创建完成"
    else
        log_info "  用户 $SERVICE_USER 已存在"
    fi
}

install_application() {
    log_info "安装ERP应用..."

    # 创建安装目录
    mkdir -p "$INSTALL_DIR"

    # 复制应用文件
    cp -r "$SCRIPT_DIR/erp/"* "$INSTALL_DIR/"

    # 创建Python虚拟环境
    python3 -m venv "$VENV_DIR"

    # 安装Python依赖
    if [ -d "$SCRIPT_DIR/wheels" ] && [ "$(ls -A $SCRIPT_DIR/wheels)" ]; then
        log_info "从离线包安装Python依赖..."
        "$VENV_DIR/bin/pip" install --no-index --find-links="$SCRIPT_DIR/wheels" -r "$INSTALL_DIR/requirements.txt"
    else
        log_info "从PyPI安装Python依赖..."
        "$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
    fi

    # 创建.env配置文件
    if [ ! -f "$INSTALL_DIR/.env" ]; then
        cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"

        # 生成SECRET_KEY
        SECRET_KEY=$(openssl rand -hex 32)

        # 更新配置
        sed -i "s/PG_HOST=.*/PG_HOST=127.0.0.1/" "$INSTALL_DIR/.env"
        sed -i "s/PG_PORT=.*/PG_PORT=5432/" "$INSTALL_DIR/.env"
        sed -i "s/PG_DATABASE=.*/PG_DATABASE=$DB_NAME/" "$INSTALL_DIR/.env"
        sed -i "s/PG_USER=.*/PG_USER=$DB_USER/" "$INSTALL_DIR/.env"
        sed -i "s/PG_PASSWORD=.*/PG_PASSWORD=$DB_PASSWORD/" "$INSTALL_DIR/.env"
        sed -i "s/INVENTORY_SECRET_KEY=.*/INVENTORY_SECRET_KEY=$SECRET_KEY/" "$INSTALL_DIR/.env"
        sed -i "s/FLASK_RUN_HOST=.*/FLASK_RUN_HOST=0.0.0.0/" "$INSTALL_DIR/.env"
    fi

    # 设置权限
    chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
    chmod -R 755 "$INSTALL_DIR"
    chmod 600 "$INSTALL_DIR/.env"

    log_info "✓ 应用安装完成"
}

initialize_database_schema() {
    log_info "初始化数据库架构..."

    cd "$INSTALL_DIR"
    sudo -u "$SERVICE_USER" "$VENV_DIR/bin/python" -c "
from app import app
from services.app_runtime import initialize_database

with app.app_context():
    try:
        initialize_database()
        print('数据库初始化成功')
    except Exception as e:
        print(f'数据库初始化失败: {e}')
        raise
"

    log_info "✓ 数据库架构初始化完成"
}

create_systemd_service() {
    log_info "创建systemd服务..."

    cat > /etc/systemd/system/erp.service <<EOF
[Unit]
Description=ERP System
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$VENV_DIR/bin"
ExecStart=$VENV_DIR/bin/python -m waitress --host=127.0.0.1 --port=5000 app:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable erp.service
    systemctl start erp.service

    log_info "✓ systemd服务创建完成"
}

configure_nginx() {
    log_info "配置Nginx反向代理..."

    cat > /etc/nginx/conf.d/erp.conf <<'EOF'
server {
    listen 80;
    server_name _;

    client_max_body_size 20M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 600;
        proxy_send_timeout 600;
        proxy_read_timeout 600;
    }

    location /static {
        alias /opt/erp/static;
        expires 30d;
    }
}
EOF

    # 测试nginx配置
    nginx -t

    # 重启nginx
    systemctl enable nginx
    systemctl restart nginx

    log_info "✓ Nginx配置完成"
}

configure_firewall() {
    log_info "配置防火墙..."

    if command -v firewall-cmd &> /dev/null; then
        firewall-cmd --permanent --add-service=http
        firewall-cmd --permanent --add-service=https
        firewall-cmd --reload
        log_info "✓ firewalld规则已更新"
    elif command -v ufw &> /dev/null; then
        ufw allow 'Nginx Full'
        log_info "✓ ufw规则已更新"
    else
        log_warn "未检测到防火墙，请手动开放80和443端口"
    fi
}

print_summary() {
    log_info "================================"
    log_info "ERP系统安装完成！"
    log_info "================================"
    echo ""
    echo "访问信息:"
    echo "  URL: http://$(hostname -I | awk '{print $1}')"
    echo "  默认用户: admin"
    echo "  默认密码: admin"
    echo ""
    echo "数据库信息:"
    echo "  数据库: $DB_NAME"
    echo "  用户: $DB_USER"
    echo "  密码: $DB_PASSWORD"
    echo ""
    echo "重要文件位置:"
    echo "  应用目录: $INSTALL_DIR"
    echo "  配置文件: $INSTALL_DIR/.env"
    echo "  日志目录: $INSTALL_DIR/logs"
    echo ""
    echo "服务管理:"
    echo "  启动: systemctl start erp"
    echo "  停止: systemctl stop erp"
    echo "  重启: systemctl restart erp"
    echo "  状态: systemctl status erp"
    echo "  日志: journalctl -u erp -f"
    echo ""
    log_warn "请务必修改默认密码并妥善保存数据库密码！"
}

# 主流程
main() {
    log_info "开始安装ERP系统..."

    check_root
    detect_os
    install_dependencies
    setup_database
    create_service_user
    install_application
    initialize_database_schema
    create_systemd_service
    configure_nginx
    configure_firewall
    print_summary

    log_info "安装完成！"
}

main
'''

    with open(install_script, 'w', encoding='utf-8', newline='\n') as f:
        f.write(script_content)

    # 设置执行权限
    install_script.chmod(0o755)

    print("✓ 安装脚本创建完成")


def create_readme():
    """创建README文件"""
    print_step("创建README文档")

    readme_content = '''# ERP系统离线安装包

## 系统要求

- 操作系统：CentOS 7/8, Ubuntu 18.04/20.04/22.04, Debian 10/11
- 内存：至少 2GB RAM
- 磁盘：至少 5GB 可用空间
- Python：3.8 或更高版本
- PostgreSQL：12 或更高版本

## 安装步骤

### 1. 上传安装包

将整个安装包上传到服务器，例如：

```bash
scp -r ERP_Linux_Installer_*.tar.gz root@your-server:/tmp/
```

### 2. 解压安装包

```bash
cd /tmp
tar -xzf ERP_Linux_Installer_*.tar.gz
cd ERP_Linux_Installer_*/
```

### 3. 运行安装脚本

```bash
chmod +x install.sh
sudo ./install.sh
```

安装脚本将自动完成：
- 安装系统依赖（Python、PostgreSQL、Nginx）
- 配置PostgreSQL数据库
- 安装ERP应用
- 初始化数据库架构
- 配置systemd服务
- 配置Nginx反向代理
- 配置防火墙规则

### 4. 访问系统

安装完成后，通过浏览器访问：

```
http://您的服务器IP地址
```

默认登录信息：
- 用户名：`admin`
- 密码：`admin`

**⚠️ 首次登录后请立即修改密码！**

## 服务管理

### 查看服务状态

```bash
systemctl status erp
```

### 启动/停止/重启服务

```bash
systemctl start erp
systemctl stop erp
systemctl restart erp
```

### 查看日志

```bash
# 查看实时日志
journalctl -u erp -f

# 查看最近100行日志
journalctl -u erp -n 100
```

## 配置文件

主配置文件位于：`/opt/erp/.env`

修改配置后需要重启服务：

```bash
systemctl restart erp
```

## 数据库备份

### 手动备份

```bash
sudo -u postgres pg_dump wms > /opt/erp/backups/wms_$(date +%Y%m%d_%H%M%S).sql
```

### 自动备份（推荐）

添加到crontab：

```bash
# 每天凌晨2点备份
0 2 * * * sudo -u postgres pg_dump wms > /opt/erp/backups/wms_$(date +\%Y\%m\%d).sql
```

## 故障排查

### 1. 服务无法启动

```bash
# 查看详细错误信息
journalctl -u erp -n 50

# 检查配置文件
cat /opt/erp/.env

# 手动启动测试
cd /opt/erp
source venv/bin/activate
python app.py
```

### 2. 无法访问网页

```bash
# 检查Nginx状态
systemctl status nginx

# 检查Nginx配置
nginx -t

# 检查端口监听
netstat -tlnp | grep -E '(80|5000)'
```

### 3. 数据库连接失败

```bash
# 检查PostgreSQL状态
systemctl status postgresql

# 测试数据库连接
sudo -u postgres psql -d wms -U wms_user -h 127.0.0.1
```

## 安全建议

1. **修改默认密码**：首次登录后立即修改admin密码
2. **保护数据库密码**：数据库密码保存在 `/opt/erp/.env`，请妥善保管
3. **配置HTTPS**：建议使用Let's Encrypt配置SSL证书
4. **定期备份**：设置自动备份任务
5. **更新系统**：定期更新操作系统和应用依赖

## HTTPS配置（可选）

### 使用Let's Encrypt（推荐）

```bash
# 安装certbot
yum install -y certbot python3-certbot-nginx  # CentOS
apt-get install -y certbot python3-certbot-nginx  # Ubuntu/Debian

# 获取证书并自动配置Nginx
certbot --nginx -d your-domain.com

# 自动续期
echo "0 3 * * * certbot renew --quiet" | crontab -
```

## 卸载

```bash
# 停止服务
systemctl stop erp
systemctl disable erp

# 删除服务文件
rm /etc/systemd/system/erp.service
systemctl daemon-reload

# 删除Nginx配置
rm /etc/nginx/conf.d/erp.conf
systemctl restart nginx

# 删除应用文件
rm -rf /opt/erp

# 删除数据库（可选）
sudo -u postgres psql -c "DROP DATABASE wms;"
sudo -u postgres psql -c "DROP USER wms_user;"
```

## 技术支持

如有问题，请联系技术支持或查阅详细文档。

---

安装包生成时间：{timestamp}
'''

    readme_file = BUILD_DIR / "README.md"
    with open(readme_file, 'w', encoding='utf-8') as f:
        f.write(readme_content.format(timestamp=TIMESTAMP))

    print("✓ README文档创建完成")


def create_tarball():
    """打包成tar.gz"""
    print_step("打包安装文件")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"{INSTALLER_NAME}.tar.gz"

    # 使用tar命令打包
    import tarfile

    with tarfile.open(output_file, "w:gz") as tar:
        tar.add(BUILD_DIR, arcname=INSTALLER_NAME)

    file_size = output_file.stat().st_size / (1024 * 1024)

    print(f"✓ 安装包创建完成")
    print(f"  文件: {output_file}")
    print(f"  大小: {file_size:.2f} MB")

    return output_file


def main():
    """主函数"""
    print("\n" + "="*60)
    print("  ERP系统离线安装包生成器")
    print("  适用于腾讯云Linux服务器")
    print("="*60 + "\n")

    try:
        create_directory_structure()
        copy_application_files()
        download_python_dependencies()
        create_install_script()
        create_readme()
        output_file = create_tarball()

        print("\n" + "="*60)
        print("  ✓ 安装包生成成功！")
        print("="*60)
        print(f"\n安装包位置: {output_file}")
        print("\n后续步骤:")
        print("1. 将安装包上传到腾讯云服务器")
        print("2. 解压: tar -xzf " + output_file.name)
        print("3. 运行安装: sudo ./install.sh")
        print("\n")

    except Exception as e:
        print(f"生成安装包失败: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
