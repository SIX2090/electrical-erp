"""Data permission routes: row-level data scope configuration and management."""
from __future__ import annotations

import logging

from flask import flash, jsonify, redirect, render_template, request, url_for

logger = logging.getLogger(__name__)

from services.data_permission_service import (
    EXPORT_STATUS_LABELS,
    PERMISSION_LABELS,
    PERMISSION_TYPES,
    ROLE_OPTIONS,
    SCOPE_LABELS,
    SUBJECT_LABELS,
    approve_export_request,
    cancel_export_request,
    create_export_request,
    create_rule,
    delete_rule,
    get_available_scopes,
    get_export_request,
    list_access_logs,
    list_export_requests,
    list_rules,
    reject_export_request,
    update_rule,
)


SCOPE_TYPE_OPTIONS = [(key, label) for key, label in SCOPE_LABELS.items()]
PERMISSION_OPTIONS = [(key, PERMISSION_LABELS[key]) for key in ("view", "edit", "approve", "export")]
SUBJECT_TYPE_OPTIONS = [("user", SUBJECT_LABELS["user"]), ("role", SUBJECT_LABELS["role"])]


def _text(name, source=None):
    holder = source if source is not None else request.form
    return (holder.get(name) or "").strip()


def _arg(name, source=None):
    holder = source if source is not None else request.args
    return (holder.get(name) or "").strip()


def _list_users(query_db):
    try:
        rows = query_db(
            """
            SELECT id::text AS id, username AS label
            FROM users
            WHERE COALESCE(status,'normal') NOT IN ('disabled','inactive')
            ORDER BY username
            LIMIT 500
            """
        ) or []
    except Exception:
        logger.warning("_list_users query failed", exc_info=True)
        rows = []
    return [{"id": str(r.get("id") or ""), "label": str(r.get("label") or r.get("id") or "")} for r in rows]


