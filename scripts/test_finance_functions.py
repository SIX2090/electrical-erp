"""
测试财务模块核心功能
"""

import sys
import os
import re
import requests
from datetime import datetime

# 测试配置
BASE_URL = os.environ.get("ERP_TEST_BASE_URL", "http://127.0.0.1:5000")
TEST_USER = os.environ.get("ERP_TEST_USER", "admin")
TEST_PASSWORD = os.environ.get("ERP_TEST_PASSWORD", "")

# 会话对象
session = requests.Session()


def login():
    """登录系统"""
    print("=" * 80)
    print("1. 登录测试")
    print("=" * 80)

    # 先访问登录页面获取CSRF token
    try:
        login_page = session.get(f"{BASE_URL}/login")
        if login_page.status_code != 200:
            print(f"[FAIL] 无法访问登录页面: {login_page.status_code}")
            return False
    except Exception as e:
        print(f"[FAIL] 访问登录页面失败: {e}")
        return False

    # 从登录页面提取CSRF token
    csrf_match = re.search(r'name="csrf_token"\s+value="([^"]+)"', login_page.text)
    csrf_token = csrf_match.group(1) if csrf_match else ""

    # 尝试登录
    response = session.post(
        f"{BASE_URL}/login",
        data={
            "username": TEST_USER,
            "password": TEST_PASSWORD,
            "csrf_token": csrf_token
        },
        allow_redirects=True  # 改为True，跟随重定向
    )

    # 检查是否登录成功 - 检查响应中是否有登录成功的标志
    if response.status_code == 200:
        # 检查是否重定向到了主页或包含用户信息
        if "/login" not in response.url and ("admin" in response.text or "退出" in response.text or "主页" in response.text):
            print("[OK] 登录成功")
            return True
        else:
            print(f"[FAIL] 登录可能失败，当前URL: {response.url}")
            return False
    else:
        print(f"[FAIL] 登录失败: {response.status_code}")
        return False


def test_period_closing_home():
    """测试期末处理首页"""
    print()
    print("=" * 80)
    print("2. 测试期末处理首页")
    print("=" * 80)

    try:
        response = session.get(f"{BASE_URL}/finance/period-closing/")

        if response.status_code == 200:
            print(f"[OK] 期末处理首页访问成功")
            print(f"     页面大小: {len(response.text)} 字节")

            # 检查页面关键内容
            if "期末处理" in response.text or "period" in response.text:
                print("[OK] 页面包含期末处理相关内容")
            else:
                print("[WARN] 页面可能缺少期末处理内容")

            return True
        else:
            print(f"[FAIL] 访问失败: {response.status_code}")
            return False

    except Exception as e:
        print(f"[ERROR] 测试失败: {e}")
        return False


