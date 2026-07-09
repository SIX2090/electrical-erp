"""
系统内部通知服务
提供创建、查询、标记已读等通知功能
"""

from datetime import datetime, timedelta
from flask import session, request


def create_notification(
    execute_db,
    title,
    message=None,
    user_id=None,
    category="system",
    severity="info",
    expires_at=None,
    action_url=None,
    related_type=None,
    related_id=None,
    query_db=None,
    execute_and_return=None,
):
    """
    创建系统通知

    Args:
        execute_db: 数据库执行函数
        title: 通知标题
        message: 通知内容（可选）
        user_id: 用户ID（None表示全局通知）
        category: 分类（security/backup/system/warning/info）
        severity: 严重级别（info/warning/error/critical）
        expires_at: 过期时间（可选）
        action_url: 操作链接（可选）
        related_type: 关联对象类型（可选）
        related_id: 关联对象ID（可选）
        execute_and_return: 可选，执行 INSERT 并返回 RETURNING 行

    Returns:
        int: 新创建的通知ID
    """
    insert_sql = """
        INSERT INTO system_notifications
        (user_id, title, message, category, severity, expires_at, action_url, related_type, related_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """
    params = (user_id, title, message, category, severity, expires_at, action_url, related_type, related_id)
    if execute_and_return is not None:
        row = execute_and_return(insert_sql, params)
        if row:
            return row.get("id") if isinstance(row, dict) else (row[0] if isinstance(row, (list, tuple)) and row else None)
        return None
    execute_db(insert_sql, params)
    # execute_db 不返回结果，回退查询获取通知ID
    if query_db and user_id:
        row = query_db(
            "SELECT id FROM system_notifications WHERE user_id=%s AND title=%s ORDER BY id DESC LIMIT 1",
            (user_id, title),
            one=True,
        )
        return row.get("id") if row else None
    return None


def create_notification_for_all_users(
    query_db,
    execute_db,
    title,
    message=None,
    category="system",
    severity="info",
    expires_at=None,
    action_url=None,
):
    """
    为所有用户创建通知

    Args:
        query_db: 数据库查询函数
        execute_db: 数据库执行函数
        title: 通知标题
        message: 通知内容
        category: 分类
        severity: 严重级别
        expires_at: 过期时间
        action_url: 操作链接

    Returns:
        int: 创建的通知数量
    """
    # 获取所有正常状态的用户
    users = query_db("SELECT id FROM users WHERE status = 'normal'")

    count = 0
    for user in users:
        create_notification(
            execute_db,
            title=title,
            message=message,
            user_id=user["id"],
            category=category,
            severity=severity,
            expires_at=expires_at,
            action_url=action_url,
        )
        count += 1

    return count


def get_unread_count(query_one, user_id):
    """
    获取用户未读通知数量

    Args:
        query_one: 数据库查询单行函数
        user_id: 用户ID

    Returns:
        int: 未读通知数量
    """
    result = query_one(
        """
        SELECT COUNT(*) as count
        FROM system_notifications
        WHERE (user_id = %s OR user_id IS NULL)
          AND is_read = FALSE
          AND (expires_at IS NULL OR expires_at > NOW())
        """,
        (user_id,),
    )
    return result["count"] if result else 0


def get_notifications(query_db, user_id, limit=50, offset=0, unread_only=False):
    """
    获取用户通知列表

    Args:
        query_db: 数据库查询函数
        user_id: 用户ID
        limit: 每页数量
        offset: 偏移量
        unread_only: 是否只查询未读通知

    Returns:
        list: 通知列表
    """
    unread_filter = "AND is_read = FALSE" if unread_only else ""

    notifications = query_db(
        f"""
        SELECT id, user_id, title, message, category, severity,
               is_read, read_at, created_at, expires_at, action_url,
               related_type, related_id
        FROM system_notifications
        WHERE (user_id = %s OR user_id IS NULL)
          AND (expires_at IS NULL OR expires_at > NOW())
          {unread_filter}
        ORDER BY is_read ASC, created_at DESC
        LIMIT %s OFFSET %s
        """,
        (user_id, limit, offset),
    )

    return notifications


