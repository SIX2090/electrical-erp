#!/usr/bin/env python3
"""
Inventory Balance Consistency Fix Wrapper
一键修复库存余额一致性问题
"""
import subprocess
import sys
import os
from pathlib import Path

# 设置工作目录为脚本所在目录
ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

# 设置环境变量
os.environ['PG_PASSWORD'] = 'admin'
os.environ['PYTHONUTF8'] = '1'
os.environ['PYTHONIOENCODING'] = 'utf-8'

print("=" * 80)
print("库存余额一致性修复工具")
print("=" * 80)
print()

# Step 1: 运行审计
print("步骤 1/4: 运行库存余额一致性审计...")
print("-" * 80)
result = subprocess.run(
    ['.venv\\Scripts\\python.exe', 'scripts\\audit_inventory_balance_consistency.py'],
    cwd=str(ROOT),
    env=os.environ.copy(),
    capture_output=False,
    text=True
)
print()

if result.returncode == 0:
    print("✅ 审计通过！库存余额一致，无需修复。")
    sys.exit(0)

print("⚠️  发现库存余额不一致问题，需要修复。")
print()

# Step 2: Dry-run 修复预览
print("步骤 2/4: 预览修复方案（dry-run）...")
print("-" * 80)
result = subprocess.run(
    ['.venv\\Scripts\\python.exe', 'scripts\\repair_inventory_balance_consistency.py', '--dry-run'],
    cwd=str(ROOT),
    env=os.environ.copy(),
    capture_output=False,
    text=True
)
print()

# Step 3: 备份数据库
print("步骤 3/4: 备份数据库...")
print("-" * 80)
backup_file = f'backups\\pre_inventory_fix_{os.getpid()}.dump'
result = subprocess.run(
    ['.venv\\Scripts\\python.exe', 'scripts\\pg_backup.py', '--output', backup_file],
    cwd=str(ROOT),
    env=os.environ.copy(),
    capture_output=False,
    text=True
)

if result.returncode != 0:
    print("❌ 备份失败！终止修复流程。")
    sys.exit(1)

print(f"✅ 备份完成: {backup_file}")
print()

# Step 4: 执行修复
print("步骤 4/4: 执行修复（apply）...")
print("-" * 80)
print("即将执行修复操作，修复策略：")
print("  - 主账：inventory_balances")
print("  - 自动备份受影响行到 inventory_balance_repair_audit 表")
print("  - 更新 legacy inventory 和 batch_tracking")
print("  - 插入 stock_transactions 对账记录")
print()

response = input("确认执行修复？(yes/no): ").strip().lower()
if response != 'yes':
    print("❌ 用户取消修复。")
    sys.exit(1)

print()
print("正在执行修复...")
result = subprocess.run(
    ['.venv\\Scripts\\python.exe', 'scripts\\repair_inventory_balance_consistency.py', '--apply'],
    cwd=str(ROOT),
    env=os.environ.copy(),
    capture_output=False,
    text=True
)

if result.returncode != 0:
    print("❌ 修复失败！")
    sys.exit(1)

print()
print("✅ 修复完成！")
print()

# Step 5: 重新审计验证
print("步骤 5/5: 重新审计验证...")
print("-" * 80)
result = subprocess.run(
    ['.venv\\Scripts\\python.exe', 'scripts\\audit_inventory_balance_consistency.py'],
    cwd=str(ROOT),
    env=os.environ.copy(),
    capture_output=False,
    text=True
)
print()

if result.returncode == 0:
    print("=" * 80)
    print("🎉 修复成功！库存余额一致性审计通过！")
    print("=" * 80)
else:
    print("=" * 80)
    print("⚠️  修复后仍有问题，请检查审计输出。")
    print("=" * 80)

sys.exit(result.returncode)
