from __future__ import annotations

from typing import Any, Dict, List, Optional


IMPACT_TYPE_SALES_ORDER = "sales_order"
IMPACT_TYPE_PURCHASE_ORDER = "purchase_order"
IMPACT_TYPE_WORK_ORDER = "work_order"
IMPACT_TYPE_SUBCONTRACT = "subcontract"
IMPACT_TYPE_INVENTORY = "inventory"
IMPACT_TYPE_DRAWING = "drawing"

IMPACT_TYPE_LABELS = {
    IMPACT_TYPE_SALES_ORDER: "销售订单",
    IMPACT_TYPE_PURCHASE_ORDER: "采购订单",
    IMPACT_TYPE_WORK_ORDER: "生产工单",
    IMPACT_TYPE_SUBCONTRACT: "委外订单",
    IMPACT_TYPE_INVENTORY: "库存",
    IMPACT_TYPE_DRAWING: "工程图纸",
}

IMPACT_LEVEL_HIGH = "high"
IMPACT_LEVEL_MEDIUM = "medium"
IMPACT_LEVEL_LOW = "low"

IMPACT_STATUS_PENDING = "pending"
IMPACT_STATUS_RESOLVED = "resolved"
IMPACT_STATUS_IGNORED = "ignored"

IMPACT_STATUS_LABELS = {
    IMPACT_STATUS_PENDING: "待处理",
    IMPACT_STATUS_RESOLVED: "已处理",
    IMPACT_STATUS_IGNORED: "已忽略",
}


def _as_dict(row) -> Dict[str, Any]:
    return dict(row or {})


def _to_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _load_ecn(query_db, ecn_id) -> Optional[Dict[str, Any]]:
    ecn_id = _to_int(ecn_id)
    if not ecn_id:
        return None
    row = query_db(
        """
        SELECT ec.*, src.bom_no AS source_bom_no, src.version AS source_bom_version,
               src.product_id AS source_product_id,
               tgt.bom_no AS target_bom_no, tgt.version AS target_bom_version
        FROM bom_engineering_changes ec
        LEFT JOIN boms src ON src.id=ec.source_bom_id
        LEFT JOIN boms tgt ON tgt.id=ec.target_bom_id
        WHERE ec.id=%s
        """,
        (ecn_id,),
        one=True,
    )
    if not row:
        return None
    return _as_dict(row)


def _collect_bom_product_ids(query_db, bom_id) -> List[int]:
    """Collect the parent product id and all child product ids of a BOM."""
    bom_id = _to_int(bom_id)
    if not bom_id:
        return []
    header = query_db("SELECT product_id FROM boms WHERE id=%s", (bom_id,), one=True)
    product_ids: List[int] = []
    if header and header.get("product_id"):
        product_ids.append(int(header["product_id"]))
    rows = query_db(
        "SELECT DISTINCT product_id FROM bom_items WHERE bom_id=%s AND product_id IS NOT NULL",
        (bom_id,),
    )
    for row in rows or []:
        pid = row.get("product_id")
        if pid is not None and int(pid) not in product_ids:
            product_ids.append(int(pid))
    return product_ids


def _affected_sales_orders(query_db, product_id, bom_id, project_code, serial_no) -> List[Dict[str, Any]]:
    where_parts: List[str] = []
    params: List[Any] = []
    if product_id:
        where_parts.append("soi.product_id=%s")
        params.append(int(product_id))
    if project_code:
        where_parts.append("COALESCE(so.project_code, '')=%s")
        params.append(project_code)
    if serial_no:
        where_parts.append("COALESCE(so.serial_no, '')=%s")
        params.append(serial_no)
    where_parts.append("COALESCE(so.status, '') NOT IN ('已作废','作废','void','cancelled')")
    where_sql = "WHERE " + " AND ".join(where_parts)
    rows = query_db(
        f"""
        SELECT DISTINCT so.id, so.order_no, so.project_code, so.serial_no,
               so.delivery_date, so.status,
               c.name AS customer_name,
               p.code AS product_code, p.name AS product_name
        FROM sales_orders so
        LEFT JOIN sales_order_items soi ON soi.order_id=so.id
        LEFT JOIN customers c ON c.id=so.customer_id
        LEFT JOIN products p ON p.id=soi.product_id
        {where_sql}
        ORDER BY so.id DESC
        LIMIT 100
        """,
        tuple(params),
    )
    return [_as_dict(row) for row in rows or []]


