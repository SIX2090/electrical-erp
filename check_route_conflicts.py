"""
路由冲突检查工具
检测 Flask 应用中是否存在重复注册的路由
"""
import re
from collections import defaultdict

def extract_routes_from_file(filepath):
    """从路由文件中提取路由定义"""
    routes = []

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # 匹配 @app.route() 装饰器
        pattern1 = r'@app\.route\(["\']([^"\']+)["\']'
        matches1 = re.finditer(pattern1, content)
        for match in matches1:
            routes.append((match.group(1), filepath, match.start()))

        # 匹配 @app.get() / @app.post() 装饰器
        pattern2 = r'@app\.(get|post|put|delete|patch)\(["\']([^"\']+)["\']'
        matches2 = re.finditer(pattern2, content)
        for match in matches2:
            routes.append((match.group(2), filepath, match.start()))

    except Exception as e:
        print(f"⚠ 读取文件失败: {filepath} - {e}")

    return routes

def check_route_conflicts():
    """检查路由冲突"""
    print("=" * 80)
    print("路由冲突检查")
    print("=" * 80)
    print()

    # 需要检查的文件列表
    route_files = [
        "routes/finance_routes.py",
        "routes/voucher_routes.py",
        "routes/general_ledger_routes.py",
        "routes/project_cost_reports_routes.py",
        "routes/invoice_matching_routes.py",
        "routes/invoice_reconciliation_routes.py",
        "routes/period_closing_routes.py",
    ]

    # 收集所有路由
    all_routes = []
    for filepath in route_files:
        routes = extract_routes_from_file(filepath)
        all_routes.extend(routes)

    # 按路径分组
    routes_by_path = defaultdict(list)
    for path, filepath, pos in all_routes:
        routes_by_path[path].append(filepath)

    # 查找冲突
    conflicts = {}
    for path, files in routes_by_path.items():
        if len(files) > 1:
            conflicts[path] = files

    if conflicts:
        print("✗ 发现路由冲突:")
        print()
        for path, files in sorted(conflicts.items()):
            print(f"  路径: {path}")
            for f in files:
                print(f"    - {f}")
            print()
        print(f"总计: {len(conflicts)} 个冲突路径")
        return 1
    else:
        print("✓ 未发现路由冲突")
        return 0

def main():
    result = check_route_conflicts()
    print()
    print("=" * 80)
    if result == 0:
        print("✓ 路由检查通过")
    else:
        print("✗ 路由检查失败")
    print("=" * 80)
    return result

if __name__ == "__main__":
    exit(main())
