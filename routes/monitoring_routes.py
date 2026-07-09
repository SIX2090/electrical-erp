"""
系统监控路由
"""

from flask import Blueprint, render_template, jsonify, request, current_app, g
from services.app_runtime import connect_db
from services.system_monitoring_service import (
    get_cpu_usage,
    get_memory_usage,
    get_disk_usage,
    get_database_connection_count,
    get_database_size,
    get_slow_queries,
    get_table_sizes,
    get_active_user_count,
    get_recent_error_logs,
    get_system_uptime,
    get_process_info,
    get_backup_status,
    get_all_system_metrics,
    check_system_health,
)

bp = Blueprint("monitoring", __name__, url_prefix="/monitoring")


def _db_config():
    return {
        "host": current_app.config.get("PG_HOST", "127.0.0.1"),
        "port": current_app.config.get("PG_PORT", 5432),
        "database": current_app.config.get("PG_DATABASE", "wms"),
        "user": current_app.config.get("PG_USER", "wms_user"),
        "password": current_app.config.get("PG_PASSWORD", "admin"),
    }


def _get_db_helpers():
    """获取数据库辅助函数"""
    if not hasattr(g, '_monitoring_db_helpers'):
        from services.app_runtime import create_db_helpers
        db_config = {
            "host": current_app.config.get("PG_HOST", "127.0.0.1"),
            "port": current_app.config.get("PG_PORT", 5432),
            "database": current_app.config.get("PG_DATABASE", "wms"),
            "user": current_app.config.get("PG_USER", "wms_user"),
            "password": current_app.config.get("PG_PASSWORD", "admin"),
        }
        _get_db, query_db, execute_db, execute_and_return = create_db_helpers(current_app, db_config)
        g._monitoring_db_helpers = (query_db, execute_db)
    return g._monitoring_db_helpers


def query_db(sql, params=None, one=False):
    """查询数据库"""
    conn = connect_db(_db_config())
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            rows = cur.fetchall()
            if one:
                return rows[0] if rows else None
            return rows
    finally:
        conn.close()


def query_one(sql, params=None):
    """查询单行"""
    return query_db(sql, params, one=True)


@bp.route("/")
def monitoring_dashboard():
    """系统监控面板"""
    return render_template("monitoring/dashboard.html")


@bp.route("/api/metrics")
def api_metrics():
    """获取所有系统指标"""
    metrics = get_all_system_metrics(query_db, query_one)

    # 格式化时间
    if metrics.get("timestamp"):
        metrics["timestamp"] = metrics["timestamp"].strftime("%Y-%m-%d %H:%M:%S")

    if metrics.get("system", {}).get("uptime", {}).get("boot_time"):
        metrics["system"]["uptime"]["boot_time"] = metrics["system"]["uptime"]["boot_time"].strftime("%Y-%m-%d %H:%M:%S")

    if metrics.get("system", {}).get("backup", {}).get("backup_time"):
        metrics["system"]["backup"]["backup_time"] = metrics["system"]["backup"]["backup_time"].strftime("%Y-%m-%d %H:%M:%S")

    if metrics.get("application", {}).get("process", {}).get("create_time"):
        metrics["application"]["process"]["create_time"] = metrics["application"]["process"]["create_time"].strftime("%Y-%m-%d %H:%M:%S")

    return jsonify({"status": "success", "metrics": metrics})


@bp.route("/api/cpu")
def api_cpu():
    """获取CPU使用率"""
    cpu = get_cpu_usage()
    return jsonify({"status": "success", "cpu": cpu})


@bp.route("/api/memory")
def api_memory():
    """获取内存使用情况"""
    memory = get_memory_usage()
    return jsonify({"status": "success", "memory": memory})


@bp.route("/api/disk")
def api_disk():
    """获取磁盘使用情况"""
    path = request.args.get("path")
    disk = get_disk_usage(path)
    return jsonify({"status": "success", "disk": disk})


@bp.route("/api/database")
def api_database():
    """获取数据库信息"""
    database = {
        "connections": get_database_connection_count(query_one),
        "size": get_database_size(query_one),
        "slow_queries": get_slow_queries(query_db),
        "table_sizes": get_table_sizes(query_db),
    }
    return jsonify({"status": "success", "database": database})


@bp.route("/api/health")
def api_health():
    """系统健康检查"""
    health = check_system_health(query_db, query_one)

    if health.get("timestamp"):
        health["timestamp"] = health["timestamp"].strftime("%Y-%m-%d %H:%M:%S")

    return jsonify({"status": "success", "health": health})
