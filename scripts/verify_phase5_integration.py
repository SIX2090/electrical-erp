"""
验证财务模块第五期集成是否完整
"""

import os
import sys

def check_file_exists(filepath, description):
    """检查文件是否存在"""
    if os.path.exists(filepath):
        print(f"✓ {description}")
        return True
    else:
        print(f"✗ {description} - 文件不存在: {filepath}")
        return False

def verify_phase5_integration():
    """验证第五期集成"""

    print("=" * 80)
    print("财务模块第五期集成验证")
    print("=" * 80)
    print()

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    all_checks = []

    # 1. 数据库层
    print("[1/6] 检查数据库层文件...")
    all_checks.append(check_file_exists(
        os.path.join(base_dir, "migrations", "20260616_005_finance_period_closing.py"),
        "迁移脚本"
    ))
    all_checks.append(check_file_exists(
        os.path.join(base_dir, "scripts", "apply_finance_period_closing_schema.py"),
        "迁移应用脚本"
    ))
    print()

    # 2. 服务层
    print("[2/6] 检查服务层文件...")
    all_checks.append(check_file_exists(
        os.path.join(base_dir, "services", "period_closing_service.py"),
        "期末处理服务"
    ))
    all_checks.append(check_file_exists(
        os.path.join(base_dir, "services", "financial_report_service.py"),
        "财务报表服务"
    ))
    print()

    # 3. 路由层
    print("[3/6] 检查路由层文件...")
    all_checks.append(check_file_exists(
        os.path.join(base_dir, "routes", "period_closing_routes.py"),
        "期末处理路由"
    ))
    all_checks.append(check_file_exists(
        os.path.join(base_dir, "routes", "financial_report_routes.py"),
        "财务报表路由"
    ))
    print()

    # 4. 模板层
    print("[4/6] 检查模板层文件...")
    templates = [
        ("period_closing_home.html", "期末处理首页"),
        ("period_closing_check.html", "结账检查页面"),
        ("period_closing_history.html", "结账历史页面"),
        ("financial_report_home.html", "财务报表首页"),
        ("balance_sheet.html", "资产负债表"),
        ("income_statement.html", "利润表"),
        ("cash_flow_statement.html", "现金流量表"),
    ]

    for filename, description in templates:
        all_checks.append(check_file_exists(
            os.path.join(base_dir, "templates", "finance", filename),
            f"{description}"
        ))
    print()

    # 5. 应用集成
    print("[5/6] 检查应用集成...")

    # 检查 app.py
    app_py = os.path.join(base_dir, "app.py")
    if os.path.exists(app_py):
        with open(app_py, 'r', encoding='utf-8') as f:
            content = f.read()

            has_period_import = 'from routes.period_closing_routes import register_period_closing_routes' in content
            has_report_import = 'from routes.financial_report_routes import register_financial_report_routes' in content
            has_period_register = 'register_period_closing_routes(app)' in content
            has_report_register = 'register_financial_report_routes(app)' in content

            if has_period_import:
                print("✓ app.py 导入期末处理路由")
                all_checks.append(True)
            else:
                print("✗ app.py 未导入期末处理路由")
                all_checks.append(False)

            if has_report_import:
                print("✓ app.py 导入财务报表路由")
                all_checks.append(True)
            else:
                print("✗ app.py 未导入财务报表路由")
                all_checks.append(False)

            if has_period_register:
                print("✓ app.py 注册期末处理路由")
                all_checks.append(True)
            else:
                print("✗ app.py 未注册期末处理路由")
                all_checks.append(False)

            if has_report_register:
                print("✓ app.py 注册财务报表路由")
                all_checks.append(True)
            else:
                print("✗ app.py 未注册财务报表路由")
                all_checks.append(False)
    else:
        print("✗ app.py 文件不存在")
        all_checks.extend([False, False, False, False])

    # 检查 base.html
    base_html = os.path.join(base_dir, "templates", "base.html")
    if os.path.exists(base_html):
        with open(base_html, 'r', encoding='utf-8') as f:
            content = f.read()

            has_period_menu = '/finance/period-closing' in content
            has_report_menu = '/finance/reports/balance-sheet' in content

            if has_period_menu:
                print("✓ base.html 包含期末处理菜单")
                all_checks.append(True)
            else:
                print("✗ base.html 未包含期末处理菜单")
                all_checks.append(False)

            if has_report_menu:
                print("✓ base.html 包含财务报表菜单")
                all_checks.append(True)
            else:
                print("✗ base.html 未包含财务报表菜单")
                all_checks.append(False)
    else:
        print("✗ base.html 文件不存在")
        all_checks.extend([False, False])

    print()

    # 6. 文档
    print("[6/6] 检查文档文件...")
    all_checks.append(check_file_exists(
        os.path.join(base_dir, "docs", "财务模块第五期_期末处理与报表开发计划_20260616.md"),
        "开发计划文档"
    ))
    print()

    # 总结
    print("=" * 80)
    print("验证结果")
    print("=" * 80)
    total = len(all_checks)
    passed = sum(all_checks)
    failed = total - passed

    print(f"总计: {total} 项")
    print(f"通过: {passed} 项")
    print(f"失败: {failed} 项")
    print()

    if failed == 0:
        print("✅ 所有检查项通过！第五期集成完整。")
        print()
        print("下一步:")
        print("  1. 运行 python scripts/apply_finance_period_closing_schema.py 应用数据库迁移")
        print("  2. 运行 python app.py 启动应用")
        print("  3. 访问期末处理和财务报表功能")
        return True
    else:
        print(f"⚠️  {failed} 项检查未通过，请修复后重新验证")
        return False

if __name__ == "__main__":
    success = verify_phase5_integration()
    sys.exit(0 if success else 1)