def mark_as_read(execute_db, notification_id, user_id):
    """
    标记通知为已读

    Args:
        execute_db: 数据库执行函数
        notification_id: 通知ID
        user_id: 用户ID

    Returns:
        bool: 是否成功
    """
    execute_db(
        """
        UPDATE system_notifications
        SET is_read = TRUE, read_at = NOW()
        WHERE id = %s AND (user_id = %s OR user_id IS NULL)
        """,
        (notification_id, user_id),
    )
    return True


def mark_all_as_read(execute_db, user_id):
    """
    标记所有通知为已读

    Args:
        execute_db: 数据库执行函数
        user_id: 用户ID

    Returns:
        int: 标记的通知数量
    """
    result = execute_db(
        """
        UPDATE system_notifications
        SET is_read = TRUE, read_at = NOW()
        WHERE (user_id = %s OR user_id IS NULL)
          AND is_read = FALSE
          AND (expires_at IS NULL OR expires_at > NOW())
        """,
        (user_id,),
    )
    return result


def delete_notification(execute_db, notification_id, user_id):
    """
    删除通知

    Args:
        execute_db: 数据库执行函数
        notification_id: 通知ID
        user_id: 用户ID

    Returns:
        bool: 是否成功
    """
    execute_db(
        """
        DELETE FROM system_notifications
        WHERE id = %s AND (user_id = %s OR user_id IS NULL)
        """,
        (notification_id, user_id),
    )
    return True


def clean_expired_notifications(execute_db):
    """
    清理过期通知

    Args:
        execute_db: 数据库执行函数

    Returns:
        int: 清理的通知数量
    """
    result = execute_db(
        """
        DELETE FROM system_notifications
        WHERE expires_at IS NOT NULL AND expires_at <= NOW()
        """
    )
    return result


# 常用通知模板

def notify_password_expiring(execute_db, user_id, username, days_remaining):
    """密码即将过期通知"""
    return create_notification(
        execute_db,
        title=f"密码即将过期",
        message=f"您的密码将在 {days_remaining} 天后过期，请及时修改密码。",
        user_id=user_id,
        category="security",
        severity="warning",
        action_url="/users/change-password",
        expires_at=datetime.now() + timedelta(days=days_remaining + 1),
    )


def notify_backup_failed(execute_db, error_message):
    """备份失败通知（全局）"""
    return create_notification(
        execute_db,
        title="数据库备份失败",
        message=f"自动备份执行失败，请检查备份日志。错误信息：{error_message}",
        user_id=None,  # 全局通知
        category="backup",
        severity="error",
        action_url="/system/backups",
    )


def notify_disk_space_low(execute_db, disk_usage_percent):
    """磁盘空间不足通知（全局）"""
    return create_notification(
        execute_db,
        title="磁盘空间不足",
        message=f"系统磁盘使用率已达 {disk_usage_percent}%，请及时清理或扩容。",
        user_id=None,
        category="system",
        severity="warning" if disk_usage_percent < 90 else "error",
        action_url="/system/data-health",
    )


def notify_high_risk_operation(execute_db, user_id, operation_description):
    """高风险操作通知"""
    return create_notification(
        execute_db,
        title="高风险操作已执行",
        message=f"检测到高风险操作：{operation_description}",
        user_id=user_id,
        category="security",
        severity="warning",
        action_url="/system/operation-logs",
        expires_at=datetime.now() + timedelta(days=7),
    )


def notify_account_locked(execute_db, user_id, username, reason):
    """账号锁定通知"""
    return create_notification(
        execute_db,
        title="账号已被锁定",
        message=f"您的账号已被锁定。原因：{reason}。请联系管理员解锁。",
        user_id=user_id,
        category="security",
        severity="critical",
    )
