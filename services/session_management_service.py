"""
会话管理服务
"""

import logging
from datetime import datetime, timedelta
from flask import session, request

logger = logging.getLogger(__name__)


def create_session_record(execute_db, session_id, user_id, username, query_db=None):
    """
    创建会话记录

    Args:
        execute_db: 数据库执行函数
        session_id: 会话ID
        user_id: 用户ID
        username: 用户名
        query_db: 数据库查询函数（可选，用于回退查询会话ID）

    Returns:
        int: 会话记录ID
    """
    ip_address = request.remote_addr if request else None
    user_agent = request.headers.get("User-Agent", "") if request else ""

    execute_db(
        """
        INSERT INTO user_sessions
        (session_id, user_id, username, ip_address, user_agent, created_at, last_activity, is_active)
        VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), TRUE)
        RETURNING id
        """,
        (session_id, user_id, username, ip_address, user_agent),
    )

    # execute_db 不返回结果，回退查询获取会话ID
    if query_db:
        row = query_db(
            "SELECT id FROM user_sessions WHERE session_id=%s ORDER BY id DESC LIMIT 1",
            (session_id,),
            one=True,
        )
        return row.get("id") if row else None
    return None


def update_session_activity(execute_db, session_id):
    """
    更新会话活动时间

    Args:
        execute_db: 数据库执行函数
        session_id: 会话ID
    """
    execute_db(
        """
        UPDATE user_sessions
        SET last_activity = NOW()
        WHERE session_id = %s AND is_active = TRUE
        """,
        (session_id,),
    )


def get_active_sessions(query_db, user_id=None):
    """
    获取活跃会话列表

    Args:
        query_db: 数据库查询函数
        user_id: 用户ID（可选，为空则查询所有）

    Returns:
        list: 会话列表
    """
    if user_id:
        try:
            sessions = query_db(
                """
                SELECT id, session_id, user_id, username, ip_address, user_agent,
                       created_at, last_activity, is_active
                FROM user_sessions
                WHERE user_id = %s AND is_active = TRUE
                ORDER BY last_activity DESC
                """,
                (user_id,),
            )
        except Exception:
            logger.warning("get_active_sessions(user_id=%s) failed", user_id, exc_info=True)
            sessions = []
    else:
        try:
            sessions = query_db(
                """
                SELECT id, session_id, user_id, username, ip_address, user_agent,
                       created_at, last_activity, is_active
                FROM user_sessions
                WHERE is_active = TRUE
                ORDER BY last_activity DESC
                """
            )
        except Exception:
            logger.warning("get_active_sessions(all) failed", exc_info=True)
            sessions = []

    return sessions


