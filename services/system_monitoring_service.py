"""
系统监控服务
提供系统资源监控、性能指标和健康检查
"""

import logging
import psutil
import os
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


def get_cpu_usage():
    """
    获取CPU使用率

    Returns:
        dict: CPU使用率信息
    """
    cpu_percent = psutil.cpu_percent(interval=1)
    cpu_count = psutil.cpu_count()
    cpu_freq = psutil.cpu_freq()

    return {
        "percent": cpu_percent,
        "count": cpu_count,
        "freq_current": cpu_freq.current if cpu_freq else None,
        "freq_max": cpu_freq.max if cpu_freq else None,
        "status": "normal" if cpu_percent < 80 else "warning" if cpu_percent < 90 else "critical",
    }


def get_memory_usage():
    """
    获取内存使用情况

    Returns:
        dict: 内存使用信息
    """
    mem = psutil.virtual_memory()

    return {
        "total": mem.total,
        "available": mem.available,
        "used": mem.used,
        "percent": mem.percent,
        "total_gb": round(mem.total / (1024**3), 2),
        "used_gb": round(mem.used / (1024**3), 2),
        "available_gb": round(mem.available / (1024**3), 2),
        "status": "normal" if mem.percent < 80 else "warning" if mem.percent < 90 else "critical",
    }


def get_disk_usage(path=None):
    """
    获取磁盘使用情况

    Args:
        path: 磁盘路径（默认当前目录所在磁盘）

    Returns:
        dict: 磁盘使用信息
    """
    if path is None:
        path = os.getcwd()

    disk = psutil.disk_usage(path)

    return {
        "path": path,
        "total": disk.total,
        "used": disk.used,
        "free": disk.free,
        "percent": disk.percent,
        "total_gb": round(disk.total / (1024**3), 2),
        "used_gb": round(disk.used / (1024**3), 2),
        "free_gb": round(disk.free / (1024**3), 2),
        "status": "normal" if disk.percent < 80 else "warning" if disk.percent < 90 else "critical",
    }


def get_database_connection_count(query_one):
    """
    获取数据库连接数

    Args:
        query_one: 数据库查询单行函数

    Returns:
        dict: 数据库连接信息
    """
    try:
        result = query_one(
            """
            SELECT
                count(*) as total_connections,
                count(*) FILTER (WHERE state = 'active') as active_connections,
                count(*) FILTER (WHERE state = 'idle') as idle_connections
            FROM pg_stat_activity
            WHERE datname = current_database()
            """
        )

        return {
            "total": result["total_connections"] if result else 0,
            "active": result["active_connections"] if result else 0,
            "idle": result["idle_connections"] if result else 0,
            "status": "normal",
        }
    except Exception as e:
        return {
            "total": 0,
            "active": 0,
            "idle": 0,
            "status": "error",
            "error": str(e),
        }


def get_database_size(query_one):
    """
    获取数据库大小

    Args:
        query_one: 数据库查询单行函数

    Returns:
        dict: 数据库大小信息
    """
    try:
        result = query_one(
            """
            SELECT pg_database_size(current_database()) as size_bytes
            """
        )

        size_bytes = result["size_bytes"] if result else 0
        size_mb = round(size_bytes / (1024**2), 2)
        size_gb = round(size_bytes / (1024**3), 2)

        return {
            "size_bytes": size_bytes,
            "size_mb": size_mb,
            "size_gb": size_gb,
            "status": "normal",
        }
    except Exception as e:
        return {
            "size_bytes": 0,
            "size_mb": 0,
            "size_gb": 0,
            "status": "error",
            "error": str(e),
        }


def get_slow_queries(query_db, threshold_seconds=3):
    """
    获取慢查询列表

    Args:
        query_db: 数据库查询函数
        threshold_seconds: 慢查询阈值（秒）

    Returns:
        list: 慢查询列表
    """
    try:
        queries = query_db(
            """
            SELECT
                pid,
                usename,
                application_name,
                client_addr,
                state,
                query,
                now() - query_start as duration
            FROM pg_stat_activity
            WHERE state = 'active'
              AND query NOT ILIKE '%pg_stat_activity%'
              AND now() - query_start > interval '%s seconds'
            ORDER BY duration DESC
            LIMIT 10
            """,
            (threshold_seconds,),
        )

        return queries or []
    except Exception as e:
        logger.warning("get_slow_queries failed: %s", e, exc_info=True)
        return []


def get_table_sizes(query_db, limit=10):
    """
    获取数据库表大小统计

    Args:
        query_db: 数据库查询函数
        limit: 返回前N个最大的表

    Returns:
        list: 表大小列表
    """
    try:
        tables = query_db(
            """
            SELECT
                schemaname,
                tablename,
                pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
                pg_total_relation_size(schemaname||'.'||tablename) as size_bytes
            FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY size_bytes DESC
            LIMIT %s
            """,
            (limit,),
        )

        return tables or []
    except Exception as e:
        logger.warning("get_table_sizes failed: %s", e, exc_info=True)
        return []


def get_active_user_count(query_one):
    """
    获取当前活跃用户数

    Args:
        query_one: 数据库查询单行函数

    Returns:
        int: 活跃用户数
    """
    try:
        result = query_one(
            """
            SELECT COUNT(DISTINCT user_id) as count
            FROM user_sessions
            WHERE is_active = TRUE
              AND last_activity > NOW() - INTERVAL '30 minutes'
            """
        )

        return result["count"] if result else 0
    except Exception as e:
        logger.warning("get_active_user_count failed: %s", e, exc_info=True)
        return 0


