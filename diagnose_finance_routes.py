"""
财务模块路由诊断脚本
检查路由注册和冲突情况
"""
import re

def main():
    print("=" * 80)
    print("财务模块路由诊断")
    print("=" * 80)

    # 读取 app.py 查找路由注册
    with open("app.py", "r", encoding="utf-8") as f:
        app_content = f.read()

    print("\n1. 路由注册顺序")
    print("-" * 80)

    # 查找所有 register 调用
    register_pattern = r'(register_\w+)\('
    matches = re.finditer(register_pattern, app_content)

    finance_related = []
    for i, match in enumerate(matches, 1):
        func_name = match.group(1)
        if any(keyword in func_name.lower() for keyword in ['finance', 'voucher', 'ledger', 'invoice', 'project_cost', 'serial_cost', 'period', 'costing']):
            line_num = app_content[:match.start()].count('\n') + 1
            finance_related.append((line_num, func_name))
            print(f"  {line_num:4d}: {func_name}")

    # 检查重复路由
    print("\n2. 可能的路由冲突")
    print("-" * 80)

    known_conflicts = [
        ("/finance/vouchers", ["register_finance_routes", "register_voucher_routes"]),
        ("/finance/vouchers/<id>", ["register_finance_routes", "register_voucher_routes"]),
        ("/finance/reports/account-balance", ["register_finance_routes", "register_general_ledger_routes"]),
        ("/finance/reports/aging", ["register_finance_routes", "register_general_ledger_routes"]),
        ("/finance/project-cost/detail", ["register_finance_routes", "register_project_cost_reports_routes"]),
    ]

    for path, handlers in known_conflicts:
        print(f"\n  路径: {path}")
        for handler in handlers:
            print(f"    - {handler}")

    # 检查守卫规则
    print("\n3. 财务路径守卫检查")
    print("-" * 80)

    if 'finance_blocked_get_paths' in app_content:
        blocked_pattern = r'finance_blocked_get_paths\s*=\s*\{([^}]+)\}'
        match = re.search(blocked_pattern, app_content)
        if match:
            print("  被拦截的 GET 路径:")
            paths = re.findall(r'"([^"]+)"', match.group(1))
            for path in paths:
                print(f"    - {path}")

    if 'finance_blocked_post_paths' in app_content:
        blocked_pattern = r'finance_blocked_post_paths\s*=\s*\{([^}]+)\}'
        match = re.search(blocked_pattern, app_content)
        if match:
            print("  被拦截的 POST 路径:")
            paths = re.findall(r'"([^"]+)"', match.group(1))
            for path in paths:
                print(f"    - {path}")

    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