def _affected_purchase_orders(query_db, product_ids) -> List[Dict[str, Any]]:
    if not product_ids:
        return []
    rows = query_db(
        """
        SELECT DISTINCT po.id, po.order_no, po.project_code, po.serial_no, po.status,
                         s.name AS supplier_name,
                         p.code AS product_code, p.name AS product_name,
                         poi.quantity, poi.received_qty,
                         GREATEST(COALESCE(poi.quantity,0)-COALESCE(poi.received_qty,0),0) AS pending_qty
        FROM purchase_order_items poi
        LEFT JOIN purchase_orders po ON po.id=poi.order_id
        LEFT JOIN suppliers s ON s.id=po.supplier_id
        LEFT JOIN products p ON p.id=poi.product_id
        WHERE poi.product_id = ANY(%s)
          AND COALESCE(po.status, '') NOT IN ('已作废','作废','cancelled','已关闭')
        ORDER BY po.id DESC
        LIMIT 100
        """,
        (product_ids,),
    )
    return [_as_dict(row) for row in rows or []]


def _affected_work_orders(query_db, product_id, bom_id, project_code, serial_no) -> List[Dict[str, Any]]:
    where_parts: List[str] = []
    params: List[Any] = []
    if product_id:
        where_parts.append("(wo.product_id=%s OR wo.bom_id=%s)")
        params.extend([int(product_id), _to_int(bom_id) or -1])
    elif bom_id:
        where_parts.append("wo.bom_id=%s")
        params.append(int(bom_id))
    if project_code:
        where_parts.append("COALESCE(wo.project_code, '')=%s")
        params.append(project_code)
    if serial_no:
        where_parts.append("COALESCE(wo.serial_no, '')=%s")
        params.append(serial_no)
    where_parts.append("COALESCE(wo.status, '') NOT IN ('已完工','已完成','已关闭','已作废','closed','completed','cancelled','void')")
    where_sql = "WHERE " + " AND ".join(where_parts)
    rows = query_db(
        f"""
        SELECT wo.id, wo.wo_no, wo.project_code, wo.serial_no, wo.status,
               wo.quantity, wo.planned_end_date,
               p.code AS product_code, p.name AS product_name,
               b.bom_no, b.version AS bom_version
        FROM work_orders wo
        LEFT JOIN products p ON p.id=wo.product_id
        LEFT JOIN boms b ON b.id=wo.bom_id
        {where_sql}
        ORDER BY wo.id DESC
        LIMIT 100
        """,
        tuple(params),
    )
    return [_as_dict(row) for row in rows or []]


def _affected_subcontract_orders(query_db, product_ids, project_code, serial_no) -> List[Dict[str, Any]]:
    where_parts: List[str] = []
    params: List[Any] = []
    if product_ids:
        where_parts.append("soi.product_id = ANY(%s)")
        params.append(product_ids)
    if project_code:
        where_parts.append("COALESCE(so.project_code, '')=%s")
        params.append(project_code)
    if serial_no:
        where_parts.append("COALESCE(so.serial_no, '')=%s")
        params.append(serial_no)
    where_parts.append("COALESCE(so.status, '') NOT IN ('已作废','作废','cancelled','已关闭')")
    where_sql = "WHERE " + " AND ".join(where_parts)
    rows = query_db(
        f"""
        SELECT DISTINCT so.id, so.order_no, so.project_code, so.serial_no, so.status,
                         s.name AS supplier_name,
                         p.code AS product_code, p.name AS product_name
        FROM subcontract_items soi
        LEFT JOIN subcontract_orders so ON so.id=soi.order_id
        LEFT JOIN suppliers s ON s.id=so.supplier_id
        LEFT JOIN products p ON p.id=soi.product_id
        {where_sql}
        ORDER BY so.id DESC
        LIMIT 100
        """,
        tuple(params),
    )
    return [_as_dict(row) for row in rows or []]