def get_recent_error_logs(query_db, hours=24, limit=50):
    """
    获取最近的错误日志

    Args:
        query_db: 数据库查询函数
        hours: 最近N小时
        limit: 返回记录数

    Returns:
        list: 错误日志列表
    """
    try:
        logs = query_db(
            """
            SELECT id, username, action, target, remark, created_at, severity
            FROM operation_logs
            WHERE severity IN ('error', 'critical')
              AND created_at > NOW() - make_interval(hours => %s)
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (hours, limit),
        )

        return logs or []
    except Exception as e:
        logger.warning("get_recent_error_logs failed: %s", e, exc_info=True)
        return []


def get_system_uptime():
    """
    获取系统运行时间

    Returns:
        dict: 系统运行时间信息
    """
    boot_time = psutil.boot_time()
    uptime_seconds = datetime.now().timestamp() - boot_time

    days = int(uptime_seconds // 86400)
    hours = int((uptime_seconds % 86400) // 3600)
    minutes = int((uptime_seconds % 3600) // 60)

    return {
        "boot_time": datetime.fromtimestamp(boot_time),
        "uptime_seconds": int(uptime_seconds),
        "uptime_days": days,
        "uptime_hours": hours,
        "uptime_minutes": minutes,
        "uptime_text": f"{days}天 {hours}小时 {minutes}分钟",
    }


def get_process_info():
    """
    获取当前进程信息

    Returns:
        dict: 进程信息
    """
    process = psutil.Process(os.getpid())

    return {
        "pid": process.pid,
        "name": process.name(),
        "status": process.status(),
        "cpu_percent": process.cpu_percent(interval=0.1),
        "memory_mb": round(process.memory_info().rss / (1024**2), 2),
        "num_threads": process.num_threads(),
        "create_time": datetime.fromtimestamp(process.create_time()),
    }


def get_backup_status(query_db):
    """
    获取备份状态

    Args:
        query_db: 数据库查询函数

    Returns:
        dict: 备份状态信息
    """
    # 这里假设有备份日志表，根据实际情况调整
    # 如果没有备份日志表，可以检查备份文件目录
    try:
        backup_dir = Path("backups")
        if backup_dir.exists():
            backup_files = sorted(backup_dir.glob("*.dump"), key=lambda x: x.stat().st_mtime, reverse=True)

            if backup_files:
                latest_backup = backup_files[0]
                backup_time = datetime.fromtimestamp(latest_backup.stat().st_mtime)
                hours_since_backup = (datetime.now() - backup_time).total_seconds() / 3600

                return {
                    "has_backup": True,
                    "latest_backup": latest_backup.name,
                    "backup_time": backup_time,
                    "hours_since_backup": round(hours_since_backup, 1),
                    "backup_size_mb": round(latest_backup.stat().st_size / (1024**2), 2),
                    "status": "normal" if hours_since_backup < 24 else "warning" if hours_since_backup < 72 else "critical",
                }

        return {
            "has_backup": False,
            "status": "critical",
            "message": "未找到备份文件",
        }
    except Exception as e:
        return {
            "has_backup": False,
            "status": "error",
            "error": str(e),
        }


def get_all_system_metrics(query_db, query_one):
    """
    获取所有系统指标（综合监控面板）

    Args:
        query_db: 数据库查询函数
        query_one: 数据库查询单行函数

    Returns:
        dict: 所有系统指标
    """
    return {
        "timestamp": datetime.now(),
        "cpu": get_cpu_usage(),
        "memory": get_memory_usage(),
        "disk": get_disk_usage(),
        "database": {
            "connections": get_database_connection_count(query_one),
            "size": get_database_size(query_one),
            "slow_queries": get_slow_queries(query_db),
            "table_sizes": get_table_sizes(query_db, limit=5),
        },
        "application": {
            "active_users": get_active_user_count(query_one),
            "recent_errors": get_recent_error_logs(query_db, hours=1, limit=10),
            "process": get_process_info(),
        },
        "system": {
            "uptime": get_system_uptime(),
            "backup": get_backup_status(query_db),
        },
    }


def check_system_health(query_db, query_one):
    """
    系统健康检查

    Args:
        query_db: 数据库查询函数
        query_one: 数据库查询单行函数

    Returns:
        dict: 健康检查结果
    """
    issues = []
    warnings = []

    # CPU 检查
    cpu = get_cpu_usage()
    if cpu["status"] == "critical":
        issues.append(f"CPU 使用率过高: {cpu['percent']}%")
    elif cpu["status"] == "warning":
        warnings.append(f"CPU 使用率偏高: {cpu['percent']}%")

    # 内存检查
    memory = get_memory_usage()
    if memory["status"] == "critical":
        issues.append(f"内存使用率过高: {memory['percent']}%")
    elif memory["status"] == "warning":
        warnings.append(f"内存使用率偏高: {memory['percent']}%")

    # 磁盘检查
    disk = get_disk_usage()
    if disk["status"] == "critical":
        issues.append(f"磁盘空间不足: {disk['percent']}%")
    elif disk["status"] == "warning":
        warnings.append(f"磁盘空间偏低: {disk['percent']}%")

    # 备份检查
    backup = get_backup_status(query_db)
    if backup["status"] == "critical":
        issues.append("备份过期或缺失")
    elif backup["status"] == "warning":
        warnings.append(f"备份时间过长: {backup.get('hours_since_backup', 0)} 小时")

    # 慢查询检查
    slow_queries = get_slow_queries(query_db)
    if len(slow_queries) > 0:
        warnings.append(f"检测到 {len(slow_queries)} 个慢查询")

    # 综合健康状态
    if len(issues) > 0:
        status = "critical"
    elif len(warnings) > 0:
        status = "warning"
    else:
        status = "healthy"

    return {
        "status": status,
        "issues": issues,
        "warnings": warnings,
        "timestamp": datetime.now(),
    }
