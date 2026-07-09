"""
财务模块修复 - 阶段 5：修复红冲模板 endpoint
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

def fix_red_flush_template():
    """修复红冲模板的 endpoint"""
    filepath = "templates/finance/invoice_red_flush_form.html"

    if not os.path.exists(filepath):
        print(f"✗ 错误: 文件不存在 - {filepath}")
        return False

    # 备份
    backup_file(filepath)

    # 读取文件
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # 替换 endpoint
    # 旧: url_for('finance.' + kind + '_invoices')
    # 新: url_for('finance_' + kind + '_invoices_standard')

    replacements = [
        (
            "url_for('finance.' + kind + '_invoices')",
            "url_for('finance_' + kind + '_invoices_standard')"
        ),
        (
            'url_for("finance." + kind + "_invoices")',
            'url_for("finance_" + kind + "_invoices_standard")'
        ),
    ]

    replacements_count = 0
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            count = content.count(new)
            print(f"✓ 替换 endpoint: {old} → {new}")
            replacements_count += 1

    # 写回文件
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"✓ {filepath} 完成 {replacements_count} 处替换")
    return True

def main():
    print("=" * 80)
    print("财务模块修复 - 阶段 5：修复红冲模板 endpoint")
    print("=" * 80)
    print()

    try:
        success = fix_red_flush_template()

        if success:
            print()
            print("=" * 80)
            print("✓ 阶段 5 修复完成")
            print("=" * 80)
            print()
            print("下一步:")
            print("1. 重启 ERP: restart_erp.cmd")
            print("2. 测试红冲功能")
            print("   预期: 提交后正确跳转到发票列表")
            return 0
        else:
            return 1
    except Exception as e:
        print(f"\n✗ 修复失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())
