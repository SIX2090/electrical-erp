"""
账号锁定管理服务
"""

import logging
from datetime import datetime, timedelta
from flask import session, request

logger = logging.getLogger(__name__)


def get_locked_accounts(query_db):
    """
    获取被锁定的账号列表

    Returns:
        list: 锁定账号列表
    """
    try:
        accounts = query_db(
            """
            SELECT id, username, role, status, locked_at, locked_reason,
                   failed_login_count, last_login_at, last_login_ip
            FROM users
            WHERE locked_at IS NOT NULL
            ORDER BY locked_at DESC
            """
        )
    except Exception:
        logger.warning("get_locked_accounts failed", exc_info=True)
        accounts = []
    return accounts


def get_login_failures(query_db, username=None, limit=100):
    """
    获取登录失败记录

    Args:
        query_db: 数据库查询函数
        username: 用户名（可选，为空则查询所有）
        limit: 返回记录数

    Returns:
        list: 失败登录记录
    """
    if username:
        try:
            records = query_db(
                """
                SELECT username, failures, locked_until, updated_at
                FROM login_attempts
                WHERE username = %s
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (username, limit),
            )
        except Exception:
            logger.warning("get_login_failures(username=%s) failed", username, exc_info=True)
            records = []
    else:
        try:
            records = query_db(
                """
                SELECT username, failures, locked_until, updated_at
                FROM login_attempts
                WHERE failures > 0
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (limit,),
            )
        except Exception:
            logger.warning("get_login_failures(all) failed", exc_info=True)
            records = []
    return records


def unlock_account(query_db, execute_db, user_id, unlock_reason=None):
    """
    解锁账号

    Args:
        query_db: 数据库查询函数
        execute_db: 数据库执行函数
        user_id: 用户ID
        unlock_reason: 解锁原因

    Returns:
        bool: 是否成功
    """
    # 清除用户表的锁定信息
    execute_db(
        """
        UPDATE users
        SET locked_at = NULL,
            locked_reason = NULL,
            failed_login_count = 0
        WHERE id = %s
        """,
        (user_id,),
    )

    # 清除 login_attempts 表的锁定信息
    username_row = query_db(
        "SELECT username FROM users WHERE id = %s",
        (user_id,),
        one=True,
    )

    if username_row:
        username = username_row.get("username") if isinstance(username_row, dict) else (username_row[0] if username_row else None)
        if username:
            execute_db(
                """
                UPDATE login_attempts
                SET failures = 0,
                    locked_until = NULL,
                    updated_at = NOW()
                WHERE username = %s
                """,
                (username,),
            )

    return True


def lock_account(query_db, execute_db, user_id, lock_reason, duration_minutes=None):
    """
    锁定账号

    Args:
        query_db: 数据库查询函数
        execute_db: 数据库执行函数
        user_id: 用户ID
        lock_reason: 锁定原因
        duration_minutes: 锁定时长（分钟），None 表示永久锁定

    Returns:
        bool: 是否成功
    """
    execute_db(
        """
        UPDATE users
        SET locked_at = NOW(),
            locked_reason = %s
        WHERE id = %s
        """,
        (lock_reason, user_id),
    )

    # 如果指定了锁定时长，更新 login_attempts 表
    if duration_minutes:
        username_row = query_db(
            "SELECT username FROM users WHERE id = %s",
            (user_id,),
            one=True,
        )

        if username_row:
            username = username_row.get("username") if isinstance(username_row, dict) else (username_row[0] if username_row else None)
            if username:
                locked_until = datetime.now() + timedelta(minutes=duration_minutes)
                execute_db(
                    """
                    INSERT INTO login_attempts (username, failures, locked_until, updated_at)
                    VALUES (%s, 999, %s, NOW())
                    ON CONFLICT (username) DO UPDATE
                    SET failures = 999,
                        locked_until = EXCLUDED.locked_until,
                        updated_at = NOW()
                    """,
                    (username, locked_until),
                )

    return True


def check_auto_unlock(query_db, execute_db):
    """
    检查并自动解锁到期的账号

    Args:
        query_db: 数据库查询函数
        execute_db: 数据库执行函数

    Returns:
        int: 解锁的账号数量
    """
    # 查询 login_attempts 中锁定已过期的用户
    expired_locks = query_db(
        """
        SELECT username
        FROM login_attempts
        WHERE locked_until IS NOT NULL
          AND locked_until <= NOW()
        """
    )

    count = 0
    for lock in expired_locks:
        username = lock["username"]

        # 清除 login_attempts 锁定
        execute_db(
            """
            UPDATE login_attempts
            SET failures = 0,
                locked_until = NULL,
                updated_at = NOW()
            WHERE username = %s
            """,
            (username,),
        )

        # 清除 users 表锁定
        execute_db(
            """
            UPDATE users
            SET locked_at = NULL,
                locked_reason = NULL,
                failed_login_count = 0
            WHERE username = %s
            """,
            (username,),
        )

        count += 1

    return count


def get_account_lock_statistics(query_one):
    """
    获取账号锁定统计

    Returns:
        dict: 统计信息
    """
    try:
        stats = query_one(
            """
            SELECT
                COUNT(*) FILTER (WHERE locked_at IS NOT NULL) as locked_count,
                COUNT(*) FILTER (WHERE failed_login_count > 0) as failed_login_count,
                COUNT(*) as total_count
            FROM users
            """
        )
    except Exception:
        stats = query_one("SELECT COUNT(*) as total_count FROM users")
        if stats:
            stats["locked_count"] = 0
            stats["failed_login_count"] = 0

    return stats or {
        "locked_count": 0,
        "failed_login_count": 0,
        "total_count": 0,
    }
