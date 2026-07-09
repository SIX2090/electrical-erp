"""
财务模块修复 - 阶段 1：路由冲突修复
自动注释掉重复的路由注册
"""
import os
import shutil
from datetime import datetime

def backup_file(filepath):
    """备份文件"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{filepath}.backup_{timestamp}"
    shutil.copy2(filepath, backup_path)
    print(f"✓ 已备份: {backup_path}")
    return backup_path

def fix_app_py():
    """修复 app.py 中的重复路由注册"""
    filepath = "app.py"

    # 备份
    backup_file(filepath)

    # 读取文件
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 需要注释的 import 行
    imports_to_comment = [
        "from routes.voucher_routes import register_voucher_routes",
        "from routes.general_ledger_routes import register_general_ledger_routes",
        "from routes.project_cost_reports_routes import register_project_cost_routes as register_project_cost_reports_routes",
    ]

    # 需要注释的注册调用行
    registers_to_comment = [
        "register_voucher_routes(",
        "register_general_ledger_routes(",
        "register_project_cost_reports_routes(",
    ]

    modified_lines = []
    in_register_call = None
    paren_depth = 0

    for i, line in enumerate(lines, 1):
        # 检查是否是需要注释的 import 行
        if any(imp in line for imp in imports_to_comment):
            if not line.strip().startswith("#"):
                modified_lines.append("# " + line)
                print(f"✓ 行 {i}: 注释 import - {line.strip()[:60]}")
                continue

        # 检查是否是需要注释的注册调用
        if in_register_call is None:
            for reg in registers_to_comment:
                if reg in line:
                    in_register_call = reg
                    paren_depth = line.count("(") - line.count(")")
                    if not line.strip().startswith("#"):
                        modified_lines.append("# " + line)
                        print(f"✓ 行 {i}: 注释注册调用开始 - {reg}")
                    else:
                        modified_lines.append(line)
                    break
            else:
                modified_lines.append(line)
        else:
            # 在注册调用内部
            paren_depth += line.count("(") - line.count(")")
            if not line.strip().startswith("#"):
                modified_lines.append("# " + line)
                print(f"✓ 行 {i}: 注释注册调用内部")
            else:
                modified_lines.append(line)

            if paren_depth <= 0:
                print(f"✓ 行 {i}: 注册调用结束")
                in_register_call = None
                paren_depth = 0

    # 写回文件
    with open(filepath, "w", encoding="utf-8") as f:
        f.writelines(modified_lines)

    print(f"\n✓ {filepath} 修复完成")

def main():
    print("=" * 80)
    print("财务模块修复 - 阶段 1：路由冲突修复")
    print("=" * 80)
    print()

    # 检查当前目录
    if not os.path.exists("app.py"):
        print("✗ 错误: 当前目录没有 app.py，请在 ERP 项目根目录运行此脚本")
        return 1

    print("开始修复 app.py...")
    print()

    try:
        fix_app_py()
        print()
        print("=" * 80)
        print("✓ 阶段 1 修复完成")
        print("=" * 80)
        print()
        print("下一步:")
        print("1. 运行验证: .venv\\Scripts\\python.exe check_route_conflicts.py")
        print("2. 重启 ERP: restart_erp.cmd")
        print("3. 访问 http://127.0.0.1:5000/finance/vouchers 测试")
        return 0
    except Exception as e:
        print(f"\n✗ 修复失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())
