"""
财务模块修复 - 阶段 2：解除路由守卫
删除拦截财务路径的 404 守卫
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

def fix_app_py_guards():
    """修复 app.py 中的路由守卫"""
    filepath = "app.py"

    # 备份
    backup_file(filepath)

    # 读取文件
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # 查找并删除 finance_blocked_get_paths 守卫块
    import re

    # 模式 1: finance_blocked_get_paths 定义和使用
    pattern1 = r'(\s*)finance_blocked_get_paths\s*=\s*\{[^}]+\}\s*if\s+method\s*==\s*"GET"\s+and\s+path\s+in\s+finance_blocked_get_paths:\s*return\s+"Not Found",\s*404\s*'

    if re.search(pattern1, content, re.MULTILINE | re.DOTALL):
        content = re.sub(pattern1, '', content)
        print("✓ 删除 finance_blocked_get_paths 守卫块")

    # 模式 2: finance_blocked_post_paths 定义和使用
    pattern2 = r'(\s*)finance_blocked_post_paths\s*=\s*\{[^}]+\}\s*if\s+method\s*==\s*"POST"\s+and\s+path\s+in\s+finance_blocked_post_paths:\s*return\s+_forbidden\(\)\s*'

    if re.search(pattern2, content, re.MULTILINE | re.DOTALL):
        content = re.sub(pattern2, '', content)
        print("✓ 删除 finance_blocked_post_paths 守卫块")

    # 如果模式匹配失败，尝试更宽松的匹配
    if 'finance_blocked_get_paths' in content:
        # 手动查找和删除
        lines = content.split('\n')
        new_lines = []
        skip_until_line = -1

        for i, line in enumerate(lines):
            if i < skip_until_line:
                continue

            # 检查是否是守卫定义开始
            if 'finance_blocked_get_paths' in line and '=' in line:
                print(f"✓ 行 {i+1}: 发现 finance_blocked_get_paths 定义")
                # 跳过定义和使用
                skip_until_line = i + 10  # 假设守卫代码在 10 行内
                for j in range(i, min(i + 15, len(lines))):
                    if 'return "Not Found", 404' in lines[j]:
                        skip_until_line = j + 1
                        print(f"✓ 行 {j+1}: 跳过到守卫代码结束")
                        break
                continue

            if 'finance_blocked_post_paths' in line and '=' in line:
                print(f"✓ 行 {i+1}: 发现 finance_blocked_post_paths 定义")
                skip_until_line = i + 10
                for j in range(i, min(i + 15, len(lines))):
                    if 'return _forbidden()' in lines[j]:
                        skip_until_line = j + 1
                        print(f"✓ 行 {j+1}: 跳过到守卫代码结束")
                        break
                continue

            new_lines.append(line)

        content = '\n'.join(new_lines)

    # 写回文件
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"\n✓ {filepath} 修复完成")

def main():
    print("=" * 80)
    print("财务模块修复 - 阶段 2：解除路由守卫")
    print("=" * 80)
    print()

    # 检查当前目录
    if not os.path.exists("app.py"):
        print("✗ 错误: 当前目录没有 app.py，请在 ERP 项目根目录运行此脚本")
        return 1

    print("开始修复 app.py...")
    print()

    try:
        fix_app_py_guards()
        print()
        print("=" * 80)
        print("✓ 阶段 2 修复完成")
        print("=" * 80)
        print()
        print("下一步:")
        print("1. 重启 ERP: restart_erp.cmd")
        print("2. 访问 http://127.0.0.1:5000/finance/vouchers/new")
        print("   预期: 不再返回 404")
        return 0
    except Exception as e:
        print(f"\n✗ 修复失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())