def _affected_inventory(query_db, product_ids) -> List[Dict[str, Any]]:
    if not product_ids:
        return []
    rows = query_db(
        """
        SELECT ib.product_id, p.code AS product_code, p.name AS product_name,
               w.code AS warehouse_code, w.name AS warehouse_name,
               COALESCE(ib.quantity, 0) AS quantity
        FROM inventory_balances ib
        LEFT JOIN products p ON p.id=ib.product_id
        LEFT JOIN warehouses w ON w.id=ib.warehouse_id
        WHERE ib.product_id = ANY(%s)
          AND COALESCE(ib.quantity, 0) <> 0
        ORDER BY p.code, w.code
        LIMIT 100
        """,
        (product_ids,),
    )
    return [_as_dict(row) for row in rows or []]


def _affected_drawings(query_db, product_ids, bom_id, project_code, serial_no) -> List[Dict[str, Any]]:
    """B-4 enhancement: find engineering drawings linked to the affected product/BOM/project/serial.

    Matches via engineering_drawing_links on product_id, bom_id, project_code, or serial_no.
    Only released/approved drawings are returned (drafts are not yet in effect).
    """
    where_parts: List[str] = []
    params: List[Any] = []
    if product_ids:
        where_parts.append("dl.product_id = ANY(%s)")
        params.append(product_ids)
    bom_id_int = _to_int(bom_id)
    if bom_id_int:
        where_parts.append("dl.bom_id=%s")
        params.append(bom_id_int)
    project_code = _clean(project_code)
    if project_code:
        where_parts.append("COALESCE(dl.project_code,'')=%s")
        params.append(project_code)
    serial_no = _clean(serial_no)
    if serial_no:
        where_parts.append("COALESCE(dl.serial_no,'')=%s")
        params.append(serial_no)
    if not where_parts:
        return []
    # OR: a drawing link may be associated by any one of product/bom/project/serial
    where_sql = " OR ".join(where_parts)
    rows = query_db(
        f"""
        SELECT DISTINCT d.id, d.drawing_no, d.version, d.drawing_name,
               d.drawing_type, d.status, d.released_date, d.file_location,
               dl.product_id, dl.bom_id, dl.project_code, dl.serial_no,
               p.code AS product_code, p.name AS product_name
        FROM engineering_drawing_links dl
        LEFT JOIN engineering_drawings d ON d.id=dl.drawing_id
        LEFT JOIN products p ON p.id=dl.product_id
        WHERE ({where_sql})
          AND COALESCE(d.status, '') IN ('released','approved','发布','已发布','frozen')
        ORDER BY d.drawing_no, d.version
        LIMIT 100
        """,
        tuple(params),
    )
    return [_as_dict(row) for row in rows or []]


