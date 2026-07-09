"""Production completion routes: completion report, inbound, and scrap registration."""
from datetime import datetime
from decimal import Decimal

from flask import flash, g, redirect, render_template, request, session

from services.work_order_cost_service import sync_work_order_costs
from services.trace_engine import create_trace_link
from services.cost_engine import run_cost_calculation as _p0_run_cost_calculation

import logging

logger = logging.getLogger(__name__)


def _location_enabled():
    """Check if location management is enabled via system options."""
    try:
        from flask import current_app

        query_db = current_app.config.get("_query_db")
        if query_db:
            row = query_db(
                "SELECT option_value FROM system_options WHERE option_key IN ('cost_warehouse_location_required','warehouse_location_required') ORDER BY option_key LIMIT 1",
                one=True,
            ) or {}
            val = row.get("option_value", "1")
            return str(val).strip().lower() in {"1", "true", "yes", "on"}
    except Exception:
        pass
    return True


DOC_STATUS_DRAFT = "草稿"
DOC_STATUS_SUBMITTED = "已提交"
DOC_STATUS_POSTED = "已过账"
DOC_STATUS_REVERSED = "已反过账"
DOC_STATUS_VOIDED = "已作废"

FINAL_WORK_ORDER_STATUSES = {
    "已关闭",
    "已完工",
    "已完成",
    "已作废",
    "已取消",
    "closed",
    "completed",
    "void",
    "cancelled",
    "canceled",
}


