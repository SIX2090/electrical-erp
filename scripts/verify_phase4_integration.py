# -*- coding: utf-8 -*-
"""
财务模块第四期完整性验证脚本
检查所有文件是否正确创建和集成
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

print("=" * 80)
print("财务模块第四期 - 完整性验证")
print("=" * 80)

# 1. 检查服务层文件
print("\n1. 检查服务层文件...")
service_files = [
    'services/inventory_costing_service.py',
    'services/project_cost_service.py',
    'services/serial_cost_service.py',
]

for file_path in service_files:
    full_path = BASE_DIR / file_path
    if full_path.exists():
        size = full_path.stat().st_size
        print(f"  ✅ {file_path} ({size} bytes)")
    else:
        print(f"  ❌ {file_path} - 文件不存在")

# 2. 检查路由层文件
print("\n2. 检查路由层文件...")
route_files = [
    'routes/inventory_costing_routes.py',
    'routes/project_cost_reports_routes.py',
    'routes/serial_cost_reports_routes.py',
]

for file_path in route_files:
    full_path = BASE_DIR / file_path
    if full_path.exists():
        size = full_path.stat().st_size
        print(f"  ✅ {file_path} ({size} bytes)")

        # 检查路由注册函数
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
            if 'def register_' in content:
                print(f"     ✓ 包含路由注册函数")
            else:
                print(f"     ✗ 缺少路由注册函数")
    else:
        print(f"  ❌ {file_path} - 文件不存在")

# 3. 检查模板文件
print("\n3. 检查模板文件...")
template_files = [
    'templates/finance/inventory_costing_home.html',
    'templates/finance/inventory_cost_ledger.html',
    'templates/finance/inventory_ledger_reconciliation.html',
    'templates/finance/project_cost_detail.html',
    'templates/finance/project_cost_summary.html',
    'templates/finance/project_gross_profit.html',
    'templates/finance/serial_cost_detail.html',
    'templates/finance/serial_cost_summary.html',
    'templates/finance/serial_cost_variance.html',
]

for file_path in template_files:
    full_path = BASE_DIR / file_path
    if full_path.exists():
        size = full_path.stat().st_size
        print(f"  ✅ {file_path} ({size} bytes)")

        # 检查是否继承base.html
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
            if 'extends "base.html"' in content:
                print(f"     ✓ 继承base.html")
            else:
                print(f"     ✗ 未继承base.html")
    else:
        print(f"  ❌ {file_path} - 文件不存在")

# 4. 检查app.py集成
print("\n4. 检查app.py集成...")
app_file = BASE_DIR / 'app.py'
if app_file.exists():
    with open(app_file, 'r', encoding='utf-8') as f:
        content = f.read()

    imports = [
        'from routes.inventory_costing_routes import register_inventory_costing_routes',
        'from routes.project_cost_reports_routes import register_project_cost_routes',
        'from routes.serial_cost_reports_routes import register_serial_cost_routes',
    ]

    registers = [
        'register_inventory_costing_routes(',
        'register_project_cost_reports_routes(',
        'register_serial_cost_routes(',
    ]

    print("  导入检查:")
    for imp in imports:
        if imp in content:
            print(f"    ✅ {imp.split(' import ')[1]}")
        else:
            print(f"    ❌ {imp.split(' import ')[1]}")

    print("  注册检查:")
    for reg in registers:
        if reg in content:
            print(f"    ✅ {reg.replace('(', '')}")
        else:
            print(f"    ❌ {reg.replace('(', '')}")
else:
    print("  ❌ app.py 文件不存在")

# 5. 检查base.html导航菜单
print("\n5. 检查base.html导航菜单...")
base_template = BASE_DIR / 'templates/base.html'
if base_template.exists():
    with open(base_template, 'r', encoding='utf-8') as f:
        content = f.read()

    menu_items = [
        '/finance/inventory-costing',
        '/finance/project-cost/detail',
        '/finance/project-cost/summary',
        '/finance/project-cost/gross-profit',
        '/finance/serial-cost/detail',
        '/finance/serial-cost/summary',
        '/finance/serial-cost/variance',
    ]

    for item in menu_items:
        if item in content:
            print(f"  ✅ {item}")
        else:
            print(f"  ❌ {item} - 菜单项缺失")
else:
    print("  ❌ templates/base.html 文件不存在")

# 6. 检查数据库迁移文件
print("\n6. 检查数据库迁移文件...")
migration_files = [
    'migrations/20260616_004_finance_inventory_costing.py',
    'scripts/apply_finance_inventory_costing_schema.py',
]

for file_path in migration_files:
    full_path = BASE_DIR / file_path
    if full_path.exists():
        size = full_path.stat().st_size
        print(f"  ✅ {file_path} ({size} bytes)")
    else:
        print(f"  ❌ {file_path} - 文件不存在")

# 7. 统计信息
print("\n" + "=" * 80)
print("统计信息")
print("=" * 80)
print(f"服务层文件: {len(service_files)} 个")
print(f"路由层文件: {len(route_files)} 个")
print(f"模板文件: {len(template_files)} 个")
print(f"总计: {len(service_files) + len(route_files) + len(template_files)} 个文件")

print("\n✅ 验证完成！")
print("\n下一步:")
print("  1. 运行数据库迁移: python scripts/apply_finance_inventory_costing_schema.py")
print("  2. 启动应用: python app.py")
print("  3. 访问页面测试功能")
print()
