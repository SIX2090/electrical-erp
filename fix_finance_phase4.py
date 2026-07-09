"""
财务模块修复 - 阶段 4：修复 SQL 字段名
将 total_amount 替换为 amount_with_tax
"""
import os
import shutil
import re
from datetime import datetime

def backup_file(filepath):
    """备份文件"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{filepath}.backup_{timestamp}"
    shutil.copy2(filepath, backup_path)
    print(f"✓ 已备份: {backup_path}")
    return backup_path

def fix_sql_fields_in_file(filepath):
    """修复单个文件中的 SQL 字段名"""
    if not os.path.exists(filepath):
        print(f"⚠ 跳过不存在的文件: {filepath}")
        return 0

    # 备份
    backup_file(filepath)

    # 读取文件
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # 替换模式
    patterns = [
        (r'\bsii\.total_amount\b', 'sii.amount_with_tax'),
        (r'\bpii\.total_amount\b', 'pii.amount_with_tax'),
        (r'\bsales_invoice_items\.total_amount\b', 'sales_invoice_items.amount_with_tax'),
        (r'\bpurchase_invoice_items\.total_amount\b', 'purchase_invoice_items.amount_with_tax'),
        (r'\bsi\.total_amount\b', 'si.amount_with_tax'),
        (r'\bpi\.total_amount\b', 'pi.amount_with_tax'),
    ]

    replacements_count = 0
    for pattern, replacement in patterns:
        matches = list(re.finditer(pattern, content))
        if matches:
            content = re.sub(pattern, replacement, content)
            replacements_count += len(matches)
            print(f"  ✓ 替换 {len(matches)} 处: {pattern} → {replacement}")

    # 写回文件
    if replacements_count > 0:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✓ {filepath} 完成 {replacements_count} 处替换")
    else:
        print(f"  ℹ {filepath} 无需替换")

    return replacements_count

def main():
    print("=" * 80)
    print("财务模块修复 - 阶段 4：修复 SQL 字段名")
    print("=" * 80)
    print()

    # 需要修复的文件列表
    files_to_fix = [
        "routes/finance_routes.py",
        "routes/invoice_matching_routes.py",
        "routes/invoice_reconciliation_routes.py",
        "routes/voucher_routes.py",
        "routes/general_ledger_routes.py",
        "routes/project_cost_reports_routes.py",
    ]

    print("将修复以下文件中的 total_amount 字段:")
    for f in files_to_fix:
        print(f"  - {f}")
    print()

    total_replacements = 0

    for filepath in files_to_fix:
        print(f"\n处理: {filepath}")
        print("-" * 80)
        count = fix_sql_fields_in_file(filepath)
        total_replacements += count

    print()
    print("=" * 80)
    print(f"✓ 阶段 4 修复完成，共替换 {total_replacements} 处")
    print("=" * 80)
    print()
    print("下一步:")
    print("1. 重启 ERP: restart_erp.cmd")
    print("2. 访问以下报表测试:")
    print("   - http://127.0.0.1:5000/finance/reports/sales-three-way-match")
    print("   - http://127.0.0.1:5000/finance/reports/purchase-three-way-match")
    print("   预期: 不再 500 错误")

if __name__ == "__main__":
    main()