def register_production_completion_routes(app, deps):
    login_required = deps["login_required"]
    safe_rows = deps["safe_rows"]
    safe_one = deps["safe_one"]
    execute_db = deps["execute_db"]
    execute_and_return = deps["execute_and_return"]
    next_doc_no = deps["next_doc_no"]
    as_decimal = deps["as_decimal"]
    as_int = deps["as_int"]
    form_text = deps["form_text"]
    form_int = deps["form_int"]
    form_decimal = deps["form_decimal"]
    has_column = deps["has_column"]
    apply_inventory_movement = deps["apply_inventory_movement"]
    build_completion_gate = deps["build_completion_gate"]
    log_action = deps["log_action"]
    run_in_transaction = deps.get("run_in_transaction") or (lambda operation: operation(None))

    def transaction_callables(cursor):
        if cursor is None:
            return safe_one, safe_rows, execute_db, execute_and_return

        def query_one(sql, params=None):
            cursor.execute(sql, params or ())
            return cursor.fetchone()

        def query_rows(sql, params=None):
            cursor.execute(sql, params or ())
            return cursor.fetchall()

        def tx_execute_db(sql, params=None):
            cursor.execute(sql, params or ())

        def tx_execute_and_return(sql, params=None):
            cursor.execute(sql, params or ())
            return cursor.fetchone()

        return query_one, query_rows, tx_execute_db, tx_execute_and_return

    def ensure_schema():
        # DDL 已迁移至 services/schema_migrations.py（20260619_005_production_completion_schema）
        # 请求期不再执行 CREATE TABLE / ALTER TABLE / CREATE INDEX
        pass

    def status_label(value):
        return {
            "draft": DOC_STATUS_DRAFT,
            "submitted": DOC_STATUS_SUBMITTED,
            "posted": DOC_STATUS_POSTED,
            "reversed": DOC_STATUS_REVERSED,
            "voided": DOC_STATUS_VOIDED,
            DOC_STATUS_DRAFT: DOC_STATUS_DRAFT,
            DOC_STATUS_SUBMITTED: DOC_STATUS_SUBMITTED,
            DOC_STATUS_POSTED: DOC_STATUS_POSTED,
            DOC_STATUS_REVERSED: DOC_STATUS_REVERSED,
            DOC_STATUS_VOIDED: DOC_STATUS_VOIDED,
        }.get(value or DOC_STATUS_DRAFT, value or DOC_STATUS_DRAFT)

    def next_action_for_status(value):
        label = status_label(value)
        if label == DOC_STATUS_DRAFT:
            return "提交或作废"
        if label == DOC_STATUS_SUBMITTED:
            return "过账或作废"
        if label == DOC_STATUS_POSTED:
            return "核对库存流水、工单完工和成本；必要时反过账"
        if label == DOC_STATUS_REVERSED:
            return "只读；核对红冲流水和工单完成数量"
        return "只读"

    def can_edit_completion_doc(doc):
        if not doc:
            return False
        if doc.get("posted_at") or doc.get("wo_complete_item_id") or doc.get("reverse_posted_at") or doc.get("voided_at"):
            return False
        return status_label(doc.get("status")) == DOC_STATUS_DRAFT

    def set_completion_form_toolbar(order=None, can_complete=True):
        actions = []
        if order and order.get("id"):
            actions.append({"label": "返回工单", "type": "link", "href": f"/work-orders/{order.get('id')}", "icon": "bi-arrow-left"})
        g.toolbar_extras = actions

    def unified_completion_query(work_order_id=None, include_legacy=True, keyword="", status=""):
        ensure_schema()
        params = []
        conditions = []
        if work_order_id:
            conditions.append("pc.work_order_id=%s")
            params.append(work_order_id)
        keyword = (keyword or "").strip()
        status = (status or "").strip()
        if keyword:
            conditions.append(
                "(pc.completion_no ILIKE %s OR wo.wo_no ILIKE %s OR pc.project_code ILIKE %s OR pc.serial_no ILIKE %s OR p.name ILIKE %s)"
            )
            params.extend([f"%{keyword}%"] * 5)
        if status:
            conditions.append("pc.status=%s")
            params.append(status)
        formal_where = "WHERE " + " AND ".join(conditions) if conditions else ""
        rows = safe_rows(
            f"""
            SELECT pc.id, 'new' AS source, pc.completion_no AS doc_no, pc.completion_no,
                   pc.work_order_id, pc.work_order_id AS wo_id, wo.wo_no, pc.quantity AS qty,
                   pc.quantity, pc.completion_date, pc.completion_date AS complete_date,
                   pc.product_id, p.code AS product_code, p.name AS product_name,
                   pc.unit_cost, pc.warehouse_id, w.name AS warehouse_name,
                   pc.location_id, pc.lot_no, pc.serial_no, pc.project_code, pc.status,
                   pc.wo_complete_item_id, pc.posted_at, pc.reverse_posted_at
            FROM production_completion_orders pc
            LEFT JOIN work_orders wo ON wo.id=pc.work_order_id
            LEFT JOIN products p ON p.id=pc.product_id
            LEFT JOIN warehouses w ON w.id=pc.warehouse_id
            {formal_where}
            ORDER BY pc.completion_date DESC NULLS LAST, pc.id DESC
            LIMIT 500
            """,
            tuple(params),
        )
        if not include_legacy:
            return rows

        legacy_params = []
        legacy_conditions = [
            "NOT EXISTS (SELECT 1 FROM production_completion_orders pc WHERE pc.wo_complete_item_id=wc.id)"
        ]
        if work_order_id:
            legacy_conditions.append("wc.wo_id=%s")
            legacy_params.append(work_order_id)
        if keyword:
            legacy_conditions.append(
                "(COALESCE(wc.source_doc_no, 'LEGACY-WC-' || wc.id::text) ILIKE %s OR wo.wo_no ILIKE %s OR wo.project_code ILIKE %s OR wc.serial_no ILIKE %s OR p.name ILIKE %s)"
            )
            legacy_params.extend([f"%{keyword}%"] * 5)
        if status:
            legacy_conditions.append("%s IN ('历史完工', 'legacy')")
            legacy_params.append(status)
        legacy_where = "WHERE " + " AND ".join(legacy_conditions)
        legacy_rows = safe_rows(
            f"""
            SELECT wc.id, 'legacy' AS source,
                   COALESCE(wc.source_doc_no, 'LEGACY-WC-' || wc.id::text) AS doc_no,
                   COALESCE(wc.source_doc_no, 'LEGACY-WC-' || wc.id::text) AS completion_no,
                   wc.wo_id, wc.wo_id AS work_order_id, wo.wo_no, wc.qty, wc.qty AS quantity,
                   wc.complete_date, wc.complete_date AS completion_date, wc.product_id,
                   p.code AS product_code, p.name AS product_name, wc.unit_cost,
                   wc.warehouse_id, w.name AS warehouse_name, wc.location_id,
                   wc.lot_no, wc.serial_no, wo.project_code, '历史完工' AS status,
                   wc.id AS wo_complete_item_id, NULL AS posted_at, wc.reverse_posted_at
            FROM wo_complete_items wc
            LEFT JOIN work_orders wo ON wo.id=wc.wo_id
            LEFT JOIN products p ON p.id=wc.product_id
            LEFT JOIN warehouses w ON w.id=wc.warehouse_id
            {legacy_where}
            ORDER BY wc.complete_date DESC NULLS LAST, wc.id DESC
            LIMIT 500
            """,
            tuple(legacy_params),
        )
        return rows + legacy_rows

    def completion_summary_for_order(work_order_id):
        rows = unified_completion_query(work_order_id=work_order_id, include_legacy=True)
        formal_qty = Decimal("0")
        legacy_qty = Decimal("0")
        reversed_qty = Decimal("0")
        for row in rows:
            qty = as_decimal(row.get("qty") or row.get("quantity"))
            if row.get("source") == "legacy":
                legacy_qty += qty
            elif status_label(row.get("status")) == DOC_STATUS_REVERSED:
                reversed_qty += qty
            elif status_label(row.get("status")) == DOC_STATUS_POSTED:
                formal_qty += qty
        formal_refs = [row.get("doc_no") for row in rows if row.get("source") == "new" and row.get("doc_no")]
        stock_qty = Decimal("0")
        if formal_refs:
            if has_column("stock_transactions", "source_doc_no"):
                stock = safe_one(
                    """
                    SELECT COALESCE(SUM(quantity),0) AS qty
                    FROM stock_transactions
                    WHERE reference_no = ANY(%s)
                       OR source_doc_no = ANY(%s)
                    """,
                    (formal_refs, formal_refs),
                ) or {}
            else:
                stock = safe_one(
                    """
                    SELECT COALESCE(SUM(quantity),0) AS qty
                    FROM stock_transactions
                    WHERE reference_no = ANY(%s)
                    """,
                    (formal_refs,),
                ) or {}
            stock_qty = as_decimal(stock.get("qty"))
        return {
            "formal_qty": formal_qty,
            "legacy_qty": legacy_qty,
            "reversed_qty": reversed_qty,
            "total_qty": formal_qty + legacy_qty,
            "stock_qty": stock_qty,
            "row_count": len(rows),
        }

    def work_order(work_order_id):
        return safe_one(
            """
            SELECT wo.*, p.code AS product_code, p.name AS product_name,
                   p.specification, p.unit AS product_unit, p.standard_price
            FROM work_orders wo
            LEFT JOIN products p ON p.id=wo.product_id
            WHERE wo.id=%s
            """,
            (work_order_id,),
        )

    def candidate_orders():
        ensure_schema()
        return safe_rows(
            """
            SELECT wo.id, wo.wo_no, wo.wo_date, wo.project_code, wo.serial_no, wo.status,
                   wo.quantity, wo.warehouse_id, wo.location_id,
                   p.code AS product_code, p.name AS product_name, p.specification, p.unit AS product_unit,
                   COALESCE(done.completed_qty, 0) AS completed_qty,
                   GREATEST(COALESCE(wo.quantity,0)-COALESCE(done.completed_qty,0),0) AS remaining_qty
            FROM work_orders wo
            LEFT JOIN products p ON p.id=wo.product_id
            LEFT JOIN LATERAL (
                SELECT COALESCE(SUM(qty), 0) AS completed_qty
                FROM wo_complete_items wc
                WHERE wc.wo_id=wo.id
            ) done ON TRUE
            WHERE COALESCE(wo.status,'') NOT IN ('已关闭','已完工','已完成','已作废','已取消','closed','completed','void','cancelled','canceled')
              AND wo.product_id IS NOT NULL
            ORDER BY wo.id DESC
            LIMIT 200
            """
        )

    def load_gate(order, candidate=None):
        material_items = safe_rows(
            """
            SELECT mi.*, p.code AS product_code,
                   GREATEST(COALESCE(mi.required_qty,0)-COALESCE(mi.issued_qty,0)+COALESCE(mi.returned_qty,0),0) AS shortage_qty
            FROM wo_material_items mi
            LEFT JOIN products p ON p.id=mi.product_id
            WHERE mi.wo_id=%s
            ORDER BY mi.id
            """,
            (order.get("id"),),
        )
        quality_rows = safe_rows(
            """
            SELECT id, inspection_result, status, inspection_type
            FROM quality_inspection_records
            WHERE (source_document_type='work_order' AND source_document_id=%s)
               OR (%s IS NOT NULL AND project_code=%s)
               OR (%s IS NOT NULL AND serial_no=%s)
            ORDER BY id DESC
            LIMIT 30
            """,
            (order.get("id"), order.get("project_code"), order.get("project_code"), order.get("serial_no"), order.get("serial_no")),
        )
        processes = safe_rows(
            """
            SELECT id, status, planned_quantity, actual_quantity, good_quantity, qc_status
            FROM work_order_processes
            WHERE work_order_id=%s
            ORDER BY id
            """,
            (order.get("id"),),
        )
        mrp_rows = safe_rows(
            """
            SELECT shortage_quantity
            FROM mrp_requirements
            WHERE work_order_id=%s
               OR (%s IS NOT NULL AND project_code=%s)
               OR (%s IS NOT NULL AND serial_no=%s)
            LIMIT 100
            """,
            (order.get("id"), order.get("project_code"), order.get("project_code"), order.get("serial_no"), order.get("serial_no")),
        )
        completion_rows = safe_rows(
            "SELECT complete_date, qty, lot_no, serial_no, warehouse_id, location_id FROM wo_complete_items WHERE wo_id=%s",
            (order.get("id"),),
        )
        stock_rows = safe_rows("SELECT transaction_type FROM stock_transactions WHERE reference_no=%s", (order.get("wo_no"),))
        return build_completion_gate(order, material_items, quality_rows, processes, mrp_rows, completion_rows, stock_rows, candidate)

    def completion_doc(doc_id):
        ensure_schema()
        return safe_one(
            """
            SELECT pc.*, wo.wo_no, wo.status AS work_order_status,
                   p.code AS product_code, p.name AS product_name, p.specification, p.unit AS product_unit,
                   w.name AS warehouse_name, l.code AS location_code, COALESCE(l.name, l.code) AS location_name
            FROM production_completion_orders pc
            LEFT JOIN work_orders wo ON wo.id=pc.work_order_id
            LEFT JOIN products p ON p.id=pc.product_id
            LEFT JOIN warehouses w ON w.id=pc.warehouse_id
            LEFT JOIN locations l ON l.id=pc.location_id
            WHERE pc.id=%s
            """,
            (doc_id,),
        )

    def copy_completion_doc(doc_id):
        doc = completion_doc(doc_id)
        if not doc:
            flash("完工入库单不存在，不能复制。", "warning")
            return redirect("/production-completions")
        doc_no = next_doc_no("PC", "production_completion_orders", "completion_no")
        copied = execute_and_return(
            """
            INSERT INTO production_completion_orders
                (completion_no, completion_date, work_order_id, product_id, quantity, failed_quantity,
                 unit_cost, warehouse_id, location_id, lot_no, serial_no, project_code, status, remark, created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id, completion_no
            """,
            (
                doc_no,
                datetime.now().date().isoformat(),
                doc.get("work_order_id"),
                doc.get("product_id"),
                doc.get("quantity"),
                doc.get("failed_quantity") or 0,
                doc.get("unit_cost") or 0,
                doc.get("warehouse_id"),
                doc.get("location_id"),
                doc.get("lot_no"),
                doc.get("serial_no"),
                doc.get("project_code"),
                DOC_STATUS_DRAFT,
                doc.get("remark"),
                session.get("user_id") or doc.get("created_by"),
            ),
        )
        log_action("复制完工入库单", f"{doc.get('completion_no')} -> {doc_no}")
        flash(f"已复制为新草稿单据 {doc_no}，请检查后提交/审核。", "success")
        return redirect(f"/production-completions/{copied.get('id')}")

    def update_completion_doc(doc_id):
        doc = completion_doc(doc_id)
        if not doc:
            flash("完工入库单不存在。", "warning")
            return redirect("/production-completions")
        if not can_edit_completion_doc(doc):
            flash("当前完工入库单不允许编辑；已提交、已过账、已反过账或已作废单据为只读。", "warning")
            return redirect(f"/production-completions/{doc_id}")
        action = form_text("save_action")
        if action == "unaudit":
            flash("反审请在已过账完工入库单详情页执行。", "warning")
            return redirect(f"/production-completions/{doc_id}")
        order = work_order(doc.get("work_order_id"))
        if not order:
            flash("来源工单不存在，不能保存。", "warning")
            return redirect(f"/production-completions/{doc_id}")
        if (order.get("status") or "") in FINAL_WORK_ORDER_STATUSES:
            flash("来源工单已关闭、已完工或已作废，不能继续编辑。", "warning")
            return redirect(f"/production-completions/{doc_id}")
        quantity = form_decimal("quantity")
        if quantity <= 0:
            flash("完工数量必须大于 0。", "warning")
            return redirect(f"/production-completions/{doc_id}/edit")
        completion_date = form_text("completion_date", datetime.now().date().isoformat())
        warehouse_id = form_int("warehouse_id") or order.get("warehouse_id")
        location_id = form_int("location_id") or order.get("location_id")
        if not _location_enabled():
            location_id = None
        serial_no = form_text("serial_no") or order.get("serial_no")
        candidate = {
            "quantity": quantity,
            "complete_date": completion_date,
            "warehouse_id": warehouse_id,
            "location_id": location_id,
            "lot_no": form_text("lot_no"),
            "serial_no": serial_no,
        }
        gate = load_gate(order, candidate)
        if not gate.get("can_complete"):
            flash("完工入库被阻断：" + "；".join(gate.get("blockers") or []), "warning")
            return redirect(f"/production-completions/{doc_id}/edit")
        unit_cost = resolve_unit_cost(order, form_decimal("unit_cost"))
        execute_db(
            """
            UPDATE production_completion_orders
            SET completion_date=%s, quantity=%s, failed_quantity=%s, unit_cost=%s,
                warehouse_id=%s, location_id=%s, lot_no=%s, serial_no=%s,
                project_code=%s, remark=%s, updated_at=NOW()
            WHERE id=%s
            """,
            (
                completion_date,
                quantity,
                form_decimal("failed_quantity"),
                unit_cost,
                warehouse_id,
                location_id,
                form_text("lot_no"),
                serial_no,
                order.get("project_code"),
                form_text("remark"),
                doc_id,
            ),
        )
        log_action("编辑完工入库单", doc.get("completion_no"), f"id={doc_id}")
        if action == "audit":
            execute_db(
                "UPDATE production_completion_orders SET status=%s, submitted_by=%s, submitted_at=NOW(), updated_at=NOW() WHERE id=%s",
                (DOC_STATUS_SUBMITTED, session.get("user_id"), doc_id),
            )
            return post_document(doc_id)
        flash(f"完工入库单 {doc.get('completion_no')} 已保存修改。", "success")
        return redirect(f"/production-completions/{doc_id}")

    @app.post("/production-completions/<int:doc_id>/copy", endpoint="production_completion_copy")
    @login_required
    def production_completion_copy(doc_id):
        return copy_completion_doc(doc_id)

    def resolve_unit_cost(order, entered_cost):
        unit_cost = as_decimal(entered_cost)
        if unit_cost != 0:
            return unit_cost
        cost = safe_one("SELECT total_cost FROM work_order_costs WHERE work_order_id=%s ORDER BY id DESC LIMIT 1", (order.get("id"),)) or {}
        order_qty = as_decimal(order.get("quantity"))
        if order_qty > 0 and as_decimal(cost.get("total_cost")) > 0:
            return as_decimal(cost.get("total_cost")) / order_qty
        return as_decimal(order.get("standard_price"))

    def recompute_work_order_status(order, query_one=None, execute_db_fn=None):
        # recompute_work_order_status(order) recomputes work order status after completion or reverse posting
        query_one = query_one or safe_one
        execute_db_fn = execute_db_fn or execute_db
        completed = query_one("SELECT COALESCE(SUM(qty),0) AS qty FROM wo_complete_items WHERE wo_id=%s", (order.get("id"),)) or {}
        completed_qty = as_decimal(completed.get("qty"))
        target_qty = as_decimal(order.get("quantity"))
        next_status = "已完工" if target_qty > 0 and completed_qty >= target_qty else "部分完工"
        fields = [
            "status=%s",
            "actual_end_date=CASE WHEN %s='已完工' THEN CURRENT_DATE ELSE actual_end_date END",
        ]
        params = [next_status, next_status]
        for column in ("completed_qty", "complete_qty", "finished_qty"):
            if has_column("work_orders", column):
                fields.append(f"{column}=%s")
                params.append(completed_qty)
        if has_column("work_orders", "blocked_reason"):
            fields.append("blocked_reason=%s")
            params.append("")
        if has_column("work_orders", "owner_role"):
            fields.append("owner_role=%s")
            params.append("仓库" if next_status == "已完工" else "生产")
        if has_column("work_orders", "production_stage"):
            fields.append("production_stage=%s")
            params.append("入库" if next_status == "已完工" else "调试")
        if has_column("work_orders", "updated_at"):
            fields.append("updated_at=NOW()")
        params.append(order.get("id"))
        execute_db_fn(f"UPDATE work_orders SET {', '.join(fields)} WHERE id=%s", tuple(params))
        return next_status, completed_qty

    def annotate_latest_stock_transaction(doc, complete_item, qty, execute_db_fn=None):
        execute_db_fn = execute_db_fn or execute_db
        set_fields = []
        params = []
        optional_values = {
            "source_doc_type": "production_completion",
            "source_doc_no": doc.get("completion_no"),
            "source_line_no": str(complete_item.get("id")),
            "source_line": str(complete_item.get("id")),
            "usage_reason": doc.get("remark") or "完工入库单过账",
            "amount": qty * as_decimal(doc.get("unit_cost")),
        }
        for column, value in optional_values.items():
            if has_column("stock_transactions", column):
                set_fields.append(f"{column}=%s")
                params.append(value)
        if not set_fields:
            return
        params.append(doc.get("completion_no"))
        execute_db_fn(
            f"""
            UPDATE stock_transactions
            SET {', '.join(set_fields)}
            WHERE id=(SELECT id FROM stock_transactions WHERE reference_no=%s ORDER BY id DESC LIMIT 1)
            """,
            tuple(params),
        )

    def post_document(doc_id):
        doc = completion_doc(doc_id)
        if not doc:
            flash("完工入库单不存在。", "warning")
            return redirect("/production-completions")
        if status_label(doc.get("status")) != DOC_STATUS_SUBMITTED:
            flash("完工入库单必须先提交后才能过账。", "warning")
            return redirect(f"/production-completions/{doc_id}")
        if doc.get("wo_complete_item_id") or doc.get("posted_at"):
            flash("完工入库单已过账，不能重复过账。", "warning")
            return redirect(f"/production-completions/{doc_id}")
        order = work_order(doc.get("work_order_id"))
        if not order:
            flash("来源工单不存在，不能过账。", "warning")
            return redirect(f"/production-completions/{doc_id}")
        if (order.get("status") or "") in FINAL_WORK_ORDER_STATUSES:
            flash("来源工单已关闭、已完工或已作废，不能过账。", "warning")
            return redirect(f"/production-completions/{doc_id}")
        qty = as_decimal(doc.get("quantity"))
        if qty <= 0:
            flash("完工数量必须大于 0。", "warning")
            return redirect(f"/production-completions/{doc_id}")
        candidate = {
            "quantity": qty,
            "complete_date": doc.get("completion_date"),
            "warehouse_id": doc.get("warehouse_id"),
            "location_id": doc.get("location_id"),
            "lot_no": doc.get("lot_no") or "",
            "serial_no": doc.get("serial_no") or order.get("serial_no"),
        }
        gate = load_gate(order, candidate)
        if not gate.get("can_complete"):
            flash("完工入库被阻断：" + "；".join(gate.get("blockers") or []), "warning")
            return redirect(f"/production-completions/{doc_id}")
        def operation(cursor):
            query_one, query_rows, tx_execute_db, tx_execute_and_return = transaction_callables(cursor)
            doc = query_one("SELECT * FROM production_completion_orders WHERE id=%s FOR UPDATE", (doc_id,))
            if not doc:
                raise ValueError("Document not found.")
            if status_label(doc.get("status")) != DOC_STATUS_SUBMITTED:
                raise ValueError("Document must be submitted before posting.")
            if doc.get("wo_complete_item_id") or doc.get("posted_at"):
                raise ValueError("Document already posted.")
            order = query_one(
                """
                SELECT wo.*, p.code AS product_code, p.name AS product_name,
                       p.specification, p.unit AS product_unit, p.standard_price
                FROM work_orders wo
                LEFT JOIN products p ON p.id=wo.product_id
                WHERE wo.id=%s
                FOR UPDATE OF wo
                """,
                (doc.get("work_order_id"),),
            )
            if not order:
                raise ValueError("Source work order not found.")
            if (order.get("status") or "") in FINAL_WORK_ORDER_STATUSES:
                raise ValueError("Source work order is closed.")
            qty = as_decimal(doc.get("quantity"))
            if qty <= 0:
                raise ValueError("Completion quantity must be greater than zero.")
            complete_item = tx_execute_and_return(
                """
                INSERT INTO wo_complete_items
                    (wo_id, complete_date, qty, lot_no, unit_cost, product_id, serial_no,
                     warehouse_id, location_id, source_doc_type, source_doc_no, reverse_posted)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,FALSE)
                RETURNING id
                """,
                (
                    order.get("id"),
                    doc.get("completion_date"),
                    qty,
                    doc.get("lot_no") or "",
                    doc.get("unit_cost") or 0,
                    doc.get("product_id"),
                    doc.get("serial_no") or order.get("serial_no"),
                    doc.get("warehouse_id"),
                    doc.get("location_id"),
                    "production_completion",
                    doc.get("completion_no"),
                ),
            )
            apply_inventory_movement(
                product_id=doc.get("product_id"),
                quantity=qty,
                unit_cost=doc.get("unit_cost") or 0,
                tx_type="\u5de5\u5355\u5b8c\u5de5\u5165\u5e93",
                reference_no=doc.get("completion_no"),
                remark=doc.get("remark") or "\u5b8c\u5de5\u5165\u5e93\u5355\u8fc7\u8d26",
                warehouse_id=doc.get("warehouse_id"),
                location_id=doc.get("location_id"),
                lot_no=doc.get("lot_no") or "",
                serial_no=doc.get("serial_no") or order.get("serial_no"),
                tx_date=doc.get("completion_date"),
                project_code=doc.get("project_code") or "",
                query_one=query_one,
                execute_db_fn=tx_execute_db,
            )
            annotate_latest_stock_transaction(doc, complete_item, qty, execute_db_fn=tx_execute_db)
            # Link the production completion to the inventory movement for traceability.
            st_row = query_one(
                "SELECT id FROM stock_transactions WHERE reference_no=%s ORDER BY id DESC LIMIT 1",
                (doc.get("completion_no"),),
            ) or {}
            st_id = st_row.get("id")
            if st_id:
                try:
                    create_trace_link(
                        query_one,
                        tx_execute_db,
                        source_doc_type="production_completion",
                        source_doc_id=doc_id,
                        source_doc_no=doc.get("completion_no"),
                        source_line_id=complete_item.get("id"),
                        target_doc_type="stock_transaction",
                        target_doc_id=st_id,
                        link_type="posts_to",
                        link_strength="soft",
                        project_code=doc.get("project_code") or order.get("project_code"),
                        serial_no=doc.get("serial_no") or order.get("serial_no"),
                        created_by=session.get("user_id"),
                        created_event="production_completion_inventory",
                    )
                except Exception:
                    logger.warning("Failed to post inventory in production completion", exc_info=True)
            next_status, completed_qty = recompute_work_order_status(order, query_one=query_one, execute_db_fn=tx_execute_db)
            sync_work_order_costs(
                query_one,
                query_rows,
                tx_execute_db,
                order.get("id"),
                source_type="\u5b8c\u5de5\u5165\u5e93",
                source_no=doc.get("completion_no"),
                remark=doc.get("remark") or "\u5b8c\u5de5\u5165\u5e93\u5355\u8fc7\u8d26",
            )
            tx_execute_db(
                """
                UPDATE production_completion_orders
                SET status=%s, posted_by=%s, posted_at=NOW(), audited_by=%s, audited_at=NOW(),
                    wo_complete_item_id=%s, updated_at=NOW()
                WHERE id=%s
                """,
                (DOC_STATUS_POSTED, session.get("user_id"), session.get("user_id"), complete_item.get("id"), doc_id),
            )
            return next_status, completed_qty

        try:
            next_status, completed_qty = run_in_transaction(operation)
        except ValueError as exc:
            flash(str(exc), "warning")
            return redirect(f"/production-completions/{doc_id}")
        log_action("\u5b8c\u5de5\u5165\u5e93\u5355\u8fc7\u8d26", doc.get("completion_no"), f"work_order={order.get('wo_no')} qty={qty}")
        # P0 集成：完工入库过账后自动归集成本并写入追溯链接
        try:
            _p0_run_cost_calculation(
                safe_one,
                safe_rows,
                execute_db,
                execute_and_return,
                project_code=doc.get("project_code") or order.get("project_code"),
                serial_no=doc.get("serial_no") or order.get("serial_no"),
                work_order_id=order.get("id"),
                created_by=session.get("user_id"),
            )
        except Exception:
            logger.warning("Failed to create trace snapshot in production completion", exc_info=True)
        try:
            create_trace_link(
                safe_one,
                execute_db,
                source_doc_type="work_order",
                source_doc_id=order.get("id"),
                source_doc_no=order.get("wo_no"),
                target_doc_type="production_completion",
                target_doc_id=doc_id,
                target_doc_no=doc.get("completion_no"),
                link_type="source_of",
                project_code=doc.get("project_code") or order.get("project_code"),
                serial_no=doc.get("serial_no") or order.get("serial_no"),
                created_by=session.get("user_id"),
                created_event="completion_post",
            )
        except Exception:
            logger.warning("Failed to create completion trace link", exc_info=True)
        flash(f"\u5b8c\u5de5\u5165\u5e93\u5355 {doc.get('completion_no')} \u5df2\u8fc7\u8d26\uff0c\u5de5\u5355\u7d2f\u8ba1\u5b8c\u5de5 {completed_qty}\uff0c\u72b6\u6001 {next_status}\u3002", "success")
        return redirect(f"/production-completions/{doc_id}")

    def reverse_post_document(doc_id):
        # 完工入库反过账：冲销已过账的完工入库单，红冲库存与工单完工量
        doc = completion_doc(doc_id)
        if not doc:
            flash("完工入库单不存在。", "warning")
            return redirect("/production-completions")
        if status_label(doc.get("status")) != DOC_STATUS_POSTED:
            flash("只有已过账的完工入库单可以反过账。", "warning")
            return redirect(f"/production-completions/{doc_id}")
        if doc.get("reverse_posted_at"):
            flash("完工入库单已反过账，不能重复反过账。", "warning")
            return redirect(f"/production-completions/{doc_id}")
        if not doc.get("wo_complete_item_id"):
            flash("缺少由本单生成的完工明细，不能自动反过账；历史完工数据不会被修改。", "warning")
            return redirect(f"/production-completions/{doc_id}")
        order = work_order(doc.get("work_order_id"))
        if not order:
            flash("来源工单不存在，不能反过账。", "warning")
            return redirect(f"/production-completions/{doc_id}")
        complete_item = safe_one("SELECT * FROM wo_complete_items WHERE id=%s", (doc.get("wo_complete_item_id"),))
        if not complete_item:
            flash("关联完工明细不存在，不能反过账。", "warning")
            return redirect(f"/production-completions/{doc_id}")
        if complete_item.get("source_doc_no") and complete_item.get("source_doc_no") != doc.get("completion_no"):
            flash("关联完工明细来源不匹配，不能反过账。", "warning")
            return redirect(f"/production-completions/{doc_id}")
        qty = as_decimal(doc.get("quantity"))
        balance = safe_one(
            """
            SELECT COALESCE(quantity, 0) AS quantity
            FROM inventory_balances
            WHERE product_id=%s
              AND COALESCE(warehouse_id, 0)=COALESCE(%s, 0)
              AND COALESCE(location_id, 0)=COALESCE(%s, 0)
              AND COALESCE(project_code, '')=COALESCE(%s, '')
              AND COALESCE(lot_no, '')=COALESCE(%s, '')
              AND COALESCE(serial_no, '')=COALESCE(%s, '')
            """,
            (
                doc.get("product_id"),
                doc.get("warehouse_id"),
                doc.get("location_id"),
                doc.get("project_code") or "",
                doc.get("lot_no") or "",
                doc.get("serial_no") or order.get("serial_no") or "",
            ),
        )
        available_qty = as_decimal((balance or {}).get("quantity"))
        if available_qty < qty:
            flash(f"当前库存余额 {available_qty} 小于本次反过账数量 {qty}，请先处理后续出库单据后再反过账。", "warning")
            return redirect(f"/production-completions/{doc_id}")
        def operation(cursor):
            query_one, query_rows, tx_execute_db, _tx_execute_and_return = transaction_callables(cursor)
            apply_inventory_movement(
                product_id=doc.get("product_id"),
                quantity=-qty,
                unit_cost=doc.get("unit_cost") or 0,
                tx_type="\u5b8c\u5de5\u5165\u5e93\u53cd\u8fc7\u8d26",
                reference_no=doc.get("completion_no"),
                remark=(doc.get("remark") or "\u5b8c\u5de5\u5165\u5e93\u5355\u53cd\u8fc7\u8d26") + "\uff1b\u7ea2\u51b2\u5e93\u5b58\u4e0e\u5de5\u5355\u5b8c\u5de5\u91cf",
                warehouse_id=doc.get("warehouse_id"),
                location_id=doc.get("location_id"),
                lot_no=doc.get("lot_no") or "",
                serial_no=doc.get("serial_no") or order.get("serial_no"),
                tx_date=datetime.now().date().isoformat(),
                project_code=doc.get("project_code") or "",
                query_one=query_one,
                execute_db_fn=tx_execute_db,
            )
            tx_execute_db(
                """
                UPDATE wo_complete_items
                SET qty=0, reverse_posted=TRUE, reverse_posted_at=NOW()
                WHERE id=%s
                """,
                (doc.get("wo_complete_item_id"),),
            )
            next_status, completed_qty = recompute_work_order_status(order, query_one=query_one, execute_db_fn=tx_execute_db)
            sync_work_order_costs(
                query_one,
                query_rows,
                tx_execute_db,
                order.get("id"),
                source_type="\u5b8c\u5de5\u5165\u5e93\u53cd\u8fc7\u8d26",
                source_no=doc.get("completion_no"),
                remark=doc.get("remark") or "\u5b8c\u5de5\u5165\u5e93\u5355\u53cd\u8fc7\u8d26",
            )
            tx_execute_db(
                """
                UPDATE production_completion_orders
                SET status=%s, reverse_posted_by=%s, reverse_posted_at=NOW(), updated_at=NOW()
                WHERE id=%s
                """,
                (DOC_STATUS_REVERSED, session.get("user_id"), doc_id),
            )
            return next_status, completed_qty

        next_status, completed_qty = run_in_transaction(operation)
        log_action("\u5b8c\u5de5\u5165\u5e93\u5355\u53cd\u8fc7\u8d26", doc.get("completion_no"), f"work_order={order.get('wo_no')} qty={qty}")
        flash(f"\u5b8c\u5de5\u5165\u5e93\u5355 {doc.get('completion_no')} \u5df2\u53cd\u8fc7\u8d26\uff0c\u5de5\u5355\u7d2f\u8ba1\u5b8c\u5de5 {completed_qty}\uff0c\u72b6\u6001 {next_status}\u3002", "success")
        return redirect(f"/production-completions/{doc_id}")

    @app.get("/production-completions", endpoint="production_completion_list")
    @login_required
    def production_completion_list():
        ensure_schema()
        keyword = (request.args.get("keyword") or "").strip()
        status = (request.args.get("status") or "").strip()
        rows = unified_completion_query(include_legacy=True, keyword=keyword, status=status)
        return render_template(
            "production_completion_list.html",
            rows=rows,
            keyword=keyword,
            status=status,
            status_choices=[DOC_STATUS_DRAFT, DOC_STATUS_SUBMITTED, DOC_STATUS_POSTED, DOC_STATUS_REVERSED, DOC_STATUS_VOIDED],
            status_label=status_label,
            next_action_for_status=next_action_for_status,
        )

    @app.route("/production-completions/new", methods=["GET", "POST"], endpoint="production_completion_new")
    @login_required
    def production_completion_new():
        ensure_schema()
        if request.method == "POST":
            work_order_id = form_int("work_order_id")
            order = work_order(work_order_id)
            if not order:
                flash("请选择有效的来源工单。", "warning")
                return redirect("/production-completions/new")
            action = form_text("save_action")
            if action == "unaudit":
                flash("反审请在已过账完工入库单详情页执行。", "warning")
                return redirect(f"/production-completions/new?work_order_id={work_order_id}")
            if (order.get("status") or "") in FINAL_WORK_ORDER_STATUSES:
                flash("来源工单已关闭、已完工或已作废，不能新增完工入库单。", "warning")
                return redirect(f"/work-orders/{work_order_id}")
            quantity = form_decimal("quantity")
            if quantity <= 0:
                flash("完工数量必须大于 0。", "warning")
                return redirect(f"/production-completions/new?work_order_id={work_order_id}")
            completion_date = form_text("completion_date", datetime.now().date().isoformat())
            warehouse_id = form_int("warehouse_id") or order.get("warehouse_id")
            location_id = form_int("location_id") or order.get("location_id")
            if not _location_enabled():
                location_id = None
            serial_no = form_text("serial_no") or order.get("serial_no")
            candidate = {
                "quantity": quantity,
                "complete_date": completion_date,
                "warehouse_id": warehouse_id,
                "location_id": location_id,
                "lot_no": form_text("lot_no"),
                "serial_no": serial_no,
            }
            gate = load_gate(order, candidate)
            if not gate.get("can_complete"):
                flash("完工入库被阻断：" + "；".join(gate.get("blockers") or []), "warning")
                return redirect(f"/production-completions/new?work_order_id={work_order_id}")
            doc_no = next_doc_no("PC", "production_completion_orders", "completion_no")
            unit_cost = resolve_unit_cost(order, form_decimal("unit_cost"))
            doc = execute_and_return(
                """
                INSERT INTO production_completion_orders
                    (completion_no, completion_date, work_order_id, product_id, quantity, failed_quantity,
                     unit_cost, warehouse_id, location_id, lot_no, serial_no, project_code, status, remark, created_by)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id, completion_no
                """,
                (
                    doc_no,
                    completion_date,
                    work_order_id,
                    order.get("product_id"),
                    quantity,
                    form_decimal("failed_quantity"),
                    unit_cost,
                    warehouse_id,
                    location_id,
                    form_text("lot_no"),
                    serial_no,
                    order.get("project_code"),
                    DOC_STATUS_DRAFT,
                    form_text("remark", "完工入库"),
                    session.get("user_id"),
                ),
            )
            create_trace_link(
                safe_one,
                execute_db,
                execute_and_return=execute_and_return,
                source_doc_type="work_order",
                source_doc_id=work_order_id,
                source_doc_no=order.get("wo_no"),
                target_doc_type="production_completion",
                target_doc_id=doc.get("id"),
                target_doc_no=doc_no,
                link_type="source_of",
                link_strength="hard",
                project_code=order.get("project_code"),
                serial_no=serial_no,
                created_by=session.get("user_id"),
                created_event="create_production_completion",
            )
            if action == "submit":
                execute_db(
                    "UPDATE production_completion_orders SET status=%s, submitted_by=%s, submitted_at=NOW(), updated_at=NOW() WHERE id=%s",
                    (DOC_STATUS_SUBMITTED, session.get("user_id"), doc.get("id")),
                )
            if action == "save_new":
                flash(f"完工入库单 {doc.get('completion_no')} 已保存。", "success")
                return redirect("/production-completions/new")
            flash(f"完工入库单 {doc.get('completion_no')} 已保存。", "success")
            return redirect(f"/production-completions/{doc.get('id')}")

        work_order_id = as_int(request.args.get("work_order_id"))
        order = work_order(work_order_id) if work_order_id else None
        completed = {"qty": Decimal("0")}
        gate = None
        if order:
            completed = safe_one("SELECT COALESCE(SUM(qty),0) AS qty FROM wo_complete_items WHERE wo_id=%s", (work_order_id,)) or completed
            remaining = as_decimal(order.get("quantity")) - as_decimal(completed.get("qty"))
            gate = load_gate(order, {"quantity": remaining if remaining > 0 else Decimal("0"), "serial_no": order.get("serial_no")})
        g.toolbar_extras = []
        warehouses = safe_rows("SELECT id, code, name FROM warehouses ORDER BY name LIMIT 200")
        locations = safe_rows("SELECT id, warehouse_id, code, name FROM locations WHERE COALESCE(is_active, TRUE)=TRUE ORDER BY code LIMIT 300")
        return render_template(
            "production_completion_form.html",
            work_orders=candidate_orders(),
            work_order_id=work_order_id,
            order=order,
            completed_qty=as_decimal(completed.get("qty")),
            remaining_qty=max(as_decimal((order or {}).get("quantity")) - as_decimal(completed.get("qty")), Decimal("0")) if order else Decimal("0"),
            gate=gate,
            warehouses=warehouses,
            locations=locations,
        )

    @app.route("/production-completions/<int:doc_id>/edit", methods=["GET", "POST"], endpoint="production_completion_edit")
    @login_required
    def production_completion_edit(doc_id):
        doc = completion_doc(doc_id)
        if not doc:
            flash("完工入库单不存在。", "warning")
            return redirect("/production-completions")
        if not can_edit_completion_doc(doc):
            flash("当前完工入库单不允许编辑。", "warning")
            return redirect(f"/production-completions/{doc_id}")
        if request.method == "POST":
            return update_completion_doc(doc_id)
        order = work_order(doc.get("work_order_id"))
        completed = safe_one("SELECT COALESCE(SUM(qty),0) AS qty FROM wo_complete_items WHERE wo_id=%s", (doc.get("work_order_id"),)) or {"qty": Decimal("0")}
        candidate = {
            "quantity": as_decimal(doc.get("quantity")),
            "complete_date": doc.get("completion_date"),
            "warehouse_id": doc.get("warehouse_id"),
            "location_id": doc.get("location_id"),
            "lot_no": doc.get("lot_no") or "",
            "serial_no": doc.get("serial_no") or (order or {}).get("serial_no"),
        }
        gate = load_gate(order, candidate) if order else None
        set_completion_form_toolbar(order, not gate or bool(gate.get("can_complete")))
        warehouses = safe_rows("SELECT id, code, name FROM warehouses ORDER BY name LIMIT 200")
        locations = safe_rows("SELECT id, warehouse_id, code, name FROM locations WHERE COALESCE(is_active, TRUE)=TRUE ORDER BY code LIMIT 300")
        return render_template(
            "production_completion_form.html",
            edit_mode=True,
            form_action=f"/production-completions/{doc_id}/edit",
            doc=doc,
            work_orders=[],
            work_order_id=doc.get("work_order_id"),
            order=order,
            completed_qty=as_decimal(completed.get("qty")),
            remaining_qty=max(as_decimal((order or {}).get("quantity")) - as_decimal(completed.get("qty")), Decimal("0")) if order else Decimal("0"),
            gate=gate,
            warehouses=warehouses,
            locations=locations,
        )

    @app.get("/production-completions/<int:doc_id>", endpoint="production_completion_detail")
    @login_required
    def production_completion_detail(doc_id):
        doc = completion_doc(doc_id)
        if not doc:
            return render_template("simple_detail.html", title="完工入库单", row=None, back_url="/production-completions", labels={})
        source_doc_filter = "OR st.source_doc_no=%s" if has_column("stock_transactions", "source_doc_no") else ""
        stock_params = (doc.get("completion_no"), doc.get("completion_no")) if source_doc_filter else (doc.get("completion_no"),)
        stock_rows = safe_rows(
            f"""
            SELECT st.id, st.transaction_date, st.transaction_type, st.quantity, st.unit_cost,
                   st.reference_no, st.project_code, st.serial_no, st.remark
            FROM stock_transactions st
            WHERE st.reference_no=%s {source_doc_filter}
            ORDER BY st.id DESC
            """,
            stock_params,
        )
        cost = safe_one("SELECT total_cost FROM work_order_costs WHERE work_order_id=%s ORDER BY id DESC LIMIT 1", (doc.get("work_order_id"),)) or {}
        completion_summary = completion_summary_for_order(doc.get("work_order_id")) if doc.get("work_order_id") else {}
        return render_template(
            "production_completion_detail.html",
            doc=doc,
            stock_rows=stock_rows,
            cost=cost,
            completion_summary=completion_summary,
            status_label=status_label,
        )

    @app.post("/production-completions/<int:doc_id>/<action>", endpoint="production_completion_action")
    @login_required
    def production_completion_action(doc_id, action):
        if action == "copy":
            return copy_completion_doc(doc_id)
        doc = completion_doc(doc_id)
        if not doc:
            flash("完工入库单不存在。", "warning")
            return redirect("/production-completions")
        label = status_label(doc.get("status"))
        if action == "submit":
            if label == DOC_STATUS_DRAFT:
                execute_db(
                    "UPDATE production_completion_orders SET status=%s, submitted_by=%s, submitted_at=NOW(), updated_at=NOW() WHERE id=%s",
                    (DOC_STATUS_SUBMITTED, session.get("user_id"), doc_id),
                )
                flash("完工入库单已提交。", "success")
            else:
                flash("只有草稿可以提交。", "warning")
        elif action == "post":
            return post_document(doc_id)
        elif action == "reverse":
            return reverse_post_document(doc_id)
        elif action == "delete":
            if label != DOC_STATUS_DRAFT:
                flash("只有草稿完工入库单可以删除；已过账单据请先反审。", "warning")
            elif doc.get("posted_at") or doc.get("wo_complete_item_id") or doc.get("reverse_posted_at"):
                flash("该完工入库单已有过账记录，不能直接删除。", "warning")
            elif safe_one("SELECT id FROM stock_transactions WHERE reference_no=%s OR source_doc_no=%s LIMIT 1", (doc.get("completion_no"), doc.get("completion_no"))):
                flash("该完工入库单已有库存流水，不能直接删除。", "warning")
            else:
                execute_db("DELETE FROM production_completion_orders WHERE id=%s", (doc_id,))
                log_action("删除完工入库单草稿", doc.get("completion_no"))
                flash(f"完工入库单 {doc.get('completion_no')} 已删除。", "success")
                return redirect("/production-completions")
        elif action == "void":
            if label in {DOC_STATUS_DRAFT, DOC_STATUS_SUBMITTED}:
                execute_db(
                    "UPDATE production_completion_orders SET status=%s, voided_by=%s, voided_at=NOW(), updated_at=NOW() WHERE id=%s",
                    (DOC_STATUS_VOIDED, session.get("user_id"), doc_id),
                )
                flash("完工入库单已作废。", "success")
            else:
                flash("只有草稿或已提交单据可以作废。", "warning")
        else:
            flash("不支持的完工入库单动作。", "warning")
        return redirect(f"/production-completions/{doc_id}")
