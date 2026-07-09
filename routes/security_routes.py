"""
安全管理路由
账号锁定、会话管理
"""

from flask import Blueprint, render_template, jsonify, request, current_app, g
from services.app_runtime import connect_db
from services.account_lock_service import (
    get_locked_accounts,
    get_login_failures,
    unlock_account,
    lock_account,
    check_auto_unlock,
    get_account_lock_statistics,
)
from services.session_management_service import (
    get_active_sessions,
    get_all_sessions,
    get_session_by_id,
    terminate_session,
    terminate_user_sessions,
    clean_expired_sessions,
    get_session_statistics,
    get_login_history,
)

bp = Blueprint("security", __name__, url_prefix="/security")


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
    if not hasattr(g, '_security_db_helpers'):
        from services.app_runtime import create_db_helpers
        db_config = {
            "host": current_app.config.get("PG_HOST", "127.0.0.1"),
            "port": current_app.config.get("PG_PORT", 5432),
            "database": current_app.config.get("PG_DATABASE", "wms"),
            "user": current_app.config.get("PG_USER", "wms_user"),
            "password": current_app.config.get("PG_PASSWORD", "admin"),
        }
        _get_db, query_db, execute_db, execute_and_return = create_db_helpers(current_app, db_config)
        g._security_db_helpers = (query_db, execute_db)
    return g._security_db_helpers


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


def execute_db(sql, params=None):
    """执行数据库语句"""
    conn = connect_db(_db_config())
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
        conn.commit()
    finally:
        conn.close()


# ============ 账号锁定管理 ============

@bp.route("/locked-accounts")
def locked_accounts_page():
    """被锁定账号列表页面"""
    return render_template("security/locked_accounts.html")


@bp.route("/api/locked-accounts")
def api_locked_accounts():
    """获取被锁定账号列表"""
    accounts = get_locked_accounts(query_db)

    # 格式化时间
    for acc in accounts:
        if acc.get("locked_at"):
            acc["locked_at"] = acc["locked_at"].strftime("%Y-%m-%d %H:%M:%S")
        if acc.get("last_login_at"):
            acc["last_login_at"] = acc["last_login_at"].strftime("%Y-%m-%d %H:%M:%S")

    return jsonify({"status": "success", "accounts": accounts})


@bp.route("/api/login-failures")
def api_login_failures():
    """获取登录失败记录"""
    username = request.args.get("username")
    try:
        limit = int(request.args.get("limit", 100))
    except (TypeError, ValueError):
        limit = 100

    records = get_login_failures(query_db, username, limit)

    # 格式化时间
    for rec in records:
        if rec.get("updated_at"):
            rec["updated_at"] = rec["updated_at"].strftime("%Y-%m-%d %H:%M:%S")
        if rec.get("locked_until"):
            rec["locked_until"] = rec["locked_until"].strftime("%Y-%m-%d %H:%M:%S")

    return jsonify({"status": "success", "records": records})


@bp.route("/api/unlock-account/<int:user_id>", methods=["POST"])
def api_unlock_account(user_id):
    """解锁账号"""
    unlock_reason = (request.json or {}).get("reason", "管理员手动解锁")

    unlock_account(query_db, execute_db, user_id, unlock_reason)

    return jsonify({"status": "success", "msg": "账号已解锁"})


@bp.route("/api/lock-account/<int:user_id>", methods=["POST"])
def api_lock_account(user_id):
    """锁定账号"""
    lock_reason = (request.json or {}).get("reason", "管理员手动锁定")
    duration_minutes = (request.json or {}).get("duration_minutes")

    lock_account(query_db, execute_db, user_id, lock_reason, duration_minutes)

    return jsonify({"status": "success", "msg": "账号已锁定"})


@bp.route("/api/account-lock-statistics")
def api_account_lock_statistics():
    """获取账号锁定统计"""
    stats = get_account_lock_statistics(query_one)
    return jsonify({"status": "success", "statistics": stats})


# ============ 会话管理 ============

@bp.route("/sessions")
def sessions_page():
    """会话管理页面"""
    return render_template("security/sessions.html")


@bp.route("/api/active-sessions")
def api_active_sessions():
    """获取活跃会话列表"""
    user_id = request.args.get("user_id")
    if user_id:
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            user_id = None

    sessions = get_active_sessions(query_db, user_id)

    # 格式化时间
    for sess in sessions:
        if sess.get("created_at"):
            sess["created_at"] = sess["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        if sess.get("last_activity"):
            sess["last_activity"] = sess["last_activity"].strftime("%Y-%m-%d %H:%M:%S")

    return jsonify({"status": "success", "sessions": sessions})


@bp.route("/api/all-sessions")
def api_all_sessions():
    """获取所有会话"""
    try:
        limit = int(request.args.get("limit", 100))
    except (TypeError, ValueError):
        limit = 100
    try:
        offset = int(request.args.get("offset", 0))
    except (TypeError, ValueError):
        offset = 0

    sessions = get_all_sessions(query_db, limit, offset)

    # 格式化时间
    for sess in sessions:
        if sess.get("created_at"):
            sess["created_at"] = sess["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        if sess.get("last_activity"):
            sess["last_activity"] = sess["last_activity"].strftime("%Y-%m-%d %H:%M:%S")
        if sess.get("expires_at"):
            sess["expires_at"] = sess["expires_at"].strftime("%Y-%m-%d %H:%M:%S")

    return jsonify({"status": "success", "sessions": sessions})


@bp.route("/api/terminate-session", methods=["POST"])
def api_terminate_session():
    """终止会话"""
    session_id = (request.json or {}).get("session_id")
    logout_reason = (request.json or {}).get("reason", "管理员强制终止")

    # 获取会话信息（用于审计）
    session_info = get_session_by_id(query_one, session_id)

    terminate_session(execute_db, session_id, logout_reason)

    return jsonify({"status": "success", "msg": "会话已终止"})


@bp.route("/api/terminate-user-sessions/<int:user_id>", methods=["POST"])
def api_terminate_user_sessions(user_id):
    """终止用户的所有会话"""
    logout_reason = (request.json or {}).get("reason", "管理员强制登出")

    count = terminate_user_sessions(execute_db, user_id, logout_reason=logout_reason)

    return jsonify({"status": "success", "msg": f"已终止 {count} 个会话"})


@bp.route("/api/clean-expired-sessions", methods=["POST"])
def api_clean_expired_sessions():
    """清理过期会话"""
    try:
        inactive_hours = int((request.json or {}).get("inactive_hours", 24))
    except (TypeError, ValueError):
        inactive_hours = 24

    count = clean_expired_sessions(execute_db, inactive_hours)

    return jsonify({"status": "success", "msg": f"已清理 {count} 个过期会话"})


@bp.route("/api/session-statistics")
def api_session_statistics():
    """获取会话统计"""
    stats = get_session_statistics(query_one)
    return jsonify({"status": "success", "statistics": stats})


@bp.route("/api/login-history")
def api_login_history():
    """获取登录历史"""
    user_id = request.args.get("user_id")
    if user_id:
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            user_id = None

    try:
        limit = int(request.args.get("limit", 50))
    except (TypeError, ValueError):
        limit = 50

    history = get_login_history(query_db, user_id, limit)

    # 格式化时间
    for item in history:
        if item.get("created_at"):
            item["created_at"] = item["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        if item.get("last_activity"):
            item["last_activity"] = item["last_activity"].strftime("%Y-%m-%d %H:%M:%S")

    return jsonify({"status": "success", "history": history})
