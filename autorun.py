import os
import sys
import subprocess

# 设置正确的工作目录
project_dir = r"C:\WMS_ERP_Offline_Installer_20260610_104613\WMS_ERP_Offline_Installer_20260610_104613"
os.chdir(project_dir)

# 执行修复脚本
python_exe = os.path.join(project_dir, ".venv", "Scripts", "python.exe")
script_path = os.path.join(project_dir, "execute_fix_inline.py")

print("=" * 80)
print("自动执行库存修复")
print("=" * 80)
print(f"工作目录: {os.getcwd()}")
print(f"Python: {python_exe}")
print(f"脚本: {script_path}")
print()

# 直接运行
try:
    result = subprocess.run(
        [python_exe, script_path],
        cwd=project_dir,
        capture_output=True,
        text=True,
        encoding='utf-8'
    )

    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)

    print()
    print("=" * 80)
    print(f"退出码: {result.returncode}")
    print("=" * 80)

    sys.exit(result.returncode)
except Exception as e:
    print(f"执行失败: {e}")
    sys.exit(1)
