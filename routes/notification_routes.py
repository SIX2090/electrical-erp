"""
系统通知路由
"""

from flask import Blueprint, render_template, jsonify, redirect, request, session, current_app, g, url_for
from services.notification_service import (
    get_unread_count,
    get_notifications,
    mark_as_read,
    mark_all_as_read,
    delete_notification,
)

bp = Blueprint("notifications", __name__, url_prefix="/notifications")


def _get_db_helpers():
    """获取数据库辅助函数"""
    if not hasattr(g, '_notification_db_helpers'):
        from services.app_runtime import create_db_helpers
        db_config = {
            "host": current_app.config.get("PG_HOST", "127.0.0.1"),
            "port": current_app.config.get("PG_PORT", 5432),
            "database": current_app.config.get("PG_DATABASE", "wms"),
            "user": current_app.config.get("PG_USER", "wms_user"),
            "password": current_app.config.get("PG_PASSWORD", "admin"),
        }
        _get_db, query_db, execute_db, execute_and_return = create_db_helpers(current_app, db_config)
        g._notification_db_helpers = (query_db, execute_db)
    return g._notification_db_helpers


def query_db(sql, params=None, one=False):
    """查询数据库"""
    qdb, _ = _get_db_helpers()
    return qdb(sql, params, one=one)


def query_one(sql, params=None):
    """查询单行"""
    return query_db(sql, params, one=True)


def execute_db(sql, params=None):
    """执行数据库语句"""
    _, edb = _get_db_helpers()
    return edb(sql, params)


@bp.route("/")
def notification_list():
    """通知列表页面"""
    if not session.get("user_id"):
        return redirect(url_for("login", next=request.path))
    return render_template("notifications/list.html")


@bp.route("/api/unread-count")
def api_unread_count():
    """获取未读通知数量"""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error", "msg": "未登录"}), 401

    count = get_unread_count(query_one, user_id)
    return jsonify({"status": "success", "unread_count": count})


@bp.route("/api/list")
def api_notification_list():
    """获取通知列表"""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error", "msg": "未登录"}), 401

    try:
        limit = int(request.args.get("limit", 50))
    except (TypeError, ValueError):
        limit = 50
    try:
        offset = int(request.args.get("offset", 0))
    except (TypeError, ValueError):
        offset = 0
    unread_only = request.args.get("unread_only", "false").lower() == "true"

    notifications = get_notifications(query_db, user_id, limit, offset, unread_only)

    # 格式化时间
    for n in notifications:
        if n.get("created_at"):
            n["created_at"] = n["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        if n.get("read_at"):
            n["read_at"] = n["read_at"].strftime("%Y-%m-%d %H:%M:%S")
        if n.get("expires_at"):
            n["expires_at"] = n["expires_at"].strftime("%Y-%m-%d %H:%M:%S")

    return jsonify({"status": "success", "notifications": notifications})


@bp.route("/api/<int:notification_id>/read", methods=["POST"])
def api_mark_as_read(notification_id):
    """标记通知为已读"""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error", "msg": "未登录"}), 401

    mark_as_read(execute_db, notification_id, user_id)
    return jsonify({"status": "success", "msg": "已标记为已读"})


@bp.route("/api/read-all", methods=["POST"])
def api_mark_all_as_read():
    """全部标记为已读"""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error", "msg": "未登录"}), 401

    mark_all_as_read(execute_db, user_id)
    return jsonify({"status": "success", "msg": "所有通知已标记为已读"})


@bp.route("/api/<int:notification_id>", methods=["DELETE"])
def api_delete_notification(notification_id):
    """删除通知"""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error", "msg": "未登录"}), 401

    delete_notification(execute_db, notification_id, user_id)
    return jsonify({"status": "success", "msg": "通知已删除"})
