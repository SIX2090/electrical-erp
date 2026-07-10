from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from services.data_scope_service import (
    BYPASS_ROLES,
    SUPPORTED_SCOPE_TYPES,
    normalize_role,
)


SUBJECT_TYPES = {"user", "role"}
PERMISSION_TYPES = {"view", "edit", "approve", "export"}
logger = logging.getLogger(__name__)
SCOPE_LABELS = {
    "project": "项目",
    "cabinet": "柜号",
    "department": "部门",
    "customer": "客户",
    "supplier": "供应商",
}
SUBJECT_LABELS = {
    "user": "用户",
    "role": "角色",
}
PERMISSION_LABELS = {
    "view": "查看",
    "edit": "编辑",
    "approve": "审批",
    "export": "导出",
}
ROLE_OPTIONS = [
    ("admin", "管理员"),
    ("manager", "经理"),
    ("sales", "销售"),
    ("purchase", "采购"),
    ("warehouse", "仓库"),
    ("production", "生产"),
    ("service", "售后"),
    ("finance", "财务"),
    ("staff", "员工"),
]


def _clean(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _label_for_scope(scope_type: str, scope_id: str, scope_label: str = "") -> str:
    label = _clean(scope_label)
    if label:
        return label
    return f"{SCOPE_LABELS.get(scope_type, scope_type)}:{scope_id}"


def list_rules(
    query_db,
    *,
    subject_type: Optional[str] = None,
    subject_id: Optional[str] = None,
    scope_type: Optional[str] = None,
    status: Optional[str] = None,
) -> List[Dict]:
    """List data permission rules with optional filters.

    Joins users table for subject labels when subject_type='user'.
    """
    where_parts: List[str] = []
    params: List[Any] = []
    if subject_type:
        where_parts.append("r.subject_type=%s")
        params.append(subject_type)
    if subject_id:
        where_parts.append("r.subject_id=%s")
        params.append(subject_id)
    if scope_type:
        where_parts.append("r.scope_type=%s")
        params.append(scope_type)
    if status:
        where_parts.append("r.status=%s")
        params.append(status)
    where_sql = "WHERE " + " AND ".join(where_parts) if where_parts else ""
    rows = query_db(
        f"""
        SELECT r.id, r.subject_type, r.subject_id, r.scope_type, r.scope_id,
               r.scope_label, r.permission, r.status, r.created_by, r.created_at,
               u.username AS subject_label
        FROM data_permission_rules r
        LEFT JOIN users u ON r.subject_type='user' AND u.id::text=r.subject_id
        {where_sql}
        ORDER BY r.subject_type, r.subject_id, r.scope_type, r.id DESC
        """,
        tuple(params),
    ) or []
    result: List[Dict] = []
    for row in rows:
        item = dict(row)
        item["subject_type_label"] = SUBJECT_LABELS.get(item.get("subject_type"), item.get("subject_type") or "")
        item["scope_type_label"] = SCOPE_LABELS.get(item.get("scope_type"), item.get("scope_type") or "")
        item["permission_label"] = PERMISSION_LABELS.get(item.get("permission"), item.get("permission") or "")
        item["status_label"] = "启用" if item.get("status") == "enabled" else "停用"
        item["scope_display"] = _label_for_scope(
            item.get("scope_type") or "",
            item.get("scope_id") or "",
            item.get("scope_label") or "",
        )
        if not item.get("subject_label"):
            if item.get("subject_type") == "role":
                item["subject_label"] = dict(ROLE_OPTIONS).get(item.get("subject_id"), item.get("subject_id") or "")
            else:
                item["subject_label"] = item.get("subject_id") or ""
        result.append(item)
    return result


def create_rule(
    query_db,
    execute_db,
    execute_and_return,
    *,
    subject_type: str,
    subject_id: str,
    scope_type: str,
    scope_id: str,
    scope_label: Optional[str] = None,
    permission: str = "view",
    created_by: Optional[int] = None,
) -> int:
    """Create a new data permission rule.

    Also creates a corresponding data_scope_rules entry for backward compatibility.
    Returns the new rule id.
    """
    subject_type = _clean(subject_type)
    subject_id = _clean(subject_id)
    scope_type = _clean(scope_type)
    scope_id = _clean(scope_id)
    permission = _clean(permission) or "view"
    scope_label = _clean(scope_label)
    if subject_type not in SUBJECT_TYPES:
        raise ValueError(f"subject_type must be one of {SUBJECT_TYPES}")
    if not subject_id:
        raise ValueError("subject_id is required")
    if scope_type not in SUPPORTED_SCOPE_TYPES:
        raise ValueError(f"scope_type must be one of {SUPPORTED_SCOPE_TYPES}")
    if not scope_id:
        raise ValueError("scope_id is required")
    if permission not in PERMISSION_TYPES:
        raise ValueError(f"permission must be one of {PERMISSION_TYPES}")
    if not scope_label:
        scope_label = _resolve_scope_label(query_db, scope_type, scope_id)

    duplicate = query_db(
        """
        SELECT id FROM data_permission_rules
        WHERE subject_type=%s AND subject_id=%s AND scope_type=%s
          AND scope_id=%s AND permission=%s
        """,
        (subject_type, subject_id, scope_type, scope_id, permission),
        one=True,
    )
    if duplicate:
        raise ValueError("相同主体、范围和权限的规则已存在")

    row = execute_and_return(
        """
        INSERT INTO data_permission_rules
            (subject_type, subject_id, scope_type, scope_id, scope_label, permission, status, created_by)
        VALUES (%s,%s,%s,%s,%s,%s,'enabled',%s)
        RETURNING id
        """,
        (subject_type, subject_id, scope_type, scope_id, scope_label, permission, created_by),
    )
    rule_id = int((row or {}).get("id") or 0)

    # Backward-compat: mirror into data_scope_rules (scope_id -> scope_value)
    try:
        execute_db(
            """
            INSERT INTO data_scope_rules
                (subject_type, subject_id, scope_type, scope_value, permission, status, created_by)
            VALUES (%s,%s,%s,%s,%s,'enabled',%s)
            ON CONFLICT (subject_type, subject_id, scope_type, scope_value, permission)
            DO UPDATE SET status='enabled'
            """,
            (subject_type, subject_id, scope_type, scope_id, permission, created_by),
        )
    except Exception as exc:
        # 镜像失败不阻塞主操作，但记录日志便于排查
        import logging
        logging.getLogger(__name__).warning(
            "data_scope_rules mirror insert failed for rule#%s: %s", rule_id, exc,
        )

    return rule_id


def update_rule(query_db, execute_db, rule_id: int, **fields) -> bool:
    """Update a rule. Allowed fields: status, permission, scope_label.

    同步更新 data_scope_rules 镜像表，确保执行层（data_scope_service）与管理层一致。
    """
    allowed = {"status", "permission", "scope_label"}
    updates: List[str] = []
    params: List[Any] = []
    for key in ("status", "permission", "scope_label"):
        if key in fields and fields[key] is not None:
            value = _clean(fields[key])
            if key == "status" and value not in {"enabled", "disabled"}:
                raise ValueError("status must be 'enabled' or 'disabled'")
            if key == "permission" and value not in PERMISSION_TYPES:
                raise ValueError(f"permission must be one of {PERMISSION_TYPES}")
            updates.append(f"{key}=%s")
            params.append(value)
    if not updates:
        return False
    params.append(int(rule_id))
    execute_db(
        f"UPDATE data_permission_rules SET {', '.join(updates)} WHERE id=%s",
        tuple(params),
    )

    # 同步到 data_scope_rules 镜像表
    # 先读取当前规则的关键字段，用于定位镜像行
    current = query_db(
        """
        SELECT subject_type, subject_id, scope_type, scope_id, permission, status
        FROM data_permission_rules WHERE id=%s
        """,
        (int(rule_id),),
        one=True,
    )
    if current:
        mirror_updates: List[str] = []
        mirror_params: List[Any] = []
        if "status" in fields and fields["status"] is not None:
            mirror_updates.append("status=%s")
            mirror_params.append(_clean(fields["status"]))
        if "permission" in fields and fields["permission"] is not None:
            mirror_updates.append("permission=%s")
            mirror_params.append(_clean(fields["permission"]))
        if mirror_updates:
            mirror_params.extend([
                current["subject_type"], current["subject_id"],
                current["scope_type"], current["scope_id"],
            ])
            # 旧权限值用于定位镜像行
            try:
                execute_db(
                    f"""
                    UPDATE data_scope_rules SET {', '.join(mirror_updates)}
                    WHERE subject_type=%s AND subject_id=%s
                      AND scope_type=%s AND scope_value=%s
                    """,
                    tuple(mirror_params),
                )
            except Exception:
                logger.warning("Failed to sync data permission mirror rule", exc_info=True)
                pass  # 镜像同步失败不阻塞主操作，但应记录日志
    return True
    return True


def delete_rule(query_db, execute_db, rule_id: int) -> bool:
    """Delete a rule. Returns True if a row was deleted.

    同步删除 data_scope_rules 镜像表中的对应行。
    """
    # 先读取规则字段，用于定位镜像行
    current = query_db(
        """
        SELECT subject_type, subject_id, scope_type, scope_id, permission
        FROM data_permission_rules WHERE id=%s
        """,
        (int(rule_id),),
        one=True,
    )
    execute_db("DELETE FROM data_permission_rules WHERE id=%s", (int(rule_id),))
    if current:
        try:
            execute_db(
                """
                DELETE FROM data_scope_rules
                WHERE subject_type=%s AND subject_id=%s
                  AND scope_type=%s AND scope_value=%s
                """,
                (
                    current["subject_type"], current["subject_id"],
                    current["scope_type"], current["scope_id"],
                ),
            )
        except Exception:
            logger.warning("data_scope_rules mirror delete failed for rule#%s", rule_id, exc_info=True)
    return True


def get_user_permissions(query_db, user_id, role) -> Dict[str, List[str]]:
    """Get all data permissions for a user.

    Combines user-specific and role-based rules. Returns a dict with
    scope_types as keys and lists of allowed scope_ids as values.
    """
    role = normalize_role(role)
    if role in BYPASS_ROLES:
        return {scope_type: ["*"] for scope_type in SUPPORTED_SCOPE_TYPES}
    rows = query_db(
        """
        SELECT scope_type, scope_id
        FROM data_permission_rules
        WHERE status='enabled'
          AND scope_type IN ('project','cabinet','department','customer','supplier')
          AND (
            (subject_type='user' AND subject_id=%s)
            OR (subject_type='role' AND subject_id=%s)
          )
        ORDER BY scope_type, scope_id
        """,
        (str(user_id), role),
    ) or []
    result: Dict[str, List[str]] = {scope_type: [] for scope_type in SUPPORTED_SCOPE_TYPES}
    for row in rows:
        scope_type = _clean(row.get("scope_type"))
        scope_id = _clean(row.get("scope_id"))
        if scope_type in result and scope_id:
            if scope_id not in result[scope_type]:
                result[scope_type].append(scope_id)
    return result


def _resolve_scope_label(query_db, scope_type: str, scope_id: str) -> str:
    """Resolve a human-readable label for a scope id."""
    scope_type = _clean(scope_type)
    scope_id = _clean(scope_id)
    if not scope_id:
        return ""
    try:
        if scope_type == "project":
            row = query_db(
                "SELECT project_code, project_name FROM project_masters WHERE project_code=%s LIMIT 1",
                (scope_id,),
                one=True,
            )
            if row:
                return _clean(row.get("project_name")) or _clean(row.get("project_code")) or scope_id
        elif scope_type == "cabinet":
            row = query_db(
                "SELECT cabinet_no FROM cabinet_masters WHERE cabinet_no=%s LIMIT 1",
                (scope_id,),
                one=True,
            )
            if row:
                return _clean(row.get("cabinet_no")) or scope_id
        elif scope_type == "department":
            row = query_db("SELECT name FROM departments WHERE id=%s LIMIT 1", (scope_id,), one=True)
            if row:
                return _clean(row.get("name")) or scope_id
        elif scope_type == "customer":
            row = query_db("SELECT name FROM customers WHERE id=%s LIMIT 1", (scope_id,), one=True)
            if row:
                return _clean(row.get("name")) or scope_id
        elif scope_type == "supplier":
            row = query_db("SELECT name FROM suppliers WHERE id=%s LIMIT 1", (scope_id,), one=True)
            if row:
                return _clean(row.get("name")) or scope_id
    except Exception:
        logger.warning("scope label lookup failed scope_type=%s scope_id=%s", scope_type, scope_id, exc_info=True)
    return scope_id


def get_available_scopes(query_db, scope_type: str) -> List[Dict]:
    """Get available items for a scope type.

    Returns a list of dicts with 'id' and 'label' keys.
    """
    scope_type = _clean(scope_type)
    result: List[Dict] = []
    try:
        if scope_type == "project":
            rows = query_db(
                """
                SELECT project_code AS id, COALESCE(NULLIF(project_name,''), project_code) AS label
                FROM project_masters
                WHERE COALESCE(project_code,'') <> ''
                ORDER BY project_code
                LIMIT 500
                """
            ) or []
            if not rows:
                rows = query_db(
                    """
                    SELECT DISTINCT project_code AS id, project_code AS label
                    FROM sales_orders
                    WHERE COALESCE(project_code,'') <> ''
                    ORDER BY project_code
                    LIMIT 500
                    """
                ) or []
            result = [{"id": _clean(r.get("id")), "label": _clean(r.get("label")) or _clean(r.get("id"))} for r in rows]
        elif scope_type == "cabinet":
            rows = query_db(
                """
                SELECT cabinet_no AS id, cabinet_no AS label
                FROM cabinet_masters
                WHERE COALESCE(cabinet_no,'') <> ''
                ORDER BY cabinet_no
                LIMIT 500
                """
            ) or []
            if not rows:
                rows = query_db(
                    """
                    SELECT DISTINCT cabinet_no AS id, cabinet_no AS label
                    FROM work_orders
                    WHERE COALESCE(cabinet_no,'') <> ''
                    ORDER BY cabinet_no
                    LIMIT 500
                    """
                ) or []
            result = [{"id": _clean(r.get("id")), "label": _clean(r.get("label")) or _clean(r.get("id"))} for r in rows]
        elif scope_type == "department":
            rows = query_db(
                """
                SELECT id::text AS id, name AS label
                FROM departments
                WHERE COALESCE(status,'启用') NOT IN ('停用','disabled','inactive')
                ORDER BY name
                LIMIT 500
                """
            ) or []
            result = [{"id": _clean(r.get("id")), "label": _clean(r.get("label")) or _clean(r.get("id"))} for r in rows]
        elif scope_type == "customer":
            rows = query_db(
                "SELECT id::text AS id, name AS label FROM customers ORDER BY name LIMIT 500"
            ) or []
            result = [{"id": _clean(r.get("id")), "label": _clean(r.get("label")) or _clean(r.get("id"))} for r in rows]
        elif scope_type == "supplier":
            rows = query_db(
                "SELECT id::text AS id, name AS label FROM suppliers ORDER BY name LIMIT 500"
            ) or []
            result = [{"id": _clean(r.get("id")), "label": _clean(r.get("label")) or _clean(r.get("id"))} for r in rows]
    except Exception:
        logger.warning("get_available_scopes failed scope_type=%s", scope_type, exc_info=True)
        result = []
    return result


def list_access_logs(
    query_db,
    *,
    user_id: Optional[int] = None,
    resource_type: Optional[str] = None,
    allowed: Optional[bool] = None,
    limit: int = 200,
) -> List[Dict]:
    """Retrieve data access logs with filters."""
    where_parts: List[str] = []
    params: List[Any] = []
    if user_id is not None:
        where_parts.append("user_id=%s")
        params.append(int(user_id))
    if resource_type:
        where_parts.append("resource_type=%s")
        params.append(resource_type)
    if allowed is not None:
        where_parts.append("allowed=%s")
        params.append(bool(allowed))
    where_sql = "WHERE " + " AND ".join(where_parts) if where_parts else ""
    try:
        limit_int = max(1, min(int(limit or 200), 1000))
    except (TypeError, ValueError):
        limit_int = 200
    params.append(limit_int)
    rows = query_db(
        f"""
        SELECT l.id, l.user_id, l.role, l.resource_type, l.resource_id,
               l.action, l.allowed, l.reason, l.created_at,
               u.username
        FROM data_access_logs l
        LEFT JOIN users u ON u.id=l.user_id
        {where_sql}
        ORDER BY l.created_at DESC, l.id DESC
        LIMIT %s
        """,
        tuple(params),
    ) or []
    result: List[Dict] = []
    for row in rows:
        item = dict(row)
        item["allowed_label"] = "允许" if item.get("allowed") else "拒绝"
        result.append(item)
    return result


def list_export_approvals(
    query_db,
    *,
    user_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 200,
) -> List[Dict]:
    """List export actions requiring approval (recorded as data access logs with action='export')."""
    where_parts = ["l.action='export'"]
    params: List[Any] = []
    if user_id is not None:
        where_parts.append("l.user_id=%s")
        params.append(int(user_id))
    if status in {"allowed", "denied"}:
        where_parts.append("l.allowed=%s")
        params.append(status == "allowed")
    where_sql = "WHERE " + " AND ".join(where_parts)
    try:
        limit_int = max(1, min(int(limit or 200), 1000))
    except (TypeError, ValueError):
        limit_int = 200
    params.append(limit_int)
    rows = query_db(
        f"""
        SELECT l.id, l.user_id, l.role, l.resource_type, l.resource_id,
               l.action, l.allowed, l.reason, l.created_at,
               u.username
        FROM data_access_logs l
        LEFT JOIN users u ON u.id=l.user_id
        {where_sql}
        ORDER BY l.created_at DESC, l.id DESC
        LIMIT %s
        """,
        tuple(params),
    ) or []
    result: List[Dict] = []
    for row in rows:
        item = dict(row)
        item["allowed_label"] = "已批准" if item.get("allowed") else "已拒绝"
        result.append(item)
    return result


def sync_to_data_scope_rules(query_db, execute_db) -> Tuple[int, int]:
    """Sync all data_permission_rules to data_scope_rules table for backward compatibility.

    Returns (synced_count, skipped_count).
    """
    rows = query_db(
        """
        SELECT subject_type, subject_id, scope_type, scope_id, permission, status
        FROM data_permission_rules
        WHERE scope_type IN ('project','cabinet','department','customer','supplier')
        """
    ) or []
    synced = 0
    skipped = 0
    for row in rows:
        subject_type = _clean(row.get("subject_type"))
        subject_id = _clean(row.get("subject_id"))
        scope_type = _clean(row.get("scope_type"))
        scope_id = _clean(row.get("scope_id"))
        permission = _clean(row.get("permission")) or "view"
        status = _clean(row.get("status")) or "enabled"
        if not all([subject_type, subject_id, scope_type, scope_id]):
            skipped += 1
            continue
        try:
            execute_db(
                """
                INSERT INTO data_scope_rules
                    (subject_type, subject_id, scope_type, scope_value, permission, status)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (subject_type, subject_id, scope_type, scope_value, permission)
                DO UPDATE SET status=EXCLUDED.status
                """,
                (subject_type, subject_id, scope_type, scope_id, permission, status),
            )
            synced += 1
        except Exception:
            skipped += 1
    return synced, skipped


# ===== P3-B5: 真正的导出审批流 =====

EXPORT_STATUS_PENDING = "pending"
EXPORT_STATUS_APPROVED = "approved"
EXPORT_STATUS_REJECTED = "rejected"
EXPORT_STATUS_CANCELLED = "cancelled"

EXPORT_STATUS_LABELS = {
    EXPORT_STATUS_PENDING: "待审批",
    EXPORT_STATUS_APPROVED: "已批准",
    EXPORT_STATUS_REJECTED: "已拒绝",
    EXPORT_STATUS_CANCELLED: "已取消",
}


def create_export_request(
    execute_db,
    execute_and_return,
    *,
    requester_id: int,
    requester_name: str = "",
    resource_type: str,
    resource_id: str = "",
    resource_label: str = "",
    export_format: str = "csv",
    filter_summary: str = "",
) -> Optional[Dict]:
    """创建一条导出审批申请，状态为 pending。"""
    if not requester_id or not resource_type:
        return None
    row = execute_and_return(
        """
        INSERT INTO export_approval_requests
            (requester_id, requester_name, resource_type, resource_id,
             resource_label, export_format, filter_summary, status, created_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,'pending',NOW())
        RETURNING id, requester_id, requester_name, resource_type, resource_id,
                  resource_label, export_format, filter_summary, status, created_at
        """,
        (
            int(requester_id), requester_name or "", resource_type,
            resource_id or "", resource_label or "",
            export_format or "csv", filter_summary or "",
        ),
    )
    return dict(row) if row else None


def list_export_requests(
    query_db,
    *,
    status: Optional[str] = None,
    requester_id: Optional[int] = None,
    limit: int = 200,
) -> List[Dict]:
    """列出导出审批申请。"""
    where_parts = ["1=1"]
    params: List[Any] = []
    if status in EXPORT_STATUS_LABELS:
        where_parts.append("status=%s")
        params.append(status)
    if requester_id is not None:
        where_parts.append("requester_id=%s")
        params.append(int(requester_id))
    where_sql = "WHERE " + " AND ".join(where_parts)
    try:
        limit_int = max(1, min(int(limit or 200), 1000))
    except (TypeError, ValueError):
        limit_int = 200
    params.append(limit_int)
    rows = query_db(
        f"""
        SELECT id, requester_id, requester_name, resource_type, resource_id,
               resource_label, export_format, filter_summary, status,
               approver_id, approver_name, approved_at, approval_remark,
               created_at, updated_at
        FROM export_approval_requests
        {where_sql}
        ORDER BY
            CASE status WHEN 'pending' THEN 0 ELSE 1 END,
            created_at DESC
        LIMIT %s
        """,
        tuple(params),
    ) or []
    result = []
    for row in rows:
        item = dict(row)
        item["status_label"] = EXPORT_STATUS_LABELS.get(item.get("status"), item.get("status") or "")
        result.append(item)
    return result


def get_export_request(query_db, request_id: int) -> Optional[Dict]:
    """获取单条导出审批申请。"""
    if not request_id:
        return None
    row = query_db(
        """
        SELECT id, requester_id, requester_name, resource_type, resource_id,
               resource_label, export_format, filter_summary, status,
               approver_id, approver_name, approved_at, approval_remark,
               created_at, updated_at
        FROM export_approval_requests
        WHERE id=%s
        """,
        (int(request_id),),
        one=True,
    )
    if not row:
        return None
    item = dict(row)
    item["status_label"] = EXPORT_STATUS_LABELS.get(item.get("status"), item.get("status") or "")
    return item


def approve_export_request(
    execute_db,
    request_id: int,
    approver_id: int,
    approver_name: str = "",
    remark: str = "",
) -> bool:
    """批准导出申请。"""
    if not request_id or not approver_id:
        return False
    execute_db(
        """
        UPDATE export_approval_requests
        SET status='approved', approver_id=%s, approver_name=%s,
            approved_at=NOW(), approval_remark=%s, updated_at=NOW()
        WHERE id=%s AND status='pending'
        """,
        (int(approver_id), approver_name or "", remark or "", int(request_id)),
    )
    return True


def reject_export_request(
    execute_db,
    request_id: int,
    approver_id: int,
    approver_name: str = "",
    remark: str = "",
) -> bool:
    """拒绝导出申请。"""
    if not request_id or not approver_id:
        return False
    execute_db(
        """
        UPDATE export_approval_requests
        SET status='rejected', approver_id=%s, approver_name=%s,
            approved_at=NOW(), approval_remark=%s, updated_at=NOW()
        WHERE id=%s AND status='pending'
        """,
        (int(approver_id), approver_name or "", remark or "", int(request_id)),
    )
    return True


def cancel_export_request(
    execute_db,
    request_id: int,
    requester_id: int,
) -> bool:
    """申请人取消导出申请（仅限自己且 pending 状态）。"""
    if not request_id or not requester_id:
        return False
    execute_db(
        """
        UPDATE export_approval_requests
        SET status='cancelled', updated_at=NOW()
        WHERE id=%s AND requester_id=%s AND status='pending'
        """,
        (int(request_id), int(requester_id)),
    )
    return True
