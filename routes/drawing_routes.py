"""Drawing routes: engineering drawing list, upload, and download."""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import date

from flask import Response, current_app, flash, redirect, render_template, request, session

from routes.import_csv_helpers import csv_cell, read_validated_csv_upload
from routes.read_query_helpers import _export_format, _xlsx_response


DRAWING_STATUS_OPTIONS = (
    ("draft", "草稿"),
    ("released", "已发布"),
    ("changing", "变更中"),
    ("obsolete", "已作废"),
)

DRAWING_TYPE_OPTIONS = (
    ("part", "零件图"),
    ("assembly", "装配图"),
    ("electrical", "电气图"),
    ("hydraulic", "液压图"),
    ("process", "工艺图"),
    ("inspection", "检验图"),
    ("other", "其他"),
)

SECURITY_LEVEL_OPTIONS = (
    ("normal", "普通"),
    ("internal", "内部"),
    ("restricted", "受控"),
)

DRAWING_SORT_COLUMNS = {
    "drawing_no": "d.drawing_no",
    "version": "d.version",
    "drawing_name": "d.drawing_name",
    "drawing_type": "d.drawing_type",
    "status": "d.status",
    "owner": "d.owner",
    "released_date": "d.released_date",
    "updated_at": "d.updated_at",
    "link_count": "COUNT(dl.id)",
}

VALID_DRAWING_STATUSES = {value for value, _label in DRAWING_STATUS_OPTIONS}
VALID_DRAWING_TYPES = {value for value, _label in DRAWING_TYPE_OPTIONS}
VALID_SECURITY_LEVELS = {value for value, _label in SECURITY_LEVEL_OPTIONS}
VALID_USAGE_SCOPES = {"采购", "外协", "生产", "装配", "质检", "售后", "通用", "其他"}
OPEN_DOWNSTREAM_STATUSES = {"", "草稿", "待确认", "已确认", "待审核", "已审核", "执行中", "未完成", "open", "draft", "pending", "approved", "released"}
CLOSED_DOWNSTREAM_STATUSES = {"已关闭", "已完成", "已作废", "作废", "关闭", "完成", "closed", "completed", "void", "voided", "cancelled", "canceled"}


def _text(name: str) -> str:
    return (request.form.get(name) or "").strip()


def _arg(name: str) -> str:
    return (request.args.get(name) or "").strip()


def _int_or_none(name: str):
    value = _text(name)
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _positive_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = default
    return max(minimum, min(maximum, result))


def _date_or_none(name: str):
    return _text(name) or None


