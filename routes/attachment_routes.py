"""Attachment routes: file upload, download, and attachment management."""
from pathlib import Path, PurePosixPath

from flask import abort, redirect, send_file, session
from werkzeug.utils import secure_filename


ROOT_DIR = Path(__file__).resolve().parents[1]
UPLOAD_ROOT = (ROOT_DIR / "static" / "uploads").resolve()


def _clean_stored_path(raw_path):
    value = (raw_path or "").replace("\\", "/").strip()
    if not value:
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        return None
    if path.parts and path.parts[0] == "static":
        path = PurePosixPath(*path.parts[1:])
    if not path.parts or path.parts[0] != "uploads":
        return None
    return path


def _resolve_upload_path(stored_path):
    clean_path = _clean_stored_path(stored_path)
    if clean_path is None:
        abort(404)
    relative_parts = clean_path.parts[1:]
    if not relative_parts:
        abort(404)
    target = (UPLOAD_ROOT.joinpath(*relative_parts)).resolve()
    try:
        target.relative_to(UPLOAD_ROOT)
    except ValueError:
        abort(404)
    if not target.is_file():
        abort(404)
    return target


def _download_name(row, target):
    name = secure_filename(row.get("file_name") or "") or target.name
    return name


def _attachment_response(row):
    target = _resolve_upload_path(row.get("stored_path"))
    response = send_file(
        target,
        as_attachment=True,
        download_name=_download_name(row, target),
        mimetype="application/octet-stream",
        max_age=0,
        conditional=True,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def register_routes(app, deps):
    query_db = deps["query_db"]
    login_required = deps["login_required"]

    # subject_type -> required permission group(s)
    # admin/manager bypass; other roles must have at least one matching group
    SUBJECT_TYPE_GROUP_MAP = {
        "product": {"master", "sales", "purchase", "production", "warehouse", "service", "finance", "tech", "inventory"},
        "supplier": {"master", "purchase"},
        "customer": {"master", "sales", "service", "finance"},
        "quotation": {"sales"},
        "sales_order": {"sales"},
        "sales_shipment": {"sales"},
        "sales_return": {"sales"},
        "sales_invoice": {"sales", "finance"},
        "customer_receipt": {"sales", "finance"},
        "receivable": {"finance"},
        "purchase_order": {"purchase"},
        "purchase_receipt": {"purchase", "inventory"},
        "purchase_return": {"purchase", "inventory"},
        "purchase_invoice": {"purchase", "finance"},
        "supplier_quote": {"purchase"},
        "payable": {"finance"},
        "work_order": {"production"},
        "quality_inspection": {"production"},
        "inventory_adjustment": {"inventory"},
        "inventory_transfer": {"inventory"},
        "inventory_check": {"inventory"},
        "inventory_assembly": {"inventory"},
        "inventory_disassembly": {"inventory"},
        "service_card": {"service"},
        "service_order": {"service"},
        "service_rma": {"service"},
    }

    def _find_attachment(attachment_id):
        row = query_db(
            """
            SELECT id, file_name, stored_path, content_type, file_size,
                   uploaded_by, subject_type, subject_id
            FROM document_attachments
            WHERE id=%s
            """,
            (attachment_id,),
            one=True,
        )
        if not row:
            abort(404)
        return row

    def _check_attachment_permission(row):
        """
        校验当前用户是否有权下载该附件。
        优先级：
        1. admin/manager 可下载全部
        2. 上传者可下载自己上传的附件（补充权限）
        3. 按附件所属业务对象（subject_type）校验角色权限组
        """
        role = session.get("role") or "staff"
        if role in ("admin", "manager"):
            return

        uploaded_by = row.get("uploaded_by")
        if uploaded_by is not None and uploaded_by == session.get("user_id"):
            return

        subject_type = row.get("subject_type") or ""
        required_groups = SUBJECT_TYPE_GROUP_MAP.get(subject_type)
        if required_groups is None:
            # 未知 subject_type，拒绝访问以防止越权
            abort(403)

        from services.pilot_permissions import default_groups_for_role
        user_groups = default_groups_for_role(role)
        if user_groups & required_groups:
            return

        abort(403)

    def _find_attachment_by_stored_path(stored_path):
        clean_path = _clean_stored_path(stored_path)
        if clean_path is None:
            abort(404)
        normalized = clean_path.as_posix()
        row = query_db(
            """
            SELECT id, file_name, stored_path, content_type, file_size,
                   uploaded_by, subject_type, subject_id
            FROM document_attachments
            WHERE stored_path=%s OR stored_path=%s
            ORDER BY id DESC
            LIMIT 1
            """,
            (normalized, f"static/{normalized}"),
            one=True,
        )
        if not row:
            abort(404)
        return row

    @app.get("/attachments/<int:attachment_id>", endpoint="attachment_download")
    @app.get("/attachments/<int:attachment_id>/download", endpoint="attachment_download_explicit")
    @app.get("/document_attachments/<int:attachment_id>", endpoint="document_attachment_download")
    @app.get("/document_attachments/<int:attachment_id>/download", endpoint="document_attachment_download_explicit")
    @login_required
    def download_attachment(attachment_id):
        row = _find_attachment(attachment_id)
        _check_attachment_permission(row)
        return _attachment_response(row)

    @app.get("/uploads/<path:stored_path>", endpoint="legacy_upload_download")
    @app.get("/static/uploads/<path:stored_path>", endpoint="legacy_static_upload_download")
    @login_required
    def download_legacy_upload(stored_path):
        row = _find_attachment_by_stored_path(f"uploads/{stored_path}")
        _check_attachment_permission(row)
        return _attachment_response(row)

    @app.get("/attachment/<int:attachment_id>", endpoint="legacy_attachment_download")
    @login_required
    def legacy_attachment_redirect(attachment_id):
        return redirect(f"/attachments/{attachment_id}/download", code=302)