def register_routes(app, deps):
    query_db = deps["query_db"]
    execute_db = deps["execute_db"]
    execute_and_return = deps["execute_and_return"]
    login_required = deps["login_required"]
    log_action = deps.get("log_action")

    @app.get("/security/data-permissions", endpoint="data_permission_list")
    @login_required
    def data_permission_list():
        subject_type = _arg("subject_type")
        subject_id = _arg("subject_id")
        scope_type = _arg("scope_type")
        status = _arg("status")
        rules = list_rules(
            query_db,
            subject_type=subject_type or None,
            subject_id=subject_id or None,
            scope_type=scope_type or None,
            status=status or None,
        )
        return render_template(
            "security/data_permissions.html",
            rules=rules,
            filters={
                "subject_type": subject_type,
                "subject_id": subject_id,
                "scope_type": scope_type,
                "status": status,
            },
            subject_type_options=[("", "全部主体")] + SUBJECT_TYPE_OPTIONS,
            scope_type_options=[("", "全部范围")] + SCOPE_TYPE_OPTIONS,
            status_options=[("", "全部状态"), ("enabled", "启用"), ("disabled", "停用")],
        )

    @app.route("/security/data-permissions/new", methods=["GET", "POST"], endpoint="data_permission_new")
    @login_required
    def data_permission_new():
        if request.method == "POST":
            subject_type = _text("subject_type")
            subject_id = _text("subject_id")
            scope_type = _text("scope_type")
            scope_id = _text("scope_id")
            scope_label = _text("scope_label")
            permission = _text("permission") or "view"
            errors = []
            if subject_type not in {"user", "role"}:
                errors.append("请选择主体类型。")
            if not subject_id:
                errors.append("请选择主体。")
            if scope_type not in SCOPE_LABELS:
                errors.append("请选择数据范围类型。")
            if not scope_id:
                errors.append("请选择数据范围。")
            if permission not in PERMISSION_TYPES:
                errors.append("请选择权限。")
            if errors:
                for err in errors:
                    flash(err, "danger")
                return render_template(
                    "security/data_permission_form.html",
                    form_state={
                        "subject_type": subject_type,
                        "subject_id": subject_id,
                        "scope_type": scope_type,
                        "scope_id": scope_id,
                        "scope_label": scope_label,
                        "permission": permission,
                    },
                    subject_type_options=SUBJECT_TYPE_OPTIONS,
                    role_options=ROLE_OPTIONS,
                    users=_list_users(query_db),
                    scope_type_options=SCOPE_TYPE_OPTIONS,
                    permission_options=PERMISSION_OPTIONS,
                    mode="new",
                )
            try:
                rule_id = create_rule(
                    query_db,
                    execute_db,
                    execute_and_return,
                    subject_type=subject_type,
                    subject_id=subject_id,
                    scope_type=scope_type,
                    scope_id=scope_id,
                    scope_label=scope_label,
                    permission=permission,
                    created_by=None,
                )
            except ValueError as exc:
                flash(str(exc) or "保存失败，请检查输入。", "danger")
                return render_template(
                    "security/data_permission_form.html",
                    form_state={
                        "subject_type": subject_type,
                        "subject_id": subject_id,
                        "scope_type": scope_type,
                        "scope_id": scope_id,
                        "scope_label": scope_label,
                        "permission": permission,
                    },
                    subject_type_options=SUBJECT_TYPE_OPTIONS,
                    role_options=ROLE_OPTIONS,
                    users=_list_users(query_db),
                    scope_type_options=SCOPE_TYPE_OPTIONS,
                    permission_options=PERMISSION_OPTIONS,
                    mode="new",
                )
            if log_action:
                log_action("新增数据权限规则", f"rule#{rule_id}", f"{subject_type}:{subject_id} {scope_type}:{scope_id} {permission}")
            flash("数据权限规则已保存。", "success")
            return redirect(url_for("data_permission_list"))
        return render_template(
            "security/data_permission_form.html",
            form_state={
                "subject_type": "user",
                "subject_id": "",
                "scope_type": "project",
                "scope_id": "",
                "scope_label": "",
                "permission": "view",
            },
            subject_type_options=SUBJECT_TYPE_OPTIONS,
            role_options=ROLE_OPTIONS,
            users=_list_users(query_db),
            scope_type_options=SCOPE_TYPE_OPTIONS,
            permission_options=PERMISSION_OPTIONS,
            mode="new",
        )

    @app.post("/security/data-permissions/<int:rule_id>/update", endpoint="data_permission_update")
    @login_required
    def data_permission_update(rule_id):
        status = _text("status")
        permission = _text("permission")
        scope_label = _text("scope_label")
        fields = {}
        if status in {"enabled", "disabled"}:
            fields["status"] = status
        if permission in PERMISSION_TYPES:
            fields["permission"] = permission
        if scope_label:
            fields["scope_label"] = scope_label
        if not fields:
            flash("没有可更新的字段。", "warning")
            return redirect(url_for("data_permission_list"))
        try:
            update_rule(query_db, execute_db, rule_id, **fields)
        except ValueError as exc:
            flash(str(exc) or "更新失败。", "danger")
            return redirect(url_for("data_permission_list"))
        if log_action:
            log_action("更新数据权限规则", f"rule#{rule_id}", ",".join(f"{k}={v}" for k, v in fields.items()))
        flash("数据权限规则已更新。", "success")
        return redirect(url_for("data_permission_list"))

    @app.post("/security/data-permissions/<int:rule_id>/delete", endpoint="data_permission_delete")
    @login_required
    def data_permission_delete(rule_id):
        delete_rule(query_db, execute_db, rule_id)
        if log_action:
            log_action("删除数据权限规则", f"rule#{rule_id}", "")
        flash("数据权限规则已删除。", "success")
        return redirect(url_for("data_permission_list"))

    @app.get("/security/data-access-logs", endpoint="data_access_logs_page")
    @login_required
    def data_access_logs_page():
        user_id = _arg("user_id")
        resource_type = _arg("resource_type")
        allowed = _arg("allowed")
        try:
            limit = int(_arg("limit") or 200)
        except (TypeError, ValueError):
            limit = 200
        allowed_flag = None
        if allowed == "1":
            allowed_flag = True
        elif allowed == "0":
            allowed_flag = False
        user_id_int = None
        if user_id:
            try:
                user_id_int = int(user_id)
            except (TypeError, ValueError):
                user_id_int = None
        logs = list_access_logs(
            query_db,
            user_id=user_id_int,
            resource_type=resource_type or None,
            allowed=allowed_flag,
            limit=limit,
        )
        return render_template(
            "security/data_access_logs.html",
            logs=logs,
            filters={
                "user_id": user_id,
                "resource_type": resource_type,
                "allowed": allowed,
                "limit": str(limit),
            },
            allowed_options=[("", "全部"), ("1", "允许"), ("0", "拒绝")],
        )

    @app.get("/security/export-approvals", endpoint="export_approvals_page")
    @login_required
    def export_approvals_page():
        """P3-B5: 导出审批流列表（真正的审批申请，非日志查询）。"""
        status = _arg("status")
        try:
            limit = int(_arg("limit") or 200)
        except (TypeError, ValueError):
            limit = 200
        approvals = list_export_requests(
            query_db,
            status=status if status in EXPORT_STATUS_LABELS else None,
            limit=limit,
        )
        return render_template(
            "security/export_approvals.html",
            approvals=approvals,
            filters={"status": status, "limit": str(limit)},
            status_options=[("", "全部")] + [(k, v) for k, v in EXPORT_STATUS_LABELS.items()],
            status_labels=EXPORT_STATUS_LABELS,
        )

    @app.route("/security/export-approvals/new", methods=["GET", "POST"], endpoint="export_approval_new")
    @login_required
    def export_approval_new():
        """创建导出审批申请。"""
        from flask import session
        user_id = session.get("user_id")
        username = session.get("username", "")
        if request.method == "POST":
            resource_type = _text("resource_type")
            resource_id = _text("resource_id")
            resource_label = _text("resource_label")
            export_format = _text("export_format") or "csv"
            filter_summary = _text("filter_summary")
            if not resource_type:
                flash("请填写资源类型。", "warning")
                return redirect(url_for("export_approval_new"))
            req = create_export_request(
                execute_db,
                execute_and_return,
                requester_id=user_id,
                requester_name=username,
                resource_type=resource_type,
                resource_id=resource_id,
                resource_label=resource_label,
                export_format=export_format,
                filter_summary=filter_summary,
            )
            if not req:
                flash("创建导出审批申请失败。", "danger")
                return redirect(url_for("export_approval_new"))
            if log_action:
                log_action("创建导出审批申请", f"request#{req.get('id')}", f"{resource_type}:{resource_label}")
            flash("导出审批申请已提交，等待审批。", "success")
            return redirect(url_for("export_approvals_page"))
        return render_template(
            "security/export_approval_form.html",
            form_state={
                "resource_type": "", "resource_id": "", "resource_label": "",
                "export_format": "csv", "filter_summary": "",
            },
            mode="new",
        )

    @app.post("/security/export-approvals/<int:request_id>/approve", endpoint="export_approval_approve")
    @login_required
    def export_approval_approve(request_id):
        """批准导出申请。"""
        from flask import session
        user_id = session.get("user_id")
        username = session.get("username", "")
        remark = _text("remark")
        req = get_export_request(query_db, request_id)
        if not req:
            flash("导出审批申请不存在。", "warning")
            return redirect(url_for("export_approvals_page"))
        if req.get("status") != "pending":
            flash("只有待审批的申请可以批准。", "warning")
            return redirect(url_for("export_approvals_page"))
        approve_export_request(execute_db, request_id, user_id, username, remark)
        if log_action:
            log_action("批准导出审批", f"request#{request_id}", remark or "")
        flash("导出申请已批准。", "success")
        return redirect(url_for("export_approvals_page"))

    @app.post("/security/export-approvals/<int:request_id>/reject", endpoint="export_approval_reject")
    @login_required
    def export_approval_reject(request_id):
        """拒绝导出申请。"""
        from flask import session
        user_id = session.get("user_id")
        username = session.get("username", "")
        remark = _text("remark")
        req = get_export_request(query_db, request_id)
        if not req:
            flash("导出审批申请不存在。", "warning")
            return redirect(url_for("export_approvals_page"))
        if req.get("status") != "pending":
            flash("只有待审批的申请可以拒绝。", "warning")
            return redirect(url_for("export_approvals_page"))
        reject_export_request(execute_db, request_id, user_id, username, remark)
        if log_action:
            log_action("拒绝导出审批", f"request#{request_id}", remark or "")
        flash("导出申请已拒绝。", "success")
        return redirect(url_for("export_approvals_page"))

    @app.post("/security/export-approvals/<int:request_id>/cancel", endpoint="export_approval_cancel")
    @login_required
    def export_approval_cancel(request_id):
        """申请人取消导出申请。"""
        from flask import session
        user_id = session.get("user_id")
        req = get_export_request(query_db, request_id)
        if not req:
            flash("导出审批申请不存在。", "warning")
            return redirect(url_for("export_approvals_page"))
        if req.get("requester_id") != user_id:
            flash("只能取消自己的导出申请。", "warning")
            return redirect(url_for("export_approvals_page"))
        if req.get("status") != "pending":
            flash("只有待审批的申请可以取消。", "warning")
            return redirect(url_for("export_approvals_page"))
        cancel_export_request(execute_db, request_id, user_id)
        if log_action:
            log_action("取消导出审批", f"request#{request_id}", "")
        flash("导出申请已取消。", "success")
        return redirect(url_for("export_approvals_page"))

    @app.get("/api/data-permissions/scopes", endpoint="api_data_permission_scopes")
    @login_required
    def api_data_permission_scopes():
        scope_type = _arg("scope_type")
        if scope_type not in SCOPE_LABELS:
            return jsonify({"status": "error", "msg": "scope_type 不合法", "scopes": []}), 400
        scopes = get_available_scopes(query_db, scope_type)
        return jsonify({"status": "success", "scopes": scopes})

    return app
