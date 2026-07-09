"""
直接测试财务模块服务层函数
绕过Web层，直接调用服务函数测试数据库交互
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from services.env_config import get_pg_password
from services.period_closing_service import (
    check_period_closing,
    get_current_period,
    get_latest_closed_period
)


def get_db_connection():
    """获取数据库连接"""
    PG_HOST = os.environ.get("PG_HOST", "127.0.0.1")
    PG_PORT = int(os.environ.get("PG_PORT", "5432"))
    PG_DATABASE = os.environ.get("PG_DATABASE", "wms")
    PG_USER = os.environ.get("PG_USER", "wms_user")
    PG_PASSWORD = get_pg_password()

    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        database=PG_DATABASE,
        user=PG_USER,
        password=PG_PASSWORD
    )


def query_db(sql, params=None, fetch_one=False, one=False):
    """数据库查询函数"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(sql, params or ())

        if fetch_one or one:
            result = cursor.fetchone()
        else:
            result = cursor.fetchall()

        return result
    finally:
        cursor.close()
        conn.close()


def test_current_period():
    """测试获取当前期间"""
    print("=" * 80)
    print("测试1: 获取当前期间")
    print("=" * 80)

    try:
        period = get_current_period()
        print(f"[OK] 当前期间: {period}")
        return True
    except Exception as e:
        print(f"[ERROR] 获取失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_latest_closed_period():
    """测试获取最近已结账期间"""
    print()
    print("=" * 80)
    print("测试2: 获取最近已结账期间")
    print("=" * 80)

    try:
        period = get_latest_closed_period(query_db)
        print(f"[OK] 最近已结账期间: {period if period else '无'}")
        return True
    except Exception as e:
        print(f"[ERROR] 获取失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_check_period_closing():
    """测试期末结账检查"""
    print()
    print("=" * 80)
    print("测试3: 期末结账检查")
    print("=" * 80)

    try:
        period = get_current_period()
        print(f"检查期间: {period}")

        result = check_period_closing(query_db, period)

        print(f"[OK] 检查完成")
        print(f"  是否可以结账: {result['can_close']}")
        print(f"  检查问题数: {len(result.get('issues', []))}")
        print(f"  警告数: {len(result.get('warnings', []))}")

        if result.get('issues'):
            print("\n  检查问题:")
            for issue in result['issues'][:5]:
                print(f"    - {issue.get('check_item')}: {issue.get('reason')}")

        if result.get('summary'):
            summary = result['summary']
            print(f"\n  汇总信息:")
            print(f"    - 凭证数量: {summary.get('voucher_count', 0)}")
            print(f"    - 未审核凭证: {summary.get('unreviewed_vouchers', 0)}")
            print(f"    - 借方总额: {summary.get('total_debit', 0)}")
            print(f"    - 贷方总额: {summary.get('total_credit', 0)}")
            print(f"    - 差额: {summary.get('balance_diff', 0)}")
            print(f"    - 收入: {summary.get('revenue', 0)}")
            print(f"    - 费用: {summary.get('expense', 0)}")
            print(f"    - 净利润: {summary.get('net_profit', 0)}")

        return True
    except Exception as e:
        print(f"[ERROR] 检查失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_table_structure():
    """测试关键表结构"""
    print()
    print("=" * 80)
    print("测试4: 验证表结构")
    print("=" * 80)

    try:
        # 检查vouchers表
        sql = """
            SELECT COUNT(*)
            FROM vouchers
            WHERE period_year IS NOT NULL
        """
        result = query_db(sql, fetch_one=True)
        print(f"[OK] vouchers表查询成功，记录数: {result[0]}")

        # 检查chart_of_accounts表
        sql = """
            SELECT COUNT(*)
            FROM chart_of_accounts
            WHERE is_active = TRUE
        """
        result = query_db(sql, fetch_one=True)
        print(f"[OK] chart_of_accounts表查询成功，记录数: {result[0]}")

        # 检查gl_account_balances表
        sql = """
            SELECT COUNT(*)
            FROM gl_account_balances
        """
        result = query_db(sql, fetch_one=True)
        print(f"[OK] gl_account_balances表查询成功，记录数: {result[0]}")

        # 检查voucher_lines表
        sql = """
            SELECT COUNT(*)
            FROM voucher_lines
        """
        result = query_db(sql, fetch_one=True)
        print(f"[OK] voucher_lines表查询成功，记录数: {result[0]}")

        return True
    except Exception as e:
        print(f"[ERROR] 表结构验证失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主测试流程"""
    print("财务模块服务层功能测试")
    print("直接测试数据库交互，绕过Web层")
    print()

    results = []

    results.append(("获取当前期间", test_current_period()))
    results.append(("获取最近已结账期间", test_latest_closed_period()))
    results.append(("验证表结构", test_table_structure()))
    results.append(("期末结账检查", test_check_period_closing()))

    # 输出测试结果
    print()
    print("=" * 80)
    print("测试结果汇总")
    print("=" * 80)

    passed = sum(1 for _, result in results if result)
    failed = len(results) - passed

    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {test_name}")

    print()
    print(f"通过: {passed}/{len(results)}")
    print(f"失败: {failed}/{len(results)}")
    print()

    if failed == 0:
        print("[SUCCESS] 所有测试通过!")
        print("\n修复的BUG总结:")
        print("  1. ✓ 表名统一 (gl_accounts → chart_of_accounts)")
        print("  2. ✓ 表名统一 (voucher_entries → voucher_lines)")
        print("  3. ✓ 字段名修正 (voucher_period → period_year/month)")
        print("  4. ✓ 字段名修正 (review_status → status)")
        print("  5. ✓ 字段名修正 (abstract → summary)")
        print("  6. ✓ execute_db参数传递修正")
        print("  7. ✓ gl_account_balances字段结构适配")
        return True
    else:
        print(f"[WARNING] {failed}个测试失败")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