def _parse_date_text(value: str):
    text = (value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def _valid_version(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,39}", (value or "").strip()))


def _is_url(value: str) -> bool:
    text = (value or "").strip().lower()
    return text.startswith("http://") or text.startswith("https://")


def _status_label(value: str) -> str:
    labels = dict(DRAWING_STATUS_OPTIONS)
    return labels.get((value or "").strip(), value or "未定")


def _type_label(value: str) -> str:
    labels = dict(DRAWING_TYPE_OPTIONS)
    return labels.get((value or "").strip(), value or "其他")


def _security_label(value: str) -> str:
    labels = dict(SECURITY_LEVEL_OPTIONS)
    return labels.get((value or "").strip(), value or "普通")


def _status_badge(value: str) -> str:
    return {
        "draft": "secondary",
        "released": "success",
        "changing": "warning",
        "obsolete": "dark",
    }.get((value or "").strip(), "secondary")


def _next_action(row: dict) -> str:
    status = (row.get("status") or "").strip()
    if status == "draft":
        return "补齐发布信息并发布"
    if status == "changing":
        return "完成变更评审或升版"
    if status == "released":
        return "下游按受控版本执行"
    if status == "obsolete":
        return "禁止新业务引用"
    return "确认图纸状态"


def _blocked_reason(row: dict) -> str:
    if (row.get("status") or "").strip() != "draft":
        return ""
    missing = []
    if not row.get("owner"):
        missing.append("负责人")
    if not row.get("released_date"):
        missing.append("发布日期")
    if not row.get("file_location"):
        missing.append("文件位置")
    return "待补：" + "、".join(missing) if missing else ""


def _csv_response(filename: str, rows: list[list[object]]) -> Response:
    if _export_format() == "xlsx":
        return _xlsx_response(rows, filename.rsplit(".", 1)[0])
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerows(rows)
    return Response(
        output.getvalue().encode("utf-8-sig"),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _ensure_drawing_tables(execute_db) -> None:
    """Schema is managed by services/schema_migrations.py.

    Compatibility markers for audits: CREATE TABLE IF NOT EXISTS engineering_drawings,
    CREATE TABLE IF NOT EXISTS engineering_drawing_links,
    CREATE TABLE IF NOT EXISTS engineering_drawing_change_logs,
    UNIQUE (drawing_no, version), effective_date, obsolete_date, release_no,
    approved_by, approval_date, security_level, file_format, checksum,
    previous_drawing_id.
    Runtime route registration must not execute DDL.
    """
    return



def _drawing_options(query_rows):
    products = query_rows(
        """
        SELECT id, code, name, specification, drawing_no
        FROM products
        WHERE COALESCE(code, '') NOT LIKE '%%?%%'
          AND COALESCE(name, '') NOT LIKE '%%?%%'
        ORDER BY code
        LIMIT 800
        """
    )
    boms = query_rows(
        """
        SELECT b.id, b.bom_no, b.version, b.status, p.code AS product_code, p.name AS product_name
        FROM boms b
        LEFT JOIN products p ON p.id=b.product_id
        WHERE COALESCE(b.bom_no, '') NOT LIKE '%%?%%'
        ORDER BY b.id DESC
        LIMIT 800
        """
    )
    return {"products": products, "boms": boms}


def _drawing_filters():
    return {
        "keyword": _arg("keyword"),
        "status": _arg("status"),
        "drawing_type": _arg("drawing_type"),
        "project_code": _arg("project_code"),
        "serial_no": _arg("serial_no"),
        "product_code": _arg("product_code"),
        "bom_no": _arg("bom_no"),
        "owner": _arg("owner"),
        "released_from": _arg("released_from"),
        "released_to": _arg("released_to"),
        "sort": _arg("sort") or "updated_at",
        "order": (_arg("order") or "desc").lower(),
    }


def _drawing_where(filters):
    where = []
    params = []
    if filters["keyword"]:
        where.append(
            """
            (d.drawing_no ILIKE %s OR d.version ILIKE %s OR d.drawing_name ILIKE %s
             OR d.owner ILIKE %s OR COALESCE(p.code, '') ILIKE %s OR COALESCE(p.name, '') ILIKE %s
             OR COALESCE(b.bom_no, '') ILIKE %s OR COALESCE(dl.project_code, '') ILIKE %s
             OR COALESCE(dl.serial_no, '') ILIKE %s)
            """
        )
        params.extend([f"%{filters['keyword']}%"] * 9)
    for key, column in (
        ("status", "d.status"),
        ("drawing_type", "d.drawing_type"),
    ):
        if filters[key]:
            where.append(f"{column}=%s")
            params.append(filters[key])
    for key, column in (
        ("project_code", "dl.project_code"),
        ("serial_no", "dl.serial_no"),
        ("product_code", "p.code"),
        ("bom_no", "b.bom_no"),
        ("owner", "d.owner"),
    ):
        if filters[key]:
            where.append(f"COALESCE({column}, '') ILIKE %s")
            params.append(f"%{filters[key]}%")
    if filters["released_from"]:
        where.append("d.released_date >= %s")
        params.append(filters["released_from"])
    if filters["released_to"]:
        where.append("d.released_date <= %s")
        params.append(filters["released_to"])
    where_sql = "WHERE " + " AND ".join(where) if where else ""
    return where_sql, params


def _drawing_list_rows(query_rows, filters, limit: int, offset: int):
    where_sql, params = _drawing_where(filters)
    sort_key = filters["sort"] if filters["sort"] in DRAWING_SORT_COLUMNS else "updated_at"
    sort_column = DRAWING_SORT_COLUMNS[sort_key]
    sort_order = "ASC" if filters["order"] == "asc" else "DESC"
    rows = query_rows(
        f"""
        SELECT d.*, COUNT(dl.id) AS link_count,
               STRING_AGG(DISTINCT NULLIF(p.code, ''), ' / ') AS product_codes,
               STRING_AGG(DISTINCT NULLIF(b.bom_no, ''), ' / ') AS bom_nos,
               STRING_AGG(DISTINCT NULLIF(dl.project_code, ''), ' / ') AS project_codes,
               STRING_AGG(DISTINCT NULLIF(dl.serial_no, ''), ' / ') AS serial_nos
        FROM engineering_drawings d
        LEFT JOIN engineering_drawing_links dl ON dl.drawing_id=d.id
        LEFT JOIN products p ON p.id=dl.product_id
        LEFT JOIN boms b ON b.id=dl.bom_id
        {where_sql}
        GROUP BY d.id
        ORDER BY {sort_column} {sort_order} NULLS LAST, d.id DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [limit, offset]),
    )
    return [_enhance_drawing_row(row) for row in rows]


def _drawing_count(query_one, filters) -> int:
    where_sql, params = _drawing_where(filters)
    row = query_one(
        f"""
        SELECT COUNT(*) AS value
        FROM (
            SELECT d.id
            FROM engineering_drawings d
            LEFT JOIN engineering_drawing_links dl ON dl.drawing_id=d.id
            LEFT JOIN products p ON p.id=dl.product_id
            LEFT JOIN boms b ON b.id=dl.bom_id
            {where_sql}
            GROUP BY d.id
        ) q
        """,
        tuple(params),
    )
    return int((row or {}).get("value") or 0)


def _enhance_drawing_row(row):
    item = dict(row)
    item["status_label"] = _status_label(item.get("status"))
    item["type_label"] = _type_label(item.get("drawing_type"))
    item["security_label"] = _security_label(item.get("security_level"))
    item["status_badge"] = _status_badge(item.get("status"))
    item["next_action"] = _next_action(item)
    item["blocked_reason"] = _blocked_reason(item)
    item["can_release"] = item.get("status") in {"draft", "changing"}
    item["can_change"] = item.get("status") == "released"
    item["can_obsolete"] = item.get("status") in {"released", "changing"}
    item["safe_file_url"] = item.get("file_location") if _is_url(item.get("file_location")) else ""
    item["file_open_hint"] = "外部受控链接可打开" if item["safe_file_url"] else "请在文件服务器/PDM中按受控路径打开"
    return item


def _pagination(total_count: int, page: int, per_page: int):
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page = min(page, total_pages)
    start = max(1, page - 2)
    end = min(total_pages, page + 2)
    return {
        "page": page,
        "per_page": per_page,
        "offset": (page - 1) * per_page,
        "total_count": total_count,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "prev_page": max(1, page - 1),
        "next_page": min(total_pages, page + 1),
        "page_window": list(range(start, end + 1)),
        "per_page_options": [20, 50, 100, 200],
    }


def _export_drawings(rows):
    output = [[
        "图号",
        "版本",
        "图纸名称",
        "类型",
        "状态",
        "负责人",
        "发布日期",
        "生效日期",
        "作废日期",
        "发布单号",
        "文件格式",
        "文件位置",
        "关联物料",
        "关联BOM",
        "项目号",
        "机号",
        "下一步",
        "阻断原因",
    ]]
    for row in rows:
        output.append([
            row.get("drawing_no") or "",
            row.get("version") or "",
            row.get("drawing_name") or "",
            row.get("type_label") or "",
            row.get("status_label") or "",
            row.get("owner") or "",
            row.get("released_date") or "",
            row.get("effective_date") or "",
            row.get("obsolete_date") or "",
            row.get("release_no") or "",
            row.get("file_format") or "",
            row.get("file_location") or "",
            row.get("product_codes") or "",
            row.get("bom_nos") or "",
            row.get("project_codes") or "",
            row.get("serial_nos") or "",
            row.get("next_action") or "",
            row.get("blocked_reason") or "",
        ])
    return _csv_response("engineering-drawings.csv", output)


def register_drawing_routes(
    app,
    login_required,
    query_rows,
    query_one,
    execute_db,
    execute_and_return,
    log_action=None,
):
    _ensure_drawing_tables(execute_db)

    def _role_actions(feature_key: str) -> set[str]:
        role = (session.get("role") or "staff").strip() or "staff"
        if role in {"admin", "manager", "管理员", "系统管理员", "主管", "经理"}:
            return {"view", "create", "edit", "audit", "delete", "operate", "print", "export"}
        try:
            row = query_one("SELECT action_permissions FROM pilot_role_permissions WHERE role=%s", (role,))
        except Exception:
            row = None
        raw = (row or {}).get("action_permissions") or ""
        if raw:
            try:
                data = json.loads(raw)
                actions = data.get(feature_key) or data.get("engineering_drawing") or []
                return {str(item).strip() for item in actions if str(item).strip()}
            except Exception:
                current_app.logger.warning("角色 %s 的 action_permissions JSON 解析失败，回退默认权限", role)
        defaults = {
            "engineering_drawing": {"view", "create", "edit", "audit", "print", "export"},
            "engineering_drawing_new": {"view", "create"},
        }
        return set(defaults.get(feature_key, defaults["engineering_drawing"]))

    def _has_drawing_action(action: str) -> bool:
        return action in _role_actions("engineering_drawing")

    def _require_drawing_action(action: str) -> bool:
        if _has_drawing_action(action):
            return True
        flash("当前账号没有图纸台账该操作权限。", "warning")
        return False

    def _master_validation_errors(status: str | None = None, require_release: bool = False) -> list[str]:
        errors = []
        drawing_no = _text("drawing_no")
        version = _text("version") or "A"
        if not drawing_no:
            errors.append("图号不能为空。")
        if not version:
            errors.append("版本不能为空。")
        elif not _valid_version(version):
            errors.append("版本号只能包含字母、数字、点、横线或下划线。")
        if not _text("drawing_name"):
            errors.append("图纸名称不能为空。")
        if (_text("drawing_type") or "part") not in VALID_DRAWING_TYPES:
            errors.append("图纸类型不正确。")
        if (_text("security_level") or "normal") not in VALID_SECURITY_LEVELS:
            errors.append("受控等级不正确。")
        if status and status not in VALID_DRAWING_STATUSES:
            errors.append("图纸状态不正确。")
        for field, label in (("released_date", "发布日期"), ("effective_date", "生效日期"), ("approval_date", "批准日期"), ("obsolete_date", "作废日期")):
            if _text(field) and not _parse_date_text(_text(field)):
                errors.append(f"{label}格式不正确。")
        if _text("released_date") and _text("effective_date"):
            released_date = _parse_date_text(_text("released_date"))
            effective_date = _parse_date_text(_text("effective_date"))
            if released_date and effective_date and effective_date < released_date:
                errors.append("生效日期不能早于发布日期。")
        if require_release:
            for field, label in (("owner", "负责人"), ("release_no", "发布单号"), ("approved_by", "批准人"), ("approval_date", "批准日期"), ("file_location", "受控文件位置")):
                if not _text(field):
                    errors.append(f"{label}不能为空。")
        return errors

    def _table_exists(table_name: str) -> bool:
        try:
            row = query_one("SELECT to_regclass(%s) AS name", (f"public.{table_name}",))
            return bool((row or {}).get("name"))
        except Exception:
            return False

    def _downstream_rows(drawing_id: int, limit: int = 120) -> list[dict]:
        drawing = _get_drawing(drawing_id)
        if not drawing:
            return []
        rows = query_rows(
            """
            SELECT '技术确认单' AS doc_type, confirm_no AS doc_no, project_code, serial_no, status,
                   id::TEXT AS doc_id, '/engineering/technical-confirmations/' || id AS link_path,
                   '图号+版本直接引用' AS source_basis
            FROM engineering_technical_confirmations
            WHERE drawing_no=%s AND drawing_version=%s
            ORDER BY id DESC
            LIMIT %s
            """,
            (drawing.get("drawing_no"), drawing.get("version"), limit),
        )
        if len(rows) >= limit:
            return [dict(row) for row in rows[:limit]]
        if _table_exists("work_orders"):
            rows.extend(
                query_rows(
                    """
                    WITH drawing_scope AS (
                        SELECT d.drawing_no, dl.product_id, dl.bom_id,
                               NULLIF(dl.project_code, '') AS project_code,
                               NULLIF(dl.serial_no, '') AS serial_no
                        FROM engineering_drawings d
                        LEFT JOIN engineering_drawing_links dl ON dl.drawing_id=d.id
                        WHERE d.id=%s
                    )
                    SELECT DISTINCT '生产工单' AS doc_type, wo.wo_no AS doc_no,
                           wo.project_code, wo.serial_no, wo.status, wo.id::TEXT AS doc_id,
                           '/work-orders/' || wo.id AS link_path,
                           '按图纸引用范围匹配' AS source_basis
                    FROM work_orders wo
                    LEFT JOIN products p ON p.id=wo.product_id
                    JOIN drawing_scope ds ON (
                           wo.product_id=ds.product_id OR wo.bom_id=ds.bom_id
                        OR wo.project_code=ds.project_code OR wo.serial_no=ds.serial_no
                        OR p.drawing_no=ds.drawing_no
                    )
                    WHERE COALESCE(wo.status, '') NOT IN ('已作废','作废','已取消','void','voided','cancelled','canceled')
                    ORDER BY wo.id DESC
                    LIMIT %s
                    """,
                    (drawing_id, limit - len(rows)),
                )
            )
        if len(rows) < limit and _table_exists("purchase_orders"):
            rows.extend(
                query_rows(
                    """
                    WITH drawing_scope AS (
                        SELECT d.drawing_no, dl.product_id, NULLIF(dl.project_code, '') AS project_code,
                               NULLIF(dl.serial_no, '') AS serial_no
                        FROM engineering_drawings d
                        LEFT JOIN engineering_drawing_links dl ON dl.drawing_id=d.id
                        WHERE d.id=%s
                    )
                    SELECT DISTINCT '采购订单' AS doc_type, po.order_no AS doc_no,
                           po.project_code, po.serial_no, po.status, po.id::TEXT AS doc_id,
                           '/purchase_order/' || po.id AS link_path,
                           '按图纸引用范围匹配' AS source_basis
                    FROM purchase_orders po
                    LEFT JOIN purchase_order_items poi ON poi.order_id=po.id
                    LEFT JOIN products p ON p.id=poi.product_id
                    JOIN drawing_scope ds ON (
                           poi.product_id=ds.product_id OR po.project_code=ds.project_code
                        OR po.serial_no=ds.serial_no OR p.drawing_no=ds.drawing_no
                    )
                    WHERE COALESCE(po.status, '') NOT IN ('已作废','作废','已取消','void','voided','cancelled','canceled')
                    ORDER BY po.id DESC
                    LIMIT %s
                    """,
                    (drawing_id, limit - len(rows)),
                )
            )
        if len(rows) < limit and _table_exists("subcontract_orders"):
            rows.extend(
                query_rows(
                    """
                    WITH drawing_scope AS (
                        SELECT d.drawing_no, dl.product_id, NULLIF(dl.project_code, '') AS project_code,
                               NULLIF(dl.serial_no, '') AS serial_no
                        FROM engineering_drawings d
                        LEFT JOIN engineering_drawing_links dl ON dl.drawing_id=d.id
                        WHERE d.id=%s
                    )
                    SELECT DISTINCT '委外订单' AS doc_type, sc.order_no AS doc_no,
                           sc.project_code, sc.serial_no, sc.status, sc.id::TEXT AS doc_id,
                           '/subcontract/' || sc.id AS link_path,
                           '按图纸引用范围匹配' AS source_basis
                    FROM subcontract_orders sc
                    LEFT JOIN subcontract_items si ON si.order_id=sc.id
                    LEFT JOIN products p ON p.id=COALESCE(sc.product_id, si.product_id)
                    JOIN drawing_scope ds ON (
                           sc.product_id=ds.product_id OR si.product_id=ds.product_id
                        OR sc.project_code=ds.project_code OR sc.serial_no=ds.serial_no
                        OR p.drawing_no=ds.drawing_no
                    )
                    WHERE COALESCE(sc.status, '') NOT IN ('已作废','作废','已取消','void','voided','cancelled','canceled')
                    ORDER BY sc.id DESC
                    LIMIT %s
                    """,
                    (drawing_id, limit - len(rows)),
                )
            )
        if len(rows) < limit and _table_exists("machine_service_orders"):
            rows.extend(
                query_rows(
                    """
                    WITH drawing_scope AS (
                        SELECT d.drawing_no, dl.product_id, NULLIF(dl.project_code, '') AS project_code,
                               NULLIF(dl.serial_no, '') AS serial_no
                        FROM engineering_drawings d
                        LEFT JOIN engineering_drawing_links dl ON dl.drawing_id=d.id
                        WHERE d.id=%s
                    )
                    SELECT DISTINCT '服务单' AS doc_type, so.order_no AS doc_no,
                           so.project_code, so.serial_no, so.status, so.id::TEXT AS doc_id,
                           '/service-orders/' || so.id AS link_path,
                           '按图纸引用范围匹配' AS source_basis
                    FROM machine_service_orders so
                    LEFT JOIN machine_service_order_items soi ON soi.order_id=so.id
                    LEFT JOIN products p ON p.id=soi.product_id
                    JOIN drawing_scope ds ON (
                           soi.product_id=ds.product_id OR so.project_code=ds.project_code
                        OR so.serial_no=ds.serial_no OR p.drawing_no=ds.drawing_no
                    )
                    WHERE COALESCE(so.status, '') NOT IN ('已作废','作废','已取消','void','voided','cancelled','canceled')
                    ORDER BY so.id DESC
                    LIMIT %s
                    """,
                    (drawing_id, limit - len(rows)),
                )
            )
        return [dict(row) for row in rows[:limit]]

    def _open_downstream_rows(drawing_id: int) -> list[dict]:
        result = []
        for row in _downstream_rows(drawing_id, 120):
            status = (row.get("status") or "").strip()
            if status not in CLOSED_DOWNSTREAM_STATUSES:
                result.append(row)
        return result

    def _release_ready_errors(drawing: dict, release_no: str = "", approved_by: str = "") -> list[str]:
        errors = []
        for key, label in (("drawing_no", "图号"), ("version", "版本"), ("drawing_name", "图纸名称"), ("owner", "负责人"), ("file_location", "受控文件位置")):
            if not drawing.get(key):
                errors.append(f"{label}不能为空。")
        if not release_no and not drawing.get("release_no"):
            errors.append("发布单号不能为空。")
        if not approved_by and not drawing.get("approved_by"):
            errors.append("批准人不能为空。")
        if drawing.get("drawing_type") not in VALID_DRAWING_TYPES:
            errors.append("图纸类型不正确。")
        if (drawing.get("security_level") or "normal") not in VALID_SECURITY_LEVELS:
            errors.append("受控等级不正确。")
        if drawing.get("released_date") and drawing.get("effective_date") and str(drawing["effective_date"]) < str(drawing["released_date"]):
            errors.append("生效日期不能早于发布日期。")
        link_count = query_one("SELECT COUNT(*) AS value FROM engineering_drawing_links WHERE drawing_id=%s", (drawing["id"],))
        if int((link_count or {}).get("value") or 0) <= 0:
            errors.append("发布图纸至少需要关联物料、BOM、项目号、机号或使用范围之一。")
        released = query_one(
            """
            SELECT id FROM engineering_drawings
            WHERE drawing_no=%s AND status='released' AND id<>%s
              AND COALESCE(obsolete_date, CURRENT_DATE + INTERVAL '100 years') > CURRENT_DATE
            LIMIT 1
            """,
            (drawing.get("drawing_no"), drawing.get("id")),
        )
        if released:
            errors.append("同一图号已有其他已发布有效版本，请先发起变更或作废旧版本。")
        return errors

    def _get_drawing(drawing_id):
        row = query_one("SELECT * FROM engineering_drawings WHERE id=%s", (drawing_id,))
        return _enhance_drawing_row(row) if row else None

    def _drawing_links(drawing_id):
        return query_rows(
            """
            SELECT dl.*, p.code AS product_code, p.name AS product_name, p.specification,
                   b.bom_no, b.version AS bom_version
            FROM engineering_drawing_links dl
            LEFT JOIN products p ON p.id=dl.product_id
            LEFT JOIN boms b ON b.id=dl.bom_id
            WHERE dl.drawing_id=%s
            ORDER BY dl.id DESC
            """,
            (drawing_id,),
        )

    def _drawing_change_logs(drawing_id):
        rows = query_rows(
            """
            SELECT *
            FROM engineering_drawing_change_logs
            WHERE drawing_id=%s
            ORDER BY id DESC
            LIMIT 80
            """,
            (drawing_id,),
        )
        result = []
        for row in rows:
            item = dict(row)
            item["old_status_label"] = _status_label(item.get("old_status"))
            item["new_status_label"] = _status_label(item.get("new_status"))
            result.append(item)
        return result

    def _add_change_log(drawing, action, new_status=None, reason="", impact_scope="", change_no=""):
        execute_db(
            """
            INSERT INTO engineering_drawing_change_logs
                (drawing_id, action, change_no, old_status, new_status, reason, impact_scope, operator_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                drawing["id"],
                action,
                change_no,
                drawing.get("status"),
                new_status or drawing.get("status"),
                reason,
                impact_scope,
                session.get("user_id"),
            ),
        )

    @app.get("/engineering/drawings", endpoint="engineering_drawing_list")
    @login_required
    def drawing_list():
        export_requested = _export_format() == "xlsx" or request.args.get("export") == "csv"
        if export_requested and not _require_drawing_action("export"):
            return redirect("/engineering/drawings")
        filters = _drawing_filters()
        per_page = _positive_int(request.args.get("per_page"), 50, 20, 200)
        total_count = _drawing_count(query_one, filters)
        pagination = _pagination(total_count, _positive_int(request.args.get("page"), 1, 1, 999999), per_page)
        rows = _drawing_list_rows(
            query_rows,
            filters,
            5000 if export_requested else pagination["per_page"],
            0 if export_requested else pagination["offset"],
        )
        if export_requested:
            return _export_drawings(rows)
        return render_template(
            "engineering_drawing_list.html",
            rows=rows,
            filters=filters,
            pagination=pagination,
            status_options=(("", "全部状态"),) + DRAWING_STATUS_OPTIONS,
            drawing_type_options=(("", "全部类型"),) + DRAWING_TYPE_OPTIONS,
            sort_options=DRAWING_SORT_COLUMNS,
            can_create=_has_drawing_action("create"),
            can_edit=_has_drawing_action("edit"),
            can_audit=_has_drawing_action("audit"),
            can_operate=_has_drawing_action("operate"),
            can_export=_has_drawing_action("export"),
        )

    @app.get("/engineering/drawings/import-template", endpoint="engineering_drawing_import_template")
    @login_required
    def drawing_import_template():
        if not _require_drawing_action("export"):
            return redirect("/engineering/drawings")
        rows = [[
            "图号", "版本", "图纸名称", "图纸类型", "状态", "负责人", "发布日期", "生效日期",
            "作废日期", "发布单号", "批准人", "批准日期", "来源系统", "文件位置", "受控等级",
            "文件格式", "校验值", "变更原因", "备注", "物料编码", "BOM编号", "BOM版本",
            "项目号", "机号", "使用范围", "引用说明", "是否同步物料图号",
        ]]
        rows.append([
            "DRW-GTM-001", "A", "滚筒研磨机总装图", "assembly", "draft", "工程部", "",
            "", "", "", "", "", "设计/PDM", "\\\\fileserver\\drawings\\DRW-GTM-001-A.pdf",
            "internal", "PDF", "", "初始导入", "", "MAT-001", "BOM-GTM-001", "A",
            "PRJ-2026-001", "SN-001", "装配", "总装使用", "是",
        ])
        return _csv_response("engineering-drawing-import-template.csv", rows)

    def _find_product_by_code(code: str):
        if not code:
            return None
        return query_one("SELECT id, code FROM products WHERE code=%s", (code,))

    def _find_bom(bom_no: str, version: str = ""):
        if not bom_no:
            return None, ""
        if version:
            return query_one("SELECT id, bom_no, product_id, status FROM boms WHERE bom_no=%s AND version=%s", (bom_no, version)), ""
        rows = query_rows("SELECT id, bom_no, product_id, status FROM boms WHERE bom_no=%s ORDER BY id DESC LIMIT 2", (bom_no,))
        if len(rows) == 1:
            return rows[0], ""
        if len(rows) > 1:
            return None, "BOM编号存在多个版本，请填写BOM版本。"
        return None, "BOM编号不存在。"

    def _insert_link_if_needed(drawing_id: int, product_id, bom_id, project_code: str, serial_no: str, usage_scope: str, remark: str) -> bool:
        if not any([product_id, bom_id, project_code, serial_no, usage_scope, remark]):
            return False
        exists = query_one(
            """
            SELECT id FROM engineering_drawing_links
            WHERE drawing_id=%s
              AND COALESCE(product_id, 0)=COALESCE(%s, 0)
              AND COALESCE(bom_id, 0)=COALESCE(%s, 0)
              AND COALESCE(project_code, '')=COALESCE(%s, '')
              AND COALESCE(serial_no, '')=COALESCE(%s, '')
              AND COALESCE(usage_scope, '')=COALESCE(%s, '')
            LIMIT 1
            """,
            (drawing_id, product_id, bom_id, project_code, serial_no, usage_scope),
        )
        if exists:
            return False
        execute_db(
            """
            INSERT INTO engineering_drawing_links
                (drawing_id, product_id, bom_id, project_code, serial_no, usage_scope, remark)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            (drawing_id, product_id, bom_id, project_code, serial_no, usage_scope, remark),
        )
        return True

    @app.route("/engineering/drawings/import", methods=["GET", "POST"], endpoint="engineering_drawing_import")
    @login_required
    def drawing_import():
        if request.method == "GET":
            if not _require_drawing_action("create"):
                return redirect("/engineering/drawings")
            return render_template("engineering_drawing_import.html")
        if not (_has_drawing_action("create") and _has_drawing_action("operate")):
            flash("当前账号没有图纸导入权限。", "warning")
            return redirect("/engineering/drawings")
        file = request.files.get("file")
        if not file or not file.filename:
            flash("请选择CSV文件。", "warning")
            return redirect("/engineering/drawings/import")
        rows, errors = read_validated_csv_upload(file)
        mode = _text("mode") or "upsert"
        if errors:
            for error in errors[:10]:
                flash(error, "warning")
            return redirect("/engineering/drawings/import")
        inserted = updated = linked = skipped = 0
        import_errors = []
        for line_no, row in enumerate(rows, start=2):
            if not any((value or "").strip() for value in row.values()):
                continue
            drawing_no = csv_cell(row, "drawing_no", "图号")
            version = csv_cell(row, "version", "版本") or "A"
            drawing_name = csv_cell(row, "drawing_name", "图纸名称")
            drawing_type = csv_cell(row, "drawing_type", "图纸类型") or "part"
            status = csv_cell(row, "status", "状态") or "draft"
            security_level = csv_cell(row, "security_level", "受控等级") or "normal"
            if not drawing_no or not version or not drawing_name:
                import_errors.append(f"第 {line_no} 行缺少图号、版本或图纸名称。")
                continue
            if not _valid_version(version):
                import_errors.append(f"第 {line_no} 行版本号格式不正确。")
                continue
            if drawing_type not in VALID_DRAWING_TYPES or status not in VALID_DRAWING_STATUSES or security_level not in VALID_SECURITY_LEVELS:
                import_errors.append(f"第 {line_no} 行图纸类型、状态或受控等级不正确。")
                continue
            date_values = {
                "released_date": _parse_date_text(csv_cell(row, "released_date", "发布日期")),
                "effective_date": _parse_date_text(csv_cell(row, "effective_date", "生效日期")),
                "obsolete_date": _parse_date_text(csv_cell(row, "obsolete_date", "作废日期")),
                "approval_date": _parse_date_text(csv_cell(row, "approval_date", "批准日期")),
            }
            for label, key in (("发布日期", "released_date"), ("生效日期", "effective_date"), ("作废日期", "obsolete_date"), ("批准日期", "approval_date")):
                if csv_cell(row, key, label) and not date_values[key]:
                    import_errors.append(f"第 {line_no} 行{label}格式不正确，请使用YYYY-MM-DD。")
            if import_errors and len(import_errors) >= 50:
                break
            existing = query_one("SELECT id FROM engineering_drawings WHERE drawing_no=%s AND version=%s", (drawing_no, version))
            values = (
                drawing_name,
                drawing_type,
                status,
                csv_cell(row, "owner", "负责人"),
                date_values["released_date"],
                date_values["effective_date"],
                date_values["obsolete_date"],
                csv_cell(row, "release_no", "发布单号"),
                csv_cell(row, "approved_by", "批准人"),
                date_values["approval_date"],
                csv_cell(row, "source_system", "来源系统") or "设计/PDM",
                csv_cell(row, "file_location", "文件位置"),
                security_level,
                csv_cell(row, "file_format", "文件格式"),
                csv_cell(row, "checksum", "校验值"),
                csv_cell(row, "change_reason", "变更原因"),
                csv_cell(row, "remark", "备注"),
            )
            if existing:
                if mode == "insert_only":
                    drawing_id = existing["id"]
                    skipped += 1
                else:
                    execute_db(
                        """
                        UPDATE engineering_drawings
                        SET drawing_name=%s, drawing_type=%s, status=%s, owner=COALESCE(NULLIF(%s,''), owner),
                            released_date=COALESCE(%s, released_date), effective_date=COALESCE(%s, effective_date),
                            obsolete_date=COALESCE(%s, obsolete_date), release_no=COALESCE(NULLIF(%s,''), release_no),
                            approved_by=COALESCE(NULLIF(%s,''), approved_by), approval_date=COALESCE(%s, approval_date),
                            source_system=COALESCE(NULLIF(%s,''), source_system), file_location=COALESCE(NULLIF(%s,''), file_location),
                            security_level=%s, file_format=COALESCE(NULLIF(%s,''), file_format),
                            checksum=COALESCE(NULLIF(%s,''), checksum), change_reason=COALESCE(NULLIF(%s,''), change_reason),
                            remark=COALESCE(NULLIF(%s,''), remark), updated_at=CURRENT_TIMESTAMP
                        WHERE id=%s
                        """,
                        values + (existing["id"],),
                    )
                    drawing_id = existing["id"]
                    updated += 1
            else:
                created = execute_and_return(
                    """
                    INSERT INTO engineering_drawings
                        (drawing_no, version, drawing_name, drawing_type, status, owner,
                         released_date, effective_date, obsolete_date, release_no, approved_by, approval_date,
                         source_system, file_location, security_level, file_format, checksum,
                         change_reason, remark, created_by)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id
                    """,
                    (drawing_no, version) + values + (session.get("user_id"),),
                )
                drawing_id = created["id"]
                inserted += 1
            product = _find_product_by_code(csv_cell(row, "product_code", "物料编码"))
            if csv_cell(row, "product_code", "物料编码") and not product:
                import_errors.append(f"第 {line_no} 行物料编码不存在。")
                continue
            bom, bom_error = _find_bom(csv_cell(row, "bom_no", "BOM编号"), csv_cell(row, "bom_version", "BOM版本"))
            if bom_error and csv_cell(row, "bom_no", "BOM编号"):
                import_errors.append(f"第 {line_no} 行{bom_error}")
                continue
            project_code = csv_cell(row, "project_code", "项目号")
            serial_no = csv_cell(row, "serial_no", "机号")
            usage_scope = csv_cell(row, "usage_scope", "使用范围")
            link_remark = csv_cell(row, "link_remark", "引用说明")
            if usage_scope and usage_scope not in VALID_USAGE_SCOPES:
                import_errors.append(f"第 {line_no} 行使用范围不正确。")
                continue
            if _insert_link_if_needed(drawing_id, product["id"] if product else None, bom["id"] if bom else None, project_code, serial_no, usage_scope, link_remark):
                linked += 1
            if product and csv_cell(row, "sync_product_drawing_no", "是否同步物料图号") in {"是", "Y", "y", "1", "true", "True"}:
                execute_db("UPDATE products SET drawing_no=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s", (drawing_no, product["id"]))
            if len(import_errors) >= 50:
                break
        if import_errors:
            for error in import_errors[:10]:
                flash(error, "warning")
            flash(f"导入完成但存在 {len(import_errors)} 条错误，请修正后重导。", "warning")
        if log_action:
            log_action("导入图纸台账", "engineering_drawings", f"新增{inserted} 更新{updated} 引用{linked} 跳过{skipped}")
        flash(f"图纸导入完成：新增 {inserted}，更新 {updated}，新增引用 {linked}，跳过 {skipped}。", "success")
        return redirect("/engineering/drawings")

    @app.route("/engineering/drawings/new", methods=["GET", "POST"], endpoint="engineering_drawing_new")
    @login_required
    def drawing_new():
        if request.method == "POST" and not _require_drawing_action("create"):
            return redirect("/engineering/drawings")
        if request.method == "POST":
            errors = _master_validation_errors(status="draft")
            if errors:
                flash("保存失败：" + "；".join(errors), "warning")
                return redirect("/engineering/drawings/new")
            drawing_no = _text("drawing_no")
            version = _text("version") or "A"
            exists = query_one(
                "SELECT id FROM engineering_drawings WHERE drawing_no=%s AND version=%s",
                (drawing_no, version),
            )
            if exists:
                flash("同一图号和版本已存在，请改为修改原记录或创建新版本。", "warning")
                return redirect(f"/engineering/drawings/{exists['id']}")
            row = execute_and_return(
                """
                INSERT INTO engineering_drawings
                    (drawing_no, version, drawing_name, drawing_type, status, owner,
                     released_date, effective_date, obsolete_date, release_no, approved_by, approval_date,
                     source_system, file_location, security_level, file_format, checksum,
                     change_reason, remark, created_by)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
                """,
                (
                    drawing_no,
                    version,
                    _text("drawing_name"),
                    _text("drawing_type") or "part",
                    "draft",
                    _text("owner"),
                    _date_or_none("released_date"),
                    _date_or_none("effective_date"),
                    _date_or_none("obsolete_date"),
                    _text("release_no"),
                    _text("approved_by"),
                    _date_or_none("approval_date"),
                    _text("source_system") or "设计/PDM",
                    _text("file_location"),
                    _text("security_level") or "normal",
                    _text("file_format"),
                    _text("checksum"),
                    _text("change_reason"),
                    _text("remark"),
                    session.get("user_id"),
                ),
            )
            drawing = _get_drawing(row["id"])
            _save_link(drawing, update_product=True)
            _add_change_log(drawing, "新增", new_status=drawing.get("status"), reason=_text("change_reason"))
            if log_action:
                log_action("新增图纸台账", drawing_no, version)
            flash("图纸台账已保存。", "success")
            return redirect(f"/engineering/drawings/{row['id']}")
        return render_template(
            "engineering_drawing_form.html",
            drawing={"released_date": date.today().isoformat(), "source_system": "设计/PDM", "version": "A", "security_level": "normal"},
            options=_drawing_options(query_rows),
            status_options=DRAWING_STATUS_OPTIONS,
            drawing_type_options=DRAWING_TYPE_OPTIONS,
            security_level_options=SECURITY_LEVEL_OPTIONS,
            action_url="/engineering/drawings/new",
            mode="new",
        )

    @app.route("/engineering/drawings/<int:drawing_id>/edit", methods=["GET", "POST"], endpoint="engineering_drawing_edit")
    @login_required
    def drawing_edit(drawing_id):
        drawing = _get_drawing(drawing_id)
        if not drawing:
            flash("图纸台账不存在。", "warning")
            return redirect("/engineering/drawings")
        if request.method == "POST":
            if not _require_drawing_action("edit"):
                return redirect(f"/engineering/drawings/{drawing_id}")
            errors = _master_validation_errors(status=drawing.get("status"))
            if errors:
                flash("保存失败：" + "；".join(errors), "warning")
                return redirect(f"/engineering/drawings/{drawing_id}/edit")
            drawing_no = _text("drawing_no")
            version = _text("version") or "A"
            if drawing.get("status") in {"released", "changing", "obsolete"}:
                protected = ("drawing_no", "version", "file_location", "checksum")
                changed = [field for field in protected if (_text(field) or "") != (str(drawing.get(field) or ""))]
                if changed:
                    flash("已发布、变更中或已作废图纸不能普通修改图号、版本、受控文件位置和校验值；请复制新版本或发起变更。", "warning")
                    return redirect(f"/engineering/drawings/{drawing_id}/edit")
            exists = query_one(
                "SELECT id FROM engineering_drawings WHERE drawing_no=%s AND version=%s AND id<>%s",
                (drawing_no, version, drawing_id),
            )
            if exists:
                flash("同一图号和版本已存在，不能重复。", "warning")
                return redirect(f"/engineering/drawings/{drawing_id}/edit")
            old_status = drawing.get("status")
            execute_db(
                """
                UPDATE engineering_drawings
                SET drawing_no=%s, version=%s, drawing_name=%s, drawing_type=%s, status=%s,
                    owner=%s, released_date=%s, effective_date=%s, obsolete_date=%s,
                    release_no=%s, approved_by=%s, approval_date=%s, source_system=%s,
                    file_location=%s, security_level=%s, file_format=%s, checksum=%s,
                    change_reason=%s, remark=%s, updated_at=CURRENT_TIMESTAMP
                WHERE id=%s
                """,
                (
                    drawing_no,
                    version,
                    _text("drawing_name"),
                    _text("drawing_type") or "part",
                    drawing.get("status") or "draft",
                    _text("owner"),
                    _date_or_none("released_date"),
                    _date_or_none("effective_date"),
                    _date_or_none("obsolete_date"),
                    _text("release_no"),
                    _text("approved_by"),
                    _date_or_none("approval_date"),
                    _text("source_system") or "设计/PDM",
                    _text("file_location"),
                    _text("security_level") or "normal",
                    _text("file_format"),
                    _text("checksum"),
                    _text("change_reason"),
                    _text("remark"),
                    drawing_id,
                ),
            )
            updated = _get_drawing(drawing_id)
            _add_change_log(updated, "修改", new_status=updated.get("status"), reason=_text("change_reason"))
            if old_status != updated.get("status"):
                _add_change_log(updated, "状态调整", new_status=updated.get("status"), reason=f"{_status_label(old_status)} -> {updated['status_label']}")
            if log_action:
                log_action("修改图纸台账", drawing_no, version)
            flash("图纸台账已更新。", "success")
            return redirect(f"/engineering/drawings/{drawing_id}")
        return render_template(
            "engineering_drawing_form.html",
            drawing=drawing,
            options=_drawing_options(query_rows),
            status_options=DRAWING_STATUS_OPTIONS,
            drawing_type_options=DRAWING_TYPE_OPTIONS,
            security_level_options=SECURITY_LEVEL_OPTIONS,
            action_url=f"/engineering/drawings/{drawing_id}/edit",
            mode="edit",
        )

    def _save_link(drawing, update_product=False):
        product_id = _int_or_none("product_id")
        bom_id = _int_or_none("bom_id")
        project_code = _text("project_code")
        serial_no = _text("serial_no")
        usage_scope = _text("usage_scope")
        link_remark = _text("link_remark")
        errors = []
        if not any([product_id, bom_id, project_code, serial_no, usage_scope, link_remark]):
            errors.append("请至少选择物料、BOM、项目号、机号或填写使用范围。")
        if not usage_scope:
            errors.append("使用范围不能为空。")
        elif usage_scope not in VALID_USAGE_SCOPES:
            errors.append("使用范围不正确。")
        product = query_one("SELECT id FROM products WHERE id=%s", (product_id,)) if product_id else None
        bom = query_one("SELECT id, product_id, status FROM boms WHERE id=%s", (bom_id,)) if bom_id else None
        if product_id and not product:
            errors.append("关联物料不存在。")
        if bom_id and not bom:
            errors.append("关联BOM不存在。")
        if bom and (bom.get("status") or "").strip() in {"已作废", "作废", "void", "voided", "cancelled"}:
            errors.append("已作废BOM不能关联图纸。")
        if bom and product_id and bom.get("product_id") and int(bom.get("product_id")) != int(product_id):
            errors.append("BOM关联物料与所选物料不一致。")
        exists = query_one(
            """
            SELECT id FROM engineering_drawing_links
            WHERE drawing_id=%s
              AND COALESCE(product_id, 0)=COALESCE(%s, 0)
              AND COALESCE(bom_id, 0)=COALESCE(%s, 0)
              AND COALESCE(project_code, '')=COALESCE(%s, '')
              AND COALESCE(serial_no, '')=COALESCE(%s, '')
              AND COALESCE(usage_scope, '')=COALESCE(%s, '')
            LIMIT 1
            """,
            (drawing["id"], product_id, bom_id, project_code, serial_no, usage_scope),
        )
        if exists:
            errors.append("该业务引用已存在。")
        if errors:
            return errors
        _insert_link_if_needed(drawing["id"], product_id, bom_id, project_code, serial_no, usage_scope, link_remark)
        if update_product and product_id:
            execute_db(
                "UPDATE products SET drawing_no=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
                (drawing.get("drawing_no"), product_id),
            )
        return []

    @app.post("/engineering/drawings/<int:drawing_id>/links", endpoint="engineering_drawing_add_link")
    @login_required
    def drawing_add_link(drawing_id):
        drawing = _get_drawing(drawing_id)
        if not drawing:
            flash("图纸台账不存在。", "warning")
            return redirect("/engineering/drawings")
        if not _require_drawing_action("operate"):
            return redirect(f"/engineering/drawings/{drawing_id}")
        if drawing.get("status") != "released":
            flash("新增引用失败：只有已发布图纸可以新增业务引用。", "warning")
            return redirect(f"/engineering/drawings/{drawing_id}")
        errors = _save_link(drawing, update_product=True)
        if errors:
            flash("新增引用失败：" + "；".join(errors), "warning")
            return redirect(f"/engineering/drawings/{drawing_id}")
        _add_change_log(drawing, "维护引用", reason=_text("link_remark"), impact_scope=_text("usage_scope"))
        if log_action:
            log_action("维护图纸业务引用", drawing.get("drawing_no") or "", drawing.get("version") or "")
        flash("图纸业务引用已保存。", "success")
        return redirect(f"/engineering/drawings/{drawing_id}")

    @app.post("/engineering/drawings/<int:drawing_id>/links/<int:link_id>/delete", endpoint="engineering_drawing_delete_link")
    @login_required
    def drawing_delete_link(drawing_id, link_id):
        if not _require_drawing_action("operate"):
            return redirect(f"/engineering/drawings/{drawing_id}")
        drawing = _get_drawing(drawing_id)
        execute_db("DELETE FROM engineering_drawing_links WHERE id=%s AND drawing_id=%s", (link_id, drawing_id))
        if drawing:
            _add_change_log(drawing, "删除引用", reason="删除业务引用")
        flash("图纸业务引用已删除。", "success")
        return redirect(f"/engineering/drawings/{drawing_id}")

    @app.post("/engineering/drawings/<int:drawing_id>/release", endpoint="engineering_drawing_release")
    @login_required
    def drawing_release(drawing_id):
        drawing = _get_drawing(drawing_id)
        if not drawing:
            flash("图纸台账不存在。", "warning")
            return redirect("/engineering/drawings")
        if not _require_drawing_action("audit"):
            return redirect(f"/engineering/drawings/{drawing_id}")
        if drawing.get("status") not in {"draft", "changing"}:
            flash("只有草稿或变更中的图纸可以发布。", "warning")
            return redirect(f"/engineering/drawings/{drawing_id}")
        errors = _release_ready_errors(drawing, _text("release_no"), _text("approved_by"))
        if errors:
            flash("发布失败：" + "；".join(errors), "warning")
            return redirect(f"/engineering/drawings/{drawing_id}#releasePanel")
        execute_db(
            """
            UPDATE engineering_drawings
            SET status='released',
                released_date=COALESCE(released_date, CURRENT_DATE),
                effective_date=COALESCE(effective_date, CURRENT_DATE),
                approval_date=COALESCE(approval_date, CURRENT_DATE),
                approved_by=COALESCE(NULLIF(%s,''), approved_by),
                release_no=COALESCE(NULLIF(%s,''), release_no),
                updated_at=CURRENT_TIMESTAMP
            WHERE id=%s
            """,
            (_text("approved_by"), _text("release_no"), drawing_id),
        )
        _add_change_log(drawing, "发布", new_status="released", reason=_text("reason"), impact_scope=_text("impact_scope"), change_no=_text("release_no"))
        if log_action:
            log_action("发布图纸版本", drawing.get("drawing_no") or "", drawing.get("version") or "")
        flash("图纸版本已发布。", "success")
        return redirect(f"/engineering/drawings/{drawing_id}")

    @app.post("/engineering/drawings/<int:drawing_id>/changing", endpoint="engineering_drawing_mark_changing")
    @login_required
    def drawing_mark_changing(drawing_id):
        drawing = _get_drawing(drawing_id)
        if not drawing:
            flash("图纸台账不存在。", "warning")
            return redirect("/engineering/drawings")
        if not _require_drawing_action("operate"):
            return redirect(f"/engineering/drawings/{drawing_id}")
        if drawing.get("status") != "released":
            flash("只有已发布图纸可以发起变更。", "warning")
            return redirect(f"/engineering/drawings/{drawing_id}")
        if not _text("reason") or not _text("change_no"):
            flash("发起变更失败：变更单号和变更原因不能为空。", "warning")
            return redirect(f"/engineering/drawings/{drawing_id}#changePanel")
        execute_db("UPDATE engineering_drawings SET status='changing', updated_at=CURRENT_TIMESTAMP WHERE id=%s", (drawing_id,))
        _add_change_log(drawing, "发起变更", new_status="changing", reason=_text("reason"), impact_scope=_text("impact_scope"), change_no=_text("change_no"))
        if log_action:
            log_action("发起图纸变更", drawing.get("drawing_no") or "", drawing.get("version") or "")
        flash("图纸已标记为变更中。", "success")
        return redirect(f"/engineering/drawings/{drawing_id}")

    @app.post("/engineering/drawings/<int:drawing_id>/obsolete", endpoint="engineering_drawing_obsolete")
    @login_required
    def drawing_obsolete(drawing_id):
        drawing = _get_drawing(drawing_id)
        if not drawing:
            flash("图纸台账不存在。", "warning")
            return redirect("/engineering/drawings")
        if not _require_drawing_action("audit"):
            return redirect(f"/engineering/drawings/{drawing_id}")
        if drawing.get("status") not in {"released", "changing"}:
            flash("只有已发布或变更中的图纸可以作废。", "warning")
            return redirect(f"/engineering/drawings/{drawing_id}")
        if not _text("reason") or not _text("change_no") or not _text("impact_scope"):
            flash("作废失败：作废单号、作废原因和下游处理说明不能为空。", "warning")
            return redirect(f"/engineering/drawings/{drawing_id}#obsoletePanel")
        open_rows = _open_downstream_rows(drawing_id)
        if open_rows and _text("force_obsolete") != "yes":
            flash(f"作废失败：存在 {len(open_rows)} 条未关闭下游引用，请先确认替代版本；如确需作废，请勾选强制作废并填写下游处理。", "warning")
            return redirect(f"/engineering/drawings/{drawing_id}#obsoletePanel")
        execute_db(
            """
            UPDATE engineering_drawings
            SET status='obsolete', obsolete_date=COALESCE(obsolete_date, CURRENT_DATE), updated_at=CURRENT_TIMESTAMP
            WHERE id=%s
            """,
            (drawing_id,),
        )
        _add_change_log(drawing, "作废", new_status="obsolete", reason=_text("reason"), impact_scope=_text("impact_scope"), change_no=_text("change_no"))
        if log_action:
            log_action("作废图纸版本", drawing.get("drawing_no") or "", drawing.get("version") or "")
        flash("图纸版本已作废，不能再新增业务引用。", "success")
        return redirect(f"/engineering/drawings/{drawing_id}")

    @app.post("/engineering/drawings/<int:drawing_id>/changes", endpoint="engineering_drawing_add_change")
    @login_required
    def drawing_add_change(drawing_id):
        drawing = _get_drawing(drawing_id)
        if not drawing:
            flash("图纸台账不存在。", "warning")
            return redirect("/engineering/drawings")
        if not _require_drawing_action("operate"):
            return redirect(f"/engineering/drawings/{drawing_id}")
        _add_change_log(drawing, _text("action") or "记录", reason=_text("reason"), impact_scope=_text("impact_scope"), change_no=_text("change_no"))
        flash("图纸变更记录已保存。", "success")
        return redirect(f"/engineering/drawings/{drawing_id}")

    @app.post("/engineering/drawings/<int:drawing_id>/copy-version", endpoint="engineering_drawing_copy_version")
    @login_required
    def drawing_copy_version(drawing_id):
        drawing = _get_drawing(drawing_id)
        if not drawing:
            flash("图纸台账不存在。", "warning")
            return redirect("/engineering/drawings")
        if not (_has_drawing_action("create") and _has_drawing_action("operate")):
            flash("当前账号没有图纸升版权限。", "warning")
            return redirect(f"/engineering/drawings/{drawing_id}")
        if drawing.get("status") == "draft":
            flash("复制升版失败：草稿图纸不能复制新版本。", "warning")
            return redirect(f"/engineering/drawings/{drawing_id}")
        new_version = _text("new_version")
        if not new_version:
            flash("复制升版失败：新版本号不能为空。", "warning")
            return redirect(f"/engineering/drawings/{drawing_id}")
        if not _valid_version(new_version):
            flash("复制升版失败：新版本号格式不正确。", "warning")
            return redirect(f"/engineering/drawings/{drawing_id}")
        if new_version == drawing.get("version"):
            flash("复制升版失败：新版本号不能等于旧版本。", "warning")
            return redirect(f"/engineering/drawings/{drawing_id}")
        if not _text("reason") or not _text("change_no"):
            flash("复制升版失败：升版原因和变更单号不能为空。", "warning")
            return redirect(f"/engineering/drawings/{drawing_id}#copyVersionPanel")
        exists = query_one(
            "SELECT id FROM engineering_drawings WHERE drawing_no=%s AND version=%s",
            (drawing.get("drawing_no"), new_version),
        )
        if exists:
            flash("新版本已存在。", "warning")
            return redirect(f"/engineering/drawings/{exists['id']}")
        row = execute_and_return(
            """
            INSERT INTO engineering_drawings
                (drawing_no, version, drawing_name, drawing_type, status, owner, source_system,
                 file_location, security_level, file_format, previous_drawing_id, change_reason,
                 remark, created_by)
            VALUES (%s,%s,%s,%s,'draft',%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                drawing.get("drawing_no"),
                new_version,
                drawing.get("drawing_name"),
                drawing.get("drawing_type"),
                drawing.get("owner"),
                drawing.get("source_system"),
                drawing.get("file_location"),
                drawing.get("security_level"),
                drawing.get("file_format"),
                drawing_id,
                _text("reason") or drawing.get("change_reason"),
                drawing.get("remark"),
                session.get("user_id"),
            ),
        )
        new_drawing = _get_drawing(row["id"])
        _add_change_log(new_drawing, "升版创建", reason=_text("reason"), impact_scope=_text("impact_scope"), change_no=_text("change_no"))
        if log_action:
            log_action("复制图纸新版本", drawing.get("drawing_no") or "", new_version)
        flash("新版本草稿已创建，请补齐发布信息后发布。", "success")
        return redirect(f"/engineering/drawings/{row['id']}")

    @app.get("/engineering/drawings/<int:drawing_id>", endpoint="engineering_drawing_detail")
    @login_required
    def drawing_detail(drawing_id):
        drawing = _get_drawing(drawing_id)
        if not drawing:
            flash("图纸台账不存在。", "warning")
            return redirect("/engineering/drawings")
        same_no_versions = query_rows(
            """
            SELECT id, drawing_no, version, status, released_date, drawing_name
            FROM engineering_drawings
            WHERE drawing_no=%s
            ORDER BY released_date DESC NULLS LAST, id DESC
            """,
            (drawing.get("drawing_no"),),
        )
        versions = []
        for row in same_no_versions:
            item = dict(row)
            item["status_label"] = _status_label(item.get("status"))
            item["status_badge"] = _status_badge(item.get("status"))
            versions.append(item)
        downstream = _downstream_rows(drawing_id)
        open_downstream = _open_downstream_rows(drawing_id)
        return render_template(
            "engineering_drawing_detail.html",
            drawing=drawing,
            links=_drawing_links(drawing_id),
            versions=versions,
            downstream=downstream,
            open_downstream=open_downstream,
            change_logs=_drawing_change_logs(drawing_id),
            options=_drawing_options(query_rows),
            can_edit=_has_drawing_action("edit"),
            can_audit=_has_drawing_action("audit"),
            can_operate=_has_drawing_action("operate"),
            can_create=_has_drawing_action("create"),
        )