def get_all_sessions(query_db, limit=100, offset=0):
    """
    获取所有会话（包括已过期）

    Args:
        query_db: 数据库查询函数
        limit: 每页数量
        offset: 偏移量

    Returns:
        list: 会话列表
    """
    try:
        sessions = query_db(
            """
            SELECT id, session_id, user_id, username, ip_address, user_agent,
                   created_at, last_activity, is_active, expires_at, logout_reason
            FROM user_sessions
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )
    except Exception:
        logger.warning("get_all_sessions failed", exc_info=True)
        sessions = []

    return sessions


def get_session_by_id(query_one, session_id):
    """
    根据会话ID获取会话信息

    Args:
        query_one: 数据库查询单行函数
        session_id: 会话ID

    Returns:
        dict: 会话信息
    """
    try:
        session_info = query_one(
            """
            SELECT id, session_id, user_id, username, ip_address, user_agent,
                   created_at, last_activity, is_active, expires_at, logout_reason
            FROM user_sessions
            WHERE session_id = %s
            """,
            (session_id,),
        )
    except Exception:
        logger.warning("get_session_by_id failed for session_id=%s", session_id, exc_info=True)
        session_info = None

    return session_info


def terminate_session(execute_db, session_id, logout_reason="管理员强制终止"):
    """
    终止会话

    Args:
        execute_db: 数据库执行函数
        session_id: 会话ID
        logout_reason: 退出原因

    Returns:
        bool: 是否成功
    """
    execute_db(
        """
        UPDATE user_sessions
        SET is_active = FALSE,
            logout_reason = %s,
            expires_at = NOW()
        WHERE session_id = %s
        """,
        (logout_reason, session_id),
    )

    return True


def terminate_user_sessions(execute_db, user_id, exclude_session_id=None, logout_reason="其他设备登录"):
    """
    终止用户的所有会话（可排除当前会话）

    Args:
        execute_db: 数据库执行函数
        user_id: 用户ID
        exclude_session_id: 排除的会话ID（通常是当前会话）
        logout_reason: 退出原因

    Returns:
        int: 终止的会话数量
    """
    if exclude_session_id:
        result = execute_db(
            """
            UPDATE user_sessions
            SET is_active = FALSE,
                logout_reason = %s,
                expires_at = NOW()
            WHERE user_id = %s
              AND session_id != %s
              AND is_active = TRUE
            """,
            (logout_reason, user_id, exclude_session_id),
        )
    else:
        result = execute_db(
            """
            UPDATE user_sessions
            SET is_active = FALSE,
                logout_reason = %s,
                expires_at = NOW()
            WHERE user_id = %s
              AND is_active = TRUE
            """,
            (logout_reason, user_id),
        )

    return result


def clean_expired_sessions(execute_db, inactive_hours=24):
    """
    清理过期会话（超过指定时间无活动）

    Args:
        execute_db: 数据库执行函数
        inactive_hours: 无活动小时数

    Returns:
        int: 清理的会话数量
    """
    result = execute_db(
        """
        UPDATE user_sessions
        SET is_active = FALSE,
            logout_reason = '会话超时',
            expires_at = NOW()
        WHERE is_active = TRUE
          AND last_activity < NOW() - INTERVAL '%s hours'
        """,
        (inactive_hours,),
    )

    return result


def get_user_concurrent_sessions_count(query_one, user_id):
    """
    获取用户当前并发会话数量

    Args:
        query_one: 数据库查询单行函数
        user_id: 用户ID

    Returns:
        int: 并发会话数量
    """
    try:
        result = query_one(
            """
            SELECT COUNT(*) as count
            FROM user_sessions
            WHERE user_id = %s AND is_active = TRUE
            """,
            (user_id,),
        )
    except Exception:
        logger.warning("get_user_concurrent_sessions_count failed for user_id=%s", user_id, exc_info=True)
        result = None

    return result["count"] if result else 0


def check_session_limit(query_one, user_id, max_sessions=3):
    """
    检查用户是否超过并发会话限制

    Args:
        query_one: 数据库查询单行函数
        user_id: 用户ID
        max_sessions: 最大并发会话数

    Returns:
        tuple: (是否超限, 当前会话数)
    """
    count = get_user_concurrent_sessions_count(query_one, user_id)
    return (count >= max_sessions, count)


def get_session_statistics(query_one):
    """
    获取会话统计信息

    Returns:
        dict: 统计信息
    """
    try:
        stats = query_one(
            """
            SELECT
                COUNT(*) FILTER (WHERE is_active = TRUE) as active_count,
                COUNT(*) FILTER (WHERE is_active = FALSE) as inactive_count,
                COUNT(*) as total_count,
                COUNT(DISTINCT user_id) FILTER (WHERE is_active = TRUE) as active_users
            FROM user_sessions
            """
        )
    except Exception:
        logger.warning("get_session_statistics failed", exc_info=True)
        stats = None

    return stats or {
        "active_count": 0,
        "inactive_count": 0,
        "total_count": 0,
        "active_users": 0,
    }


def get_login_history(query_db, user_id=None, limit=50):
    """
    获取登录历史

    Args:
        query_db: 数据库查询函数
        user_id: 用户ID（可选）
        limit: 返回记录数

    Returns:
        list: 登录历史
    """
    if user_id:
        try:
            history = query_db(
                """
                SELECT session_id, username, ip_address, user_agent,
                       created_at, last_activity, is_active, logout_reason
                FROM user_sessions
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (user_id, limit),
            )
        except Exception:
            logger.warning("get_login_history(user_id=%s) failed", user_id, exc_info=True)
            history = []
    else:
        try:
            history = query_db(
                """
                SELECT session_id, user_id, username, ip_address, user_agent,
                       created_at, last_activity, is_active, logout_reason
                FROM user_sessions
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
        except Exception:
            logger.warning("get_login_history(all) failed", exc_info=True)
            history = []

    return history