def _build_result(
    affected_type: str,
    rows: List[Dict[str, Any]],
    id_field: str,
    no_field: str,
    action_required: str,
    impact_level: str = IMPACT_LEVEL_MEDIUM,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for row in rows:
        results.append({
            "affected_type": affected_type,
            "affected_id": row.get(id_field),
            "affected_no": row.get(no_field),
            "impact_level": impact_level,
            "action_required": action_required,
            "status": IMPACT_STATUS_PENDING,
            "detail": row,
        })
    return results


def analyze_ecn_impact(
    query_db,
    ecn_id,
    product_id=None,
    bom_id=None,
    project_code=None,
    serial_no=None,
) -> List[Dict[str, Any]]:
    """Analyze what's affected by an ECN.

    Affected sales orders (matching product), purchase orders (matching BOM items),
    work orders (matching product/BOM), subcontract orders, and inventory.
    Returns list of impact results.
    """
    ecn = _load_ecn(query_db, ecn_id)
    if not ecn:
        return []
    resolved_bom_id = _to_int(bom_id) or _to_int(ecn.get("source_bom_id")) or _to_int(ecn.get("target_bom_id"))
    resolved_product_id = _to_int(product_id) or _to_int(ecn.get("source_product_id"))
    resolved_project_code = _clean(project_code) or _clean(ecn.get("project_code"))
    resolved_serial_no = _clean(serial_no)
    bom_product_ids = _collect_bom_product_ids(query_db, resolved_bom_id)
    if resolved_product_id and resolved_product_id not in bom_product_ids:
        bom_product_ids.insert(0, resolved_product_id)
    results: List[Dict[str, Any]] = []
    sales_rows = _affected_sales_orders(query_db, resolved_product_id, resolved_bom_id, resolved_project_code, resolved_serial_no)
    results.extend(_build_result(
        IMPACT_TYPE_SALES_ORDER, sales_rows, "id", "order_no",
        "评估是否需要通知客户、调整交期或换型", IMPACT_LEVEL_HIGH,
    ))
    purchase_rows = _affected_purchase_orders(query_db, bom_product_ids)
    results.extend(_build_result(
        IMPACT_TYPE_PURCHASE_ORDER, purchase_rows, "id", "order_no",
        "评估采购未到量是否需要变更、退换或转用", IMPACT_LEVEL_MEDIUM,
    ))
    work_order_rows = _affected_work_orders(query_db, resolved_product_id, resolved_bom_id, resolved_project_code, resolved_serial_no)
    results.extend(_build_result(
        IMPACT_TYPE_WORK_ORDER, work_order_rows, "id", "wo_no",
        "评估在制工单是否需要切版、补料或暂停", IMPACT_LEVEL_HIGH,
    ))
    subcontract_rows = _affected_subcontract_orders(query_db, bom_product_ids, resolved_project_code, resolved_serial_no)
    results.extend(_build_result(
        IMPACT_TYPE_SUBCONTRACT, subcontract_rows, "id", "order_no",
        "评估委外在制订单是否需要变更或回收", IMPACT_LEVEL_MEDIUM,
    ))
    inventory_rows = _affected_inventory(query_db, bom_product_ids)
    results.extend(_build_result(
        IMPACT_TYPE_INVENTORY, inventory_rows, "product_id", "product_code",
        "评估库存是否需要冻结、转用或报废", IMPACT_LEVEL_LOW,
    ))
    drawing_rows = _affected_drawings(query_db, bom_product_ids, resolved_bom_id, resolved_project_code, resolved_serial_no)
    results.extend(_build_result(
        IMPACT_TYPE_DRAWING, drawing_rows, "id", "drawing_no",
        "评估关联图纸是否需要升版、替换或废止", IMPACT_LEVEL_MEDIUM,
    ))
    return results


def save_impact_results(query_db, execute_db, ecn_id, results: List[Dict[str, Any]]) -> int:
    """Save impact results to ecn_impact_results. Replaces existing pending rows.

    DELETE and INSERTs run in a single transaction via CTE so they commit atomically.
    """
    ecn_id = _to_int(ecn_id)
    if not ecn_id:
        return 0
    # Build a single VALUES list for batch insert, then run DELETE + INSERT in one CTE.
    values_rows = []
    for item in results or []:
        values_rows.append(
            (
                ecn_id,
                item.get("affected_type"),
                _to_int(item.get("affected_id")),
                _clean(item.get("affected_no")),
                item.get("impact_level") or IMPACT_LEVEL_MEDIUM,
                _clean(item.get("action_required")) or "",
                item.get("status") or IMPACT_STATUS_PENDING,
            )
        )
    if values_rows:
        placeholders = ",".join(["(%s,%s,%s,%s,%s,%s,%s)"] * len(values_rows))
        flat_params = tuple(v for row in values_rows for v in row)
        execute_db(
            f"""
            WITH deleted AS (
                DELETE FROM ecn_impact_results WHERE ecn_id=%s AND status='pending'
                RETURNING id
            )
            INSERT INTO ecn_impact_results
                (ecn_id, affected_type, affected_id, affected_no,
                 impact_level, action_required, status)
            VALUES {placeholders}
            """,
            (ecn_id,) + flat_params,
        )
        return len(values_rows)
    # No new rows: just delete pending rows.
    execute_db(
        "DELETE FROM ecn_impact_results WHERE ecn_id=%s AND status='pending'",
        (ecn_id,),
    )
    return 0


def get_impact_results(query_db, ecn_id) -> List[Dict[str, Any]]:
    """Retrieve saved impact results for an ECN."""
    ecn_id = _to_int(ecn_id)
    if not ecn_id:
        return []
    rows = query_db(
        """
        SELECT ir.*, ec.ecn_no, ec.title AS ecn_title
        FROM ecn_impact_results ir
        LEFT JOIN bom_engineering_changes ec ON ec.id=ir.ecn_id
        WHERE ir.ecn_id=%s
        ORDER BY
            CASE ir.impact_level WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
            CASE ir.status WHEN 'pending' THEN 0 WHEN 'resolved' THEN 1 ELSE 2 END,
            ir.id DESC
        """,
        (ecn_id,),
    )
    result = []
    for row in rows or []:
        item = _as_dict(row)
        item["affected_type_label"] = IMPACT_TYPE_LABELS.get(item.get("affected_type"), item.get("affected_type") or "")
        item["status_label"] = IMPACT_STATUS_LABELS.get(item.get("status"), item.get("status") or "")
        result.append(item)
    return result


def get_pending_impact_tasks(query_db) -> List[Dict[str, Any]]:
    """Get all pending impact tasks across all ECNs."""
    rows = query_db(
        """
        SELECT ir.*, ec.ecn_no, ec.title AS ecn_title, ec.status AS ecn_status
        FROM ecn_impact_results ir
        LEFT JOIN bom_engineering_changes ec ON ec.id=ir.ecn_id
        WHERE ir.status='pending'
        ORDER BY
            CASE ir.impact_level WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
            ir.id DESC
        LIMIT 200
        """,
    )
    result = []
    for row in rows or []:
        item = _as_dict(row)
        item["affected_type_label"] = IMPACT_TYPE_LABELS.get(item.get("affected_type"), item.get("affected_type") or "")
        item["status_label"] = IMPACT_STATUS_LABELS.get(item.get("status"), item.get("status") or "")
        result.append(item)
    return result


def resolve_impact_task(execute_db, task_id, action_taken: Optional[str] = None) -> bool:
    """Mark an impact task as resolved."""
    task_id = _to_int(task_id)
    if not task_id:
        return False
    execute_db(
        """
        UPDATE ecn_impact_results
        SET status='resolved', action_required=COALESCE(%s, action_required)
        WHERE id=%s AND status='pending'
        """,
        (_clean(action_taken), task_id),
    )
    return True


# ===== ECN 变更执行控制 =====

ACTION_TASK_PURCHASE_CHANGE = "purchase_change"
ACTION_TASK_WORK_ORDER_CHANGE = "work_order_change"
ACTION_TASK_PICK_ADJUST = "pick_adjust"
ACTION_TASK_DRAWING_REPLACE = "drawing_replace"
ACTION_TASK_SERVICE_NOTICE = "service_notice"

ACTION_TASK_LABELS = {
    ACTION_TASK_PURCHASE_CHANGE: "采购变更",
    ACTION_TASK_WORK_ORDER_CHANGE: "工单变更",
    ACTION_TASK_PICK_ADJUST: "领料调整",
    ACTION_TASK_DRAWING_REPLACE: "图纸替换",
    ACTION_TASK_SERVICE_NOTICE: "售后通知",
}

ACTION_STATUS_PENDING = "pending"
ACTION_STATUS_IN_PROGRESS = "in_progress"
ACTION_STATUS_DONE = "done"
ACTION_STATUS_CANCELLED = "cancelled"

ACTION_STATUS_LABELS = {
    ACTION_STATUS_PENDING: "待处理",
    ACTION_STATUS_IN_PROGRESS: "处理中",
    ACTION_STATUS_DONE: "已完成",
    ACTION_STATUS_CANCELLED: "已取消",
}


def _impact_type_to_task_type(affected_type: str) -> Optional[str]:
    """Map impact result type to action task type."""
    mapping = {
        IMPACT_TYPE_PURCHASE_ORDER: ACTION_TASK_PURCHASE_CHANGE,
        IMPACT_TYPE_WORK_ORDER: ACTION_TASK_WORK_ORDER_CHANGE,
        IMPACT_TYPE_SUBCONTRACT: ACTION_TASK_PURCHASE_CHANGE,
        IMPACT_TYPE_INVENTORY: ACTION_TASK_PICK_ADJUST,
        IMPACT_TYPE_SALES_ORDER: ACTION_TASK_SERVICE_NOTICE,
        IMPACT_TYPE_DRAWING: ACTION_TASK_DRAWING_REPLACE,
    }
    return mapping.get(affected_type)


def generate_action_tasks(
    query_db, execute_db, ecn_id
) -> int:
    """根据 ECN 影响分析结果自动生成变更执行任务。

    对每条 pending 的影响结果，按受影响对象类型生成对应的执行任务：
    - 采购订单/委外订单 -> 采购变更
    - 生产工单 -> 工单变更 + 领料调整
    - 库存 -> 领料调整
    - 销售订单 -> 售后通知

    已存在的同类型 pending 任务不重复生成。
    """
    ecn_id = _to_int(ecn_id)
    if not ecn_id:
        return 0
    results = get_impact_results(query_db, ecn_id)
    created = 0
    for item in results:
        if item.get("status") != IMPACT_STATUS_PENDING:
            continue
        affected_type = item.get("affected_type")
        task_types = []
        primary = _impact_type_to_task_type(affected_type)
        if primary:
            task_types.append(primary)
        if affected_type == IMPACT_TYPE_WORK_ORDER:
            task_types.append(ACTION_TASK_PICK_ADJUST)
        if affected_type == IMPACT_TYPE_WORK_ORDER:
            task_types.append(ACTION_TASK_DRAWING_REPLACE)
        for task_type in task_types:
            existing = query_db(
                """
                SELECT id FROM ecn_action_tasks
                WHERE ecn_id=%s AND impact_result_id=%s
                  AND task_type=%s AND action_status='pending'
                """,
                (ecn_id, item.get("id"), task_type),
                one=True,
            )
            if existing:
                continue
            description = _build_task_description(task_type, item)
            execute_db(
                """
                INSERT INTO ecn_action_tasks
                    (ecn_id, impact_result_id, task_type,
                     affected_doc_type, affected_doc_id, affected_doc_no,
                     action_description, action_status, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
                """,
                (
                    ecn_id,
                    item.get("id"),
                    task_type,
                    affected_type,
                    item.get("affected_id"),
                    item.get("affected_no"),
                    description,
                    ACTION_STATUS_PENDING,
                ),
            )
            created += 1
    return created


def _build_task_description(task_type: str, impact_item: Dict[str, Any]) -> str:
    """Build human-readable action description."""
    doc_no = impact_item.get("affected_no") or ""
    labels = ACTION_TASK_LABELS
    label = labels.get(task_type, task_type)
    if task_type == ACTION_TASK_PURCHASE_CHANGE:
        return f"检查并调整采购/委外单据 {doc_no}：确认是否需要变更数量、物料或取消。"
    if task_type == ACTION_TASK_WORK_ORDER_CHANGE:
        return f"检查生产工单 {doc_no}：确认是否需要更新BOM版本、工艺路线或调整数量。"
    if task_type == ACTION_TASK_PICK_ADJUST:
        return f"检查工单 {doc_no} 的领料情况：确认是否需要退料、补料或调整替代料。"
    if task_type == ACTION_TASK_DRAWING_REPLACE:
        if impact_item.get("affected_type") == IMPACT_TYPE_DRAWING:
            drawing_name = impact_item.get("detail", {}).get("drawing_name") or ""
            return f"检查工程图纸 {doc_no} {drawing_name}：确认是否需要升版、替换或废止关联版本。"
        return f"检查工单 {doc_no} 的图纸版本：确认是否需要替换为新版本图纸。"
    if task_type == ACTION_TASK_SERVICE_NOTICE:
        return f"通知售后部门关注销售订单 {doc_no} 对应设备的工程变更影响。"
    return f"{label}：{doc_no}"


def list_action_tasks(
    query_db, ecn_id=None, status=None
) -> List[Dict[str, Any]]:
    """列出 ECN 执行任务，可按 ECN 和状态筛选。"""
    where_parts = []
    params = []
    if ecn_id:
        where_parts.append("t.ecn_id=%s")
        params.append(ecn_id)
    if status:
        where_parts.append("t.action_status=%s")
        params.append(status)
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    rows = query_db(
        f"""
        SELECT t.*, ec.ecn_no, ec.title AS ecn_title,
               assignee.username AS assigned_to_name,
               resolver.username AS resolved_by_name
        FROM ecn_action_tasks t
        LEFT JOIN bom_engineering_changes ec ON ec.id=t.ecn_id
        LEFT JOIN users assignee ON assignee.id=t.assigned_to
        LEFT JOIN users resolver ON resolver.id=t.resolved_by
        {where_sql}
        ORDER BY
            CASE t.action_status WHEN 'pending' THEN 0 WHEN 'in_progress' THEN 1 ELSE 2 END,
            t.id DESC
        """,
        tuple(params),
    ) or []
    result = []
    for row in rows:
        item = _as_dict(row)
        item["task_type_label"] = ACTION_TASK_LABELS.get(item.get("task_type"), item.get("task_type") or "")
        item["action_status_label"] = ACTION_STATUS_LABELS.get(item.get("action_status"), item.get("action_status") or "")
        result.append(item)
    return result


def get_action_task(query_db, task_id) -> Optional[Dict[str, Any]]:
    """获取单条执行任务。"""
    task_id = _to_int(task_id)
    if not task_id:
        return None
    row = query_db(
        """
        SELECT t.*, ec.ecn_no, ec.title AS ecn_title
        FROM ecn_action_tasks t
        LEFT JOIN bom_engineering_changes ec ON ec.id=t.ecn_id
        WHERE t.id=%s
        """,
        (task_id,),
        one=True,
    )
    if not row:
        return None
    item = _as_dict(row)
    item["task_type_label"] = ACTION_TASK_LABELS.get(item.get("task_type"), item.get("task_type") or "")
    item["action_status_label"] = ACTION_STATUS_LABELS.get(item.get("action_status"), item.get("action_status") or "")
    return item


def update_action_task_status(
    execute_db, task_id, status: str, resolved_by=None, remark: Optional[str] = None
) -> bool:
    """更新执行任务状态。"""
    task_id = _to_int(task_id)
    if not task_id:
        return False
    if status in (ACTION_STATUS_DONE, ACTION_STATUS_CANCELLED):
        execute_db(
            """
            UPDATE ecn_action_tasks
            SET action_status=%s, resolved_by=%s, resolved_at=CURRENT_TIMESTAMP,
                resolution_remark=COALESCE(%s, resolution_remark), updated_at=CURRENT_TIMESTAMP
            WHERE id=%s
            """,
            (status, resolved_by, _clean(remark), task_id),
        )
    else:
        execute_db(
            """
            UPDATE ecn_action_tasks
            SET action_status=%s, updated_at=CURRENT_TIMESTAMP
            WHERE id=%s
            """,
            (status, task_id),
        )
    return True


def assign_action_task(execute_db, task_id, assigned_to) -> bool:
    """指派执行任务。"""
    task_id = _to_int(task_id)
    if not task_id:
        return False
    execute_db(
        """
        UPDATE ecn_action_tasks
        SET assigned_to=%s, updated_at=CURRENT_TIMESTAMP
        WHERE id=%s
        """,
        (assigned_to, task_id),
    )
    return True