def test_period_closing_check():
    """测试期末结账检查"""
    print()
    print("=" * 80)
    print("3. 测试期末结账检查")
    print("=" * 80)

    try:
        # 获取当前期间
        current_period = datetime.now().strftime('%Y-%m')
        print(f"     当前期间: {current_period}")

        response = session.post(
            f"{BASE_URL}/finance/period-closing/check",
            json={"period": current_period},
            headers={"Content-Type": "application/json"}
        )

        if response.status_code == 200:
            result = response.json()
            print(f"[OK] 结账检查API调用成功")
            print(f"     是否可以结账: {result.get('can_close', False)}")
            print(f"     检查问题数: {len(result.get('issues', []))}")
            print(f"     警告数: {len(result.get('warnings', []))}")

            if result.get('issues'):
                print("\n     检查问题:")
                for issue in result['issues'][:3]:  # 只显示前3个
                    print(f"       - {issue.get('check_item')}: {issue.get('reason')}")

            if result.get('summary'):
                summary = result['summary']
                print(f"\n     汇总信息:")
                print(f"       - 凭证数量: {summary.get('voucher_count', 0)}")
                print(f"       - 未审核凭证: {summary.get('unreviewed_vouchers', 0)}")
                print(f"       - 借方总额: {summary.get('total_debit', 0)}")
                print(f"       - 贷方总额: {summary.get('total_credit', 0)}")

            return True
        else:
            print(f"[FAIL] API调用失败: {response.status_code}")
            print(f"       响应: {response.text[:200]}")
            return False

    except Exception as e:
        print(f"[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_financial_reports_home():
    """测试财务报表首页"""
    print()
    print("=" * 80)
    print("4. 测试财务报表首页")
    print("=" * 80)

    try:
        response = session.get(f"{BASE_URL}/finance/reports/")

        if response.status_code == 200:
            print(f"[OK] 财务报表首页访问成功")
            print(f"     页面大小: {len(response.text)} 字节")

            # 检查页面关键内容
            if "资产负债表" in response.text or "利润表" in response.text:
                print("[OK] 页面包含财务报表相关内容")
            else:
                print("[WARN] 页面可能缺少财务报表内容")

            return True
        else:
            print(f"[FAIL] 访问失败: {response.status_code}")
            return False

    except Exception as e:
        print(f"[ERROR] 测试失败: {e}")
        return False


def test_balance_sheet():
    """测试资产负债表生成"""
    print()
    print("=" * 80)
    print("5. 测试资产负债表生成")
    print("=" * 80)

    try:
        current_period = datetime.now().strftime('%Y-%m')
        print(f"     报表期间: {current_period}")

        response = session.get(
            f"{BASE_URL}/finance/reports/balance-sheet",
            params={"period": current_period}
        )

        if response.status_code == 200:
            print(f"[OK] 资产负债表生成成功")
            print(f"     页面大小: {len(response.text)} 字节")

            # 检查页面关键内容
            if "资产负债表" in response.text:
                print("[OK] 页面包含资产负债表内容")
            else:
                print("[WARN] 页面可能缺少资产负债表内容")

            return True
        else:
            print(f"[FAIL] 生成失败: {response.status_code}")
            print(f"       响应: {response.text[:500]}")
            return False

    except Exception as e:
        print(f"[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_voucher_list():
    """测试凭证列表"""
    print()
    print("=" * 80)
    print("6. 测试凭证管理")
    print("=" * 80)

    try:
        response = session.get(f"{BASE_URL}/finance/vouchers")

        if response.status_code == 200:
            print(f"[OK] 凭证列表访问成功")
            print(f"     页面大小: {len(response.text)} 字节")

            # 检查页面关键内容
            if "凭证" in response.text:
                print("[OK] 页面包含凭证列表内容")
            else:
                print("[WARN] 页面可能缺少凭证列表内容")

            return True
        else:
            print(f"[FAIL] 访问失败: {response.status_code}")
            return False

    except Exception as e:
        print(f"[ERROR] 测试失败: {e}")
        return False


def main():
    """主测试流程"""
    print("财务模块功能测试")
    print("测试时间:", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print()

    results = []

    # 1. 登录
    if not login():
        print("\n登录失败，无法继续测试")
        return False

    # 2. 测试期末处理首页
    results.append(("期末处理首页", test_period_closing_home()))

    # 3. 测试期末结账检查
    results.append(("期末结账检查", test_period_closing_check()))

    # 4. 测试财务报表首页
    results.append(("财务报表首页", test_financial_reports_home()))

    # 5. 测试资产负债表
    results.append(("资产负债表", test_balance_sheet()))

    # 6. 测试凭证列表
    results.append(("凭证管理", test_voucher_list()))

    # 输出测试结果
    print()
    print("=" * 80)
    print("测试结果汇总")
    print("=" * 80)

    passed = 0
    failed = 0

    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {test_name}")
        if result:
            passed += 1
        else:
            failed += 1

    print()
    print(f"通过: {passed}/{len(results)}")
    print(f"失败: {failed}/{len(results)}")
    print()

    if failed == 0:
        print("[SUCCESS] 所有测试通过!")
        return True
    else:
        print(f"[WARNING] {failed}个测试失败")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
