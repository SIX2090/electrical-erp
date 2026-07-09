"""Production pick routes: pick list, pick form, and material issue for production."""
from datetime import datetime
from decimal import Decimal

from flask import flash, g, redirect, render_template, request, session

from services.work_order_material_service import (
    returnable_material_quantity,
    resolve_unit_cost,
    validate_issue_stock,
)
from services.work_order_cost_service import sync_work_order_costs
from services.trace_engine import create_trace_link

import logging

logger = logging.getLogger(__name__)


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

DRAFT_STATUSES = {"draft", "草稿", None, ""}
SUBMITTED_STATUSES = {"assigned", "submitted", "已提交"}
POSTED_STATUSES = {"completed", "posted", "已过账"}
VOIDED_STATUSES = {"cancelled", "voided", "已作废"}


def register_production_pick_routes(app, deps):
    login_required = deps["login_required"]
    safe_rows = deps["safe_rows"]
    safe_one = deps["safe_one"]
    execute_db = deps["execute_db"]
    execute_and_return = deps["execute_and_return"]
    next_doc_no = deps["next_doc_no"]
    as_decimal = deps["as_decimal"]
    form_text = deps["form_text"]
    form_int = deps["form_int"]
    apply_inventory_movement = deps["apply_inventory_movement"]
    log_action = deps["log_action"]
    run_in_transaction = deps.get("run_in_transaction") or (lambda operation: operation(None))

    def transaction_callables(cursor):
        if cursor is None:
            return safe_one, safe_rows, execute_db

        def query_one(sql, params=None):
            cursor.execute(sql, params or ())
            return cursor.fetchone()

        def query_rows(sql, params=None):
            cursor.execute(sql, params or ())
            return cursor.fetchall()

        def tx_execute_db(sql, params=None):
            cursor.execute(sql, params or ())

        return query_one, query_rows, tx_execute_db

    def ensure_schema():
        # DDL 已迁移至 services/schema_migrations.py（20260619_001_pick_lists_schema）
        # 请求期不再执行 CREATE TABLE / ALTER TABLE
        pass

    def meta(doc_type):
        if doc_type == "production_return":
            return {
                "title": "生产退料单",
                "list_url": "/production-returns",
                "detail_prefix": "/production-returns",
                "new_url": "/production-returns/new",
                "prefix": "PRTN",
                "tx_type": "生产退料",
                "direction": Decimal("1"),
                "quantity_label": "退料数量",
                "quantity_short_label": "退料",
                "source_hint": "从已领未退的工单用料行带出可退数量。",
            }
        return {
            "title": "生产领料单",
            "list_url": "/production-issues",
            "detail_prefix": "/production-issues",
            "new_url": "/production-issues/new",
            "prefix": "PISS",
            "tx_type": "生产领料",
            "direction": Decimal("-1"),
            "quantity_label": "领料数量",
            "quantity_short_label": "领料",
            "source_hint": "从工单用料带出待领数量。",
        }

    def status_label(value):
        return {
            "draft": "草稿",
            "assigned": "已提交",
            "in_progress": "处理中",
            "submitted": "已提交",
            "completed": "已过账",
            "posted": "已过账",
            "cancelled": "已作废",
            "voided": "已作废",
            "草稿": "草稿",
            "已提交": "已提交",
            "已过账": "已过账",
            "已作废": "已作废",
        }.get(value or "draft", value or "草稿")

    def can_edit_pick_document(doc):
        if not doc:
            return False
        if doc.get("posted_at") or doc.get("voided_at"):
            return False
        return (doc.get("status") or "draft") in DRAFT_STATUSES

    def open_work_orders(doc_type):
        ensure_schema()
        comparator = (
            "COALESCE(mi.issued_qty,0) > COALESCE(mi.returned_qty,0)"
            if doc_type == "production_return"
            else "GREATEST(COALESCE(mi.required_qty,0)-COALESCE(mi.issued_qty,0)+COALESCE(mi.returned_qty,0),0) > 0"
        )
        return safe_rows(
            f"""
            SELECT wo.id, wo.wo_no, wo.project_code, wo.serial_no, wo.status,
                   COUNT(mi.id) AS line_count,
                   SUM(CASE WHEN {comparator} THEN 1 ELSE 0 END) AS available_quantity
            FROM work_orders wo
            JOIN wo_material_items mi ON mi.wo_id=wo.id
            WHERE COALESCE(wo.status,'') NOT IN %s
            GROUP BY wo.id
            HAVING SUM(CASE WHEN {comparator} THEN 1 ELSE 0 END) > 0
            ORDER BY wo.id DESC
            LIMIT 200
            """,
            (tuple(FINAL_WORK_ORDER_STATUSES),),
        )

    def work_order(work_order_id):
        return safe_one(
            """
            SELECT wo.*, p.code AS product_code, p.name AS product_name
            FROM work_orders wo
            LEFT JOIN products p ON p.id=wo.product_id
            WHERE wo.id=%s
            """,
            (work_order_id,),
        )

    def preview_lines(work_order_id, doc_type):
        if not work_order_id:
            return []
        rows = safe_rows(
            """
            SELECT mi.*, p.code AS product_code, p.name AS product_name, p.specification, p.unit
            FROM wo_material_items mi
            LEFT JOIN products p ON p.id=mi.product_id
            WHERE mi.wo_id=%s
            ORDER BY mi.id
            """,
            (work_order_id,),
        )
        result = []
        for row in rows:
            if doc_type == "production_return":
                max_qty = returnable_material_quantity(row)
            else:
                max_qty = as_decimal(row.get("required_qty")) - as_decimal(row.get("issued_qty")) + as_decimal(row.get("returned_qty"))
            if max_qty <= 0:
                continue
            row["max_quantity"] = max_qty
            row["material_code_display"] = row.get("material_code") or row.get("product_code")
            row["material_name_display"] = row.get("material_name") or row.get("product_name")
            row["material_spec_display"] = row.get("material_spec") or row.get("specification")
            row["material_unit_display"] = row.get("material_unit") or row.get("unit")
            row["line_warehouse_id"] = row.get("warehouse_id")
            row["line_location_id"] = row.get("location_id")
            result.append(row)
        return result

    def warehouses():
        return safe_rows("SELECT id, code, name FROM warehouses ORDER BY name LIMIT 300")

    def locations():
        return safe_rows("SELECT id, warehouse_id, code, name FROM locations ORDER BY code LIMIT 500")

    def create_document(doc_type):
        ensure_schema()
        m = meta(doc_type)
        work_order_id = form_int("work_order_id")
        order = work_order(work_order_id)
        if not order:
            return None, "请选择有效的来源生产工单。"
        selected_lines = preview_lines(work_order_id, doc_type)
        if not selected_lines:
            return None, "来源工单没有可领或可退的用料行。"
        doc_date = form_text("doc_date", datetime.now().date().isoformat())
        doc_no = next_doc_no(m["prefix"], "pick_lists", "doc_no")
        item_ids = request.form.getlist("item_id[]")
        line_warehouse_ids = request.form.getlist("line_warehouse_id[]")
        line_location_ids = request.form.getlist("line_location_id[]")
        header_warehouse_id = 0
        header_location_id = 0
        for idx, _item_id in enumerate(item_ids):
            header_warehouse_id = int(line_warehouse_ids[idx]) if idx < len(line_warehouse_ids) and line_warehouse_ids[idx] else 0
            header_location_id = int(line_location_ids[idx]) if idx < len(line_location_ids) and line_location_ids[idx] else 0
            if header_warehouse_id:
                break
        if not header_warehouse_id:
            return None, "请选择明细仓库。"
        doc = execute_and_return(
            """
            INSERT INTO pick_lists
                (doc_type, doc_no, pick_no, doc_date, pick_date, work_order_id, warehouse_id, location_id,
                 project_code, serial_no, status, created_by, remark)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'draft',%s,%s)
            RETURNING id, doc_no
            """,
            (
                doc_type,
                doc_no,
                doc_no,
                doc_date,
                doc_date,
                work_order_id,
                header_warehouse_id,
                header_location_id or None,
                order.get("project_code"),
                order.get("serial_no"),
                session.get("user_id"),
                form_text("remark"),
            ),
        )
        create_trace_link(
            safe_one,
            execute_db,
            execute_and_return=execute_and_return,
            source_doc_type="work_order",
            source_doc_id=work_order_id,
            source_doc_no=order.get("wo_no"),
            target_doc_type="pick_list",
            target_doc_id=doc.get("id"),
            target_doc_no=doc_no,
            link_type="dispatches_to",
            link_strength="hard",
            project_code=order.get("project_code"),
            serial_no=order.get("serial_no"),
            created_by=session.get("user_id"),
            created_event=f"create_{doc_type}",
        )
        quantities = request.form.getlist("quantity[]")
        lot_nos = request.form.getlist("lot_no[]")
        created = 0
        line_map = {str(row.get("id")): row for row in selected_lines}
        for idx, item_id in enumerate(item_ids):
            row = line_map.get(str(item_id))
            if not row:
                continue
            qty = as_decimal(quantities[idx] if idx < len(quantities) else 0)
            max_qty = as_decimal(row.get("max_quantity"))
            if qty <= 0:
                continue
            if qty > max_qty:
                execute_db("DELETE FROM pick_lists WHERE id=%s", (doc.get("id"),))
                return None, f"{row.get('material_name_display') or row.get('product_id')} 数量不能超过 {max_qty}。"
            line_warehouse_id = int(line_warehouse_ids[idx]) if idx < len(line_warehouse_ids) and line_warehouse_ids[idx] else 0
            line_location_id = int(line_location_ids[idx]) if idx < len(line_location_ids) and line_location_ids[idx] else 0
            if not line_warehouse_id:
                execute_db("DELETE FROM pick_lists WHERE id=%s", (doc.get("id"),))
                return None, f"{row.get('material_name_display') or row.get('product_id')} 必须选择仓库和库位。"
            execute_db(
                """
                INSERT INTO pick_list_items
                    (pick_list_id, pick_id, wo_material_item_id, product_id, material_code, material_name,
                     material_spec, material_unit, quantity, posted_qty, unit_cost, warehouse_id, location_id,
                     lot_no, serial_no, source_line_no, line_project_code, line_serial_no, remark)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,0,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    doc.get("id"),
                    doc.get("id"),
                    row.get("id"),
                    row.get("product_id"),
                    row.get("material_code_display"),
                    row.get("material_name_display"),
                    row.get("material_spec_display"),
                    row.get("material_unit_display"),
                    qty,
                    row.get("unit_cost") or 0,
                    line_warehouse_id,
                    line_location_id or None,
                    lot_nos[idx] if idx < len(lot_nos) else row.get("lot_no"),
                    row.get("line_serial_no") or order.get("serial_no"),
                    row.get("source_line_no"),
                    row.get("line_project_code") or order.get("project_code"),
                    row.get("line_serial_no") or order.get("serial_no"),
                    row.get("remark") or form_text("remark"),
                ),
            )
            created += 1
        if not created:
            execute_db("DELETE FROM pick_lists WHERE id=%s", (doc.get("id"),))
            return None, "请至少保留一行数量大于 0 的用料明细。"
        log_action(f"创建{m['title']}", doc_no, f"work_order_id={work_order_id}")
        return doc, ""

    def load_document(doc_type, doc_id):
        return safe_one(
            """
            SELECT pl.*, wo.wo_no, wo.status AS work_order_status,
                   w.name AS warehouse_name, l.code AS location_code, COALESCE(l.name,l.code) AS location_name
            FROM pick_lists pl
            LEFT JOIN work_orders wo ON wo.id=pl.work_order_id
            LEFT JOIN warehouses w ON w.id=pl.warehouse_id
            LEFT JOIN locations l ON l.id=pl.location_id
            WHERE pl.id=%s AND pl.doc_type=%s
            """,
            (doc_id, doc_type),
        )

    def load_lines(doc_id):
        return safe_rows(
            """
            SELECT pli.*, p.code AS product_code, p.name AS product_name,
                   w.name AS warehouse_name,
                   COALESCE(l.name,l.code) AS location_name
            FROM pick_list_items pli
            LEFT JOIN products p ON p.id=pli.product_id
            LEFT JOIN warehouses w ON w.id=pli.warehouse_id
            LEFT JOIN locations l ON l.id=pli.location_id
            WHERE pli.pick_list_id=%s OR pli.pick_id=%s
            ORDER BY pli.id
            """,
            (doc_id, doc_id),
        )

    def edit_lines(doc_type, doc):
        lines = load_lines(doc.get("id"))
        available = {str(row.get("id")): row for row in preview_lines(doc.get("work_order_id"), doc_type)}
        result = []
        for line in lines:
            source = available.get(str(line.get("wo_material_item_id"))) or {}
            source_item_id = line.get("wo_material_item_id")
            line["id"] = source_item_id
            line["max_quantity"] = source.get("max_quantity") or line.get("quantity") or 0
            line["material_code_display"] = line.get("material_code") or line.get("product_code") or source.get("material_code_display")
            line["material_name_display"] = line.get("material_name") or line.get("product_name") or source.get("material_name_display")
            line["material_spec_display"] = line.get("material_spec") or source.get("material_spec_display")
            line["material_unit_display"] = line.get("material_unit") or source.get("material_unit_display")
            line["line_warehouse_id"] = line.get("warehouse_id")
            line["line_location_id"] = line.get("location_id")
            result.append(line)
        return result

    def update_document(doc_type, doc_id):
        ensure_schema()
        m = meta(doc_type)
        doc = load_document(doc_type, doc_id)
        if not doc:
            flash(f"{m['title']}不存在。", "warning")
            return redirect(m["list_url"])
        if not can_edit_pick_document(doc):
            flash(f"{m['title']}当前状态不允许编辑；已提交、已过账或已作废单据请走状态流程。", "warning")
            return redirect(f"{m['detail_prefix']}/{doc_id}")
        order = work_order(doc.get("work_order_id"))
        if not order or (order.get("status") or "") in FINAL_WORK_ORDER_STATUSES:
            flash("来源生产工单已关闭、已完工或已作废，不能继续编辑。", "warning")
            return redirect(f"{m['detail_prefix']}/{doc_id}")
        selected_lines = {str(row.get("id")): row for row in preview_lines(doc.get("work_order_id"), doc_type)}
        item_ids = request.form.getlist("item_id[]")
        quantities = request.form.getlist("quantity[]")
        line_warehouse_ids = request.form.getlist("line_warehouse_id[]")
        line_location_ids = request.form.getlist("line_location_id[]")
        lot_nos = request.form.getlist("lot_no[]")
        rows_to_save = []
        for idx, item_id in enumerate(item_ids):
            source = selected_lines.get(str(item_id))
            if not source:
                continue
            qty = as_decimal(quantities[idx] if idx < len(quantities) else 0)
            if qty <= 0:
                continue
            max_qty = as_decimal(source.get("max_quantity"))
            if qty > max_qty:
                flash(f"{source.get('material_name_display') or source.get('product_id')} 数量不能超过 {max_qty}。", "warning")
                return redirect(f"{m['detail_prefix']}/{doc_id}/edit")
            line_warehouse_id = int(line_warehouse_ids[idx]) if idx < len(line_warehouse_ids) and line_warehouse_ids[idx] else 0
            line_location_id = int(line_location_ids[idx]) if idx < len(line_location_ids) and line_location_ids[idx] else 0
            if not line_warehouse_id:
                flash(f"{source.get('material_name_display') or source.get('product_id')} 必须选择仓库和库位。", "warning")
                return redirect(f"{m['detail_prefix']}/{doc_id}/edit")
            rows_to_save.append((source, qty, line_warehouse_id, line_location_id, lot_nos[idx] if idx < len(lot_nos) else source.get("lot_no")))
        if not rows_to_save:
            flash("请至少保留一行数量大于 0 的用料明细。", "warning")
            return redirect(f"{m['detail_prefix']}/{doc_id}/edit")
        doc_date = form_text("doc_date", datetime.now().date().isoformat())
        header_warehouse_id = rows_to_save[0][2]
        header_location_id = rows_to_save[0][3]
        execute_db(
            """
            UPDATE pick_lists
            SET doc_date=%s, pick_date=%s, warehouse_id=%s, location_id=%s,
                project_code=%s, serial_no=%s, remark=%s
            WHERE id=%s AND doc_type=%s
            """,
            (doc_date, doc_date, header_warehouse_id, header_location_id or None, order.get("project_code"), order.get("serial_no"), form_text("remark"), doc_id, doc_type),
        )
        execute_db("DELETE FROM pick_list_items WHERE pick_list_id=%s OR pick_id=%s", (doc_id, doc_id))
        for source, qty, line_warehouse_id, line_location_id, lot_no in rows_to_save:
            execute_db(
                """
                INSERT INTO pick_list_items
                    (pick_list_id, pick_id, wo_material_item_id, product_id, material_code, material_name,
                     material_spec, material_unit, quantity, posted_qty, unit_cost, warehouse_id, location_id,
                     lot_no, serial_no, source_line_no, line_project_code, line_serial_no, remark)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,0,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    doc_id,
                    doc_id,
                    source.get("id"),
                    source.get("product_id"),
                    source.get("material_code_display"),
                    source.get("material_name_display"),
                    source.get("material_spec_display"),
                    source.get("material_unit_display"),
                    qty,
                    source.get("unit_cost") or 0,
                    line_warehouse_id,
                    line_location_id or None,
                    lot_no,
                    source.get("line_serial_no") or order.get("serial_no"),
                    source.get("source_line_no"),
                    source.get("line_project_code") or order.get("project_code"),
                    source.get("line_serial_no") or order.get("serial_no"),
                    source.get("remark") or form_text("remark"),
                ),
            )
        log_action(f"编辑{m['title']}", doc.get("doc_no") or doc.get("pick_no"), f"id={doc_id}")
        if request.form.get("save_action") == "post":
            execute_db("UPDATE pick_lists SET status='assigned' WHERE id=%s", (doc_id,))
            return post_document(doc_type, doc_id)
        flash(f"{m['title']}已保存修改。", "success")
        return redirect(f"{m['detail_prefix']}/{doc_id}")

    def update_stock_transaction_source(doc_type, doc, line, unit_cost, execute_db_fn=None):
        execute_db_fn = execute_db_fn or execute_db
        ref_no = doc.get("doc_no") or doc.get("pick_no")
        execute_db_fn(
            """
            UPDATE stock_transactions
            SET source_doc_type=%s,
                source_doc_no=%s,
                source_line_no=%s,
                amount=COALESCE(quantity,0) * COALESCE(unit_cost,0)
            WHERE id=(
                SELECT id FROM stock_transactions
                WHERE reference_no=%s
                  AND product_id=%s
                  AND transaction_type=%s
                ORDER BY id DESC
                LIMIT 1
            )
            """,
            (
                doc_type,
                ref_no,
                line.get("source_line_no") or str(line.get("wo_material_item_id") or ""),
                ref_no,
                line.get("product_id"),
                meta(doc_type)["tx_type"],
            ),
        )

    def sync_batch_tracking(line, doc, query_one=None, execute_db_fn=None, movement_qty=None):
        query_one = query_one or safe_one
        execute_db_fn = execute_db_fn or execute_db
        product_id = line.get("product_id")
        warehouse_id = line.get("warehouse_id") or doc.get("warehouse_id")
        location_id = line.get("location_id") or doc.get("location_id")
        lot_no = line.get("lot_no") or ""
        serial_no = line.get("serial_no") or doc.get("serial_no") or ""
        project_code = line.get("line_project_code") or doc.get("project_code") or ""
        balance = query_one(
            """
            SELECT COALESCE(SUM(quantity),0) AS quantity,
                   CASE WHEN COALESCE(SUM(quantity),0) <> 0
                       THEN COALESCE(SUM(quantity * COALESCE(unit_cost,0)) / NULLIF(SUM(quantity),0),0)
                       ELSE COALESCE(MAX(unit_cost),0)
                   END AS unit_cost
            FROM inventory_balances
            WHERE product_id=%s
              AND COALESCE(warehouse_id,0)=COALESCE(%s,0)
              AND COALESCE(location_id,0)=COALESCE(%s,0)
              AND COALESCE(lot_no,'')=COALESCE(%s,'')
              AND COALESCE(serial_no,'')=COALESCE(%s,'')
              AND COALESCE(project_code,'')=COALESCE(%s,'')
            """,
            (product_id, warehouse_id, location_id, lot_no, serial_no, project_code),
        ) or {}
        qty = as_decimal(balance.get("quantity"))
        unit_cost = as_decimal(balance.get("unit_cost"))
        mv_qty = as_decimal(movement_qty) if movement_qty is not None else qty
        batch = query_one(
            """
            SELECT id
            FROM batch_tracking
            WHERE product_id=%s
              AND COALESCE(warehouse_id,0)=COALESCE(%s,0)
              AND COALESCE(location_id,0)=COALESCE(%s,0)
              AND COALESCE(lot_no,'')=COALESCE(%s,'')
              AND COALESCE(serial_no,'')=COALESCE(%s,'')
              AND COALESCE(project_code,'')=COALESCE(%s,'')
            ORDER BY id
            LIMIT 1
            FOR UPDATE
            """,
            (product_id, warehouse_id, location_id, lot_no, serial_no, project_code),
        )
        if batch:
            execute_db_fn(
                """
                UPDATE batch_tracking
                SET quantity_available=%s,
                    quantity_in=CASE WHEN %s > 0 THEN COALESCE(quantity_in,0) + %s ELSE COALESCE(quantity_in,0) END,
                    quantity_out=CASE WHEN %s < 0 THEN COALESCE(quantity_out,0) + (-%s) ELSE COALESCE(quantity_out,0) END,
                    unit_cost=%s,
                    updated_at=NOW()
                WHERE id=%s
                """,
                (qty, mv_qty, mv_qty, mv_qty, mv_qty, unit_cost, batch.get("id")),
            )
        else:
            execute_db_fn(
                """
                INSERT INTO batch_tracking
                    (lot_no, product_id, warehouse_id, location_id, serial_no, project_code,
                     quantity_in, quantity_out, quantity_available, unit_cost, source_order_no,
                     status, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s,'derived',NOW(),NOW())
                """,
                (
                    lot_no,
                    product_id,
                    warehouse_id,
                    location_id,
                    serial_no,
                    project_code,
                    mv_qty if mv_qty > 0 else Decimal("0"),
                    -mv_qty if mv_qty < 0 else Decimal("0"),
                    qty,
                    unit_cost,
                    doc.get("doc_no") or doc.get("pick_no"),
                ),
            )

    def post_document(doc_type, doc_id):
        ensure_schema()
        m = meta(doc_type)
        doc = load_document(doc_type, doc_id)
        if not doc:
            flash(f"{m['title']}不存在。", "warning")
            return redirect(m["list_url"])
        if doc.get("status") in POSTED_STATUSES:
            flash("单据已过账，请勿重复过账。", "warning")
            return redirect(f"{m['detail_prefix']}/{doc_id}")
        if doc.get("status") not in SUBMITTED_STATUSES:
            flash("只有已提交单据可以过账；草稿请先提交或使用提交并过账。", "warning")
            return redirect(f"{m['detail_prefix']}/{doc_id}")
        lines = load_lines(doc_id)
        if not lines:
            flash("单据没有明细，不能过账。", "warning")
            return redirect(f"{m['detail_prefix']}/{doc_id}")
        for line in lines:
            qty = as_decimal(line.get("quantity"))
            item = safe_one("SELECT * FROM wo_material_items WHERE id=%s", (line.get("wo_material_item_id"),)) or {}
            if qty <= 0 or not item:
                flash("存在无效明细，不能过账。", "warning")
                return redirect(f"{m['detail_prefix']}/{doc_id}")
            if doc_type == "production_issue":
                pending = as_decimal(item.get("required_qty")) - as_decimal(item.get("issued_qty")) + as_decimal(item.get("returned_qty"))
                if qty > pending:
                    flash("领料数量超过工单待领数量。", "warning")
                    return redirect(f"{m['detail_prefix']}/{doc_id}")
                stock_error, available_qty = validate_issue_stock(item, qty, line.get("warehouse_id") or doc.get("warehouse_id"), safe_one)
                if stock_error == "stock_shortage":
                    material_name = line.get("material_name") or line.get("product_id")
                    flash(f"库存不足：{material_name} 可用 {available_qty}，需 {qty}。", "warning")
                    return redirect(f"{m['detail_prefix']}/{doc_id}")
            elif qty > returnable_material_quantity(item):
                flash("退料数量超过可退数量。", "warning")
                return redirect(f"{m['detail_prefix']}/{doc_id}")
        def operation(cursor):
            query_one, query_rows, tx_execute_db = transaction_callables(cursor)
            for line in lines:
                qty = as_decimal(line.get("quantity"))
                unit_cost = resolve_unit_cost(line.get("unit_cost"), line.get("product_id"), line.get("warehouse_id") or doc.get("warehouse_id"), query_one)
                apply_inventory_movement(
                    product_id=line.get("product_id"),
                    quantity=qty * m["direction"],
                    unit_cost=unit_cost,
                    tx_type=m["tx_type"],
                    reference_no=doc.get("doc_no") or doc.get("pick_no"),
                    remark=doc.get("remark") or m["title"],
                    warehouse_id=line.get("warehouse_id") or doc.get("warehouse_id"),
                    location_id=line.get("location_id") or doc.get("location_id"),
                    lot_no=line.get("lot_no") or "",
                    serial_no=line.get("serial_no") or doc.get("serial_no"),
                    tx_date=doc.get("doc_date"),
                    project_code=line.get("line_project_code") or doc.get("project_code") or "",
                    query_one=query_one,
                    execute_db_fn=tx_execute_db,
                )
                update_stock_transaction_source(doc_type, doc, line, unit_cost, execute_db_fn=tx_execute_db)
                # Link the pick list to the inventory movement for traceability.
                st_row = query_one(
                    "SELECT id FROM stock_transactions WHERE reference_no=%s AND product_id=%s AND transaction_type=%s ORDER BY id DESC LIMIT 1",
                    (doc.get("doc_no") or doc.get("pick_no"), line.get("product_id"), m["tx_type"]),
                ) or {}
                st_id = st_row.get("id")
                if st_id:
                    try:
                        create_trace_link(
                            query_one,
                            tx_execute_db,
                            source_doc_type=doc_type,
                            source_doc_id=doc_id,
                            source_doc_no=doc.get("doc_no") or doc.get("pick_no"),
                            source_line_id=line.get("id"),
                            target_doc_type="stock_transaction",
                            target_doc_id=st_id,
                            link_type="posts_to",
                            link_strength="soft",
                            project_code=line.get("line_project_code") or doc.get("project_code"),
                            serial_no=line.get("serial_no") or doc.get("serial_no"),
                            created_by=session.get("user_id"),
                            created_event="pick_list_inventory",
                        )
                    except Exception:
                        logger.warning("Failed to post inventory in production pick", exc_info=True)
                sync_batch_tracking(line, doc, query_one=query_one, execute_db_fn=tx_execute_db, movement_qty=qty * m["direction"])
                if doc_type == "production_issue":
                    tx_execute_db(
                        "UPDATE wo_material_items SET issued_qty=COALESCE(issued_qty,0)+%s, unit_cost=COALESCE(NULLIF(unit_cost,0),%s) WHERE id=%s",
                        (qty, unit_cost, line.get("wo_material_item_id")),
                    )
                else:
                    tx_execute_db(
                        "UPDATE wo_material_items SET returned_qty=COALESCE(returned_qty,0)+%s WHERE id=%s",
                        (qty, line.get("wo_material_item_id")),
                    )
                tx_execute_db("UPDATE pick_list_items SET posted_qty=%s, unit_cost=%s WHERE id=%s", (qty, unit_cost, line.get("id")))
            sync_work_order_costs(
                query_one,
                query_rows,
                tx_execute_db,
                doc.get("work_order_id"),
                source_type=m["tx_type"],
                source_no=doc.get("doc_no") or doc.get("pick_no"),
                remark=m["title"],
            )
            tx_execute_db("UPDATE pick_lists SET status='completed', posted_at=NOW(), approved_by=%s WHERE id=%s", (session.get("user_id"), doc_id))

        run_in_transaction(operation)
        log_action(f"{m['title']}\u8fc7\u8d26", doc.get("doc_no") or doc.get("pick_no"), f"id={doc_id}")
        flash(f"{m['title']}\u5df2\u8fc7\u8d26\uff0c\u5e93\u5b58\u6d41\u6c34\u548c\u5de5\u5355\u7528\u6599\u5df2\u56de\u5199\u3002", "success")
        return redirect(f"{m['detail_prefix']}/{doc_id}")
        for line in lines:
            qty = as_decimal(line.get("quantity"))
            unit_cost = resolve_unit_cost(line.get("unit_cost"), line.get("product_id"), line.get("warehouse_id") or doc.get("warehouse_id"), safe_one)
            apply_inventory_movement(
                product_id=line.get("product_id"),
                quantity=qty * m["direction"],
                unit_cost=unit_cost,
                tx_type=m["tx_type"],
                reference_no=doc.get("doc_no") or doc.get("pick_no"),
                remark=doc.get("remark") or m["title"],
                warehouse_id=line.get("warehouse_id") or doc.get("warehouse_id"),
                location_id=line.get("location_id") or doc.get("location_id"),
                lot_no=line.get("lot_no") or "",
                serial_no=line.get("serial_no") or doc.get("serial_no"),
                tx_date=doc.get("doc_date"),
                project_code=line.get("line_project_code") or doc.get("project_code") or "",
            )
            update_stock_transaction_source(doc_type, doc, line, unit_cost)
            sync_batch_tracking(line, doc, movement_qty=qty * m["direction"])
            if doc_type == "production_issue":
                execute_db(
                    "UPDATE wo_material_items SET issued_qty=COALESCE(issued_qty,0)+%s, unit_cost=COALESCE(NULLIF(unit_cost,0),%s) WHERE id=%s",
                    (qty, unit_cost, line.get("wo_material_item_id")),
                )
            else:
                execute_db(
                    "UPDATE wo_material_items SET returned_qty=COALESCE(returned_qty,0)+%s WHERE id=%s",
                    (qty, line.get("wo_material_item_id")),
                )
            execute_db("UPDATE pick_list_items SET posted_qty=%s, unit_cost=%s WHERE id=%s", (qty, unit_cost, line.get("id")))
        sync_work_order_costs(
            safe_one,
            safe_rows,
            execute_db,
            doc.get("work_order_id"),
            source_type=m["tx_type"],
            source_no=doc.get("doc_no") or doc.get("pick_no"),
            remark=m["title"],
        )
        execute_db("UPDATE pick_lists SET status='completed', posted_at=NOW(), approved_by=%s WHERE id=%s", (session.get("user_id"), doc_id))
        log_action(f"{m['title']}过账", doc.get("doc_no") or doc.get("pick_no"), f"id={doc_id}")
        flash(f"{m['title']}已过账，库存流水和工单用料已回写。", "success")
        return redirect(f"{m['detail_prefix']}/{doc_id}")

    def unaudit_document(doc_type, doc_id):
        ensure_schema()
        m = meta(doc_type)
        doc = load_document(doc_type, doc_id)
        if not doc:
            flash(f"{m['title']}不存在。", "warning")
            return redirect(m["list_url"])
        if doc.get("status") not in POSTED_STATUSES:
            flash("只有已过账单据可以反审。", "warning")
            return redirect(f"{m['detail_prefix']}/{doc_id}")
        lines = load_lines(doc_id)
        if not lines:
            flash("单据没有明细，不能反审。", "warning")
            return redirect(f"{m['detail_prefix']}/{doc_id}")

        def operation(cursor):
            query_one, query_rows, tx_execute_db = transaction_callables(cursor)
            fresh = query_one("SELECT status FROM pick_lists WHERE id=%s AND doc_type=%s FOR UPDATE", (doc_id, doc_type)) or {}
            if fresh.get("status") not in POSTED_STATUSES:
                raise ValueError("单据状态已变更，反审中止。")
            for line in lines:
                qty = as_decimal(line.get("posted_qty") or line.get("quantity"))
                if qty <= 0:
                    continue
                unit_cost = resolve_unit_cost(line.get("unit_cost"), line.get("product_id"), line.get("warehouse_id") or doc.get("warehouse_id"), query_one)
                apply_inventory_movement(
                    product_id=line.get("product_id"),
                    quantity=-(qty * m["direction"]),
                    unit_cost=unit_cost,
                    tx_type=f"{m['tx_type']}反审",
                    reference_no=doc.get("doc_no") or doc.get("pick_no"),
                    remark=doc.get("remark") or f"{m['title']}反审",
                    warehouse_id=line.get("warehouse_id") or doc.get("warehouse_id"),
                    location_id=line.get("location_id") or doc.get("location_id"),
                    lot_no=line.get("lot_no") or "",
                    serial_no=line.get("serial_no") or doc.get("serial_no"),
                    tx_date=doc.get("doc_date"),
                    project_code=line.get("line_project_code") or doc.get("project_code") or "",
                    query_one=query_one,
                    execute_db_fn=tx_execute_db,
                )
                sync_batch_tracking(line, doc, query_one=query_one, execute_db_fn=tx_execute_db, movement_qty=-(qty * m["direction"]))
                if doc_type == "production_issue":
                    tx_execute_db(
                        "UPDATE wo_material_items SET issued_qty=GREATEST(COALESCE(issued_qty,0)-%s,0) WHERE id=%s",
                        (qty, line.get("wo_material_item_id")),
                    )
                else:
                    tx_execute_db(
                        "UPDATE wo_material_items SET returned_qty=GREATEST(COALESCE(returned_qty,0)-%s,0) WHERE id=%s",
                        (qty, line.get("wo_material_item_id")),
                    )
                tx_execute_db("UPDATE pick_list_items SET posted_qty=0 WHERE id=%s", (line.get("id"),))
            sync_work_order_costs(
                query_one,
                query_rows,
                tx_execute_db,
                doc.get("work_order_id"),
                source_type=f"{m['tx_type']}反审",
                source_no=doc.get("doc_no") or doc.get("pick_no"),
                remark=f"{m['title']}反审",
            )
            tx_execute_db("UPDATE pick_lists SET status='assigned', posted_at=NULL, approved_by=NULL WHERE id=%s", (doc_id,))

        try:
            run_in_transaction(operation)
        except ValueError as exc:
            flash(str(exc), "warning")
            return redirect(f"{m['detail_prefix']}/{doc_id}")
        log_action(f"{m['title']}反审", doc.get("doc_no") or doc.get("pick_no"), f"id={doc_id}")
        flash(f"{m['title']}已反审，库存和工单用料已回滚。", "success")
        return redirect(f"{m['detail_prefix']}/{doc_id}")

    def list_page(doc_type):
        m = meta(doc_type)
        ensure_schema()
        keyword = request.args.get("keyword", "").strip()
        keyword_sql = ""
        params = [doc_type]
        if keyword:
            keyword_sql = "AND (pl.doc_no ILIKE %s OR wo.wo_no ILIKE %s OR pl.project_code ILIKE %s OR pl.serial_no ILIKE %s)"
            params.extend([f"%{keyword}%"] * 4)
        rows = safe_rows(
            f"""
            SELECT pl.*, wo.wo_no, w.name AS warehouse_name,
                   COALESCE(SUM(pli.quantity),0) AS total_quantity,
                   COUNT(pli.id) AS line_count
            FROM pick_lists pl
            LEFT JOIN work_orders wo ON wo.id=pl.work_order_id
            LEFT JOIN warehouses w ON w.id=pl.warehouse_id
            LEFT JOIN pick_list_items pli ON pli.pick_list_id=pl.id OR pli.pick_id=pl.id
            WHERE pl.doc_type=%s {keyword_sql}
            GROUP BY pl.id, wo.wo_no, w.name
            ORDER BY pl.id DESC
            LIMIT 200
            """,
            tuple(params),
        )
        return render_template("production_pick_list.html", title=f"{m['title']}列表", rows=rows, meta=m, keyword=keyword, status_label=status_label)

    def form_page(doc_type):
        m = meta(doc_type)
        g.toolbar_extras = []
        work_order_id = request.args.get("work_order_id", "").strip()
        if request.method == "POST":
            if request.form.get("save_action") == "unaudit":
                flash("反审请在已过账单据详情页执行。", "warning")
                return redirect(m["new_url"])
            doc, error = create_document(doc_type)
            if error:
                flash(error, "warning")
                return redirect(m["new_url"])
            if request.form.get("save_action") == "post":
                execute_db("UPDATE pick_lists SET status='assigned' WHERE id=%s", (doc.get("id"),))
                return post_document(doc_type, doc.get("id"))
            if request.form.get("save_action") == "save_new":
                flash(f"{m['title']}已保存为草稿，可继续新增下一张。", "success")
                return redirect(m["new_url"])
            flash(f"{m['title']}已保存为草稿，请在详情页提交、过账或作废。", "success")
            return redirect(f"{m['detail_prefix']}/{doc.get('id')}")
        order = work_order(int(work_order_id)) if work_order_id else None
        return render_template(
            "production_pick_form.html",
            meta=m,
            work_orders=open_work_orders(doc_type),
            work_order_id=work_order_id,
            source_order=order,
            preview_lines=preview_lines(int(work_order_id), doc_type) if work_order_id else [],
            warehouses=warehouses(),
            locations=locations(),
            default_warehouse_id=(order or {}).get("warehouse_id"),
        )

    def edit_page(doc_type, doc_id):
        m = meta(doc_type)
        g.toolbar_extras = []
        doc = load_document(doc_type, doc_id)
        if not doc:
            flash(f"{m['title']}不存在。", "warning")
            return redirect(m["list_url"])
        if not can_edit_pick_document(doc):
            flash(f"{m['title']}当前状态不允许编辑。", "warning")
            return redirect(f"{m['detail_prefix']}/{doc_id}")
        if request.method == "POST":
            if request.form.get("save_action") == "unaudit":
                return unaudit_document(doc_type, doc_id)
            return update_document(doc_type, doc_id)
        order = work_order(doc.get("work_order_id"))
        return render_template(
            "production_pick_form.html",
            meta=m,
            edit_mode=True,
            form_action=f"{m['detail_prefix']}/{doc_id}/edit",
            doc=doc,
            work_orders=[],
            work_order_id=doc.get("work_order_id"),
            source_order=order,
            preview_lines=edit_lines(doc_type, doc),
            warehouses=warehouses(),
            locations=locations(),
            default_warehouse_id=doc.get("warehouse_id") or (order or {}).get("warehouse_id"),
        )

    def detail_page(doc_type, doc_id):
        m = meta(doc_type)
        ensure_schema()
        doc = load_document(doc_type, doc_id)
        if not doc:
            return render_template("simple_detail.html", title=m["title"], row=None, back_url=m["list_url"], labels={})
        return render_template("production_pick_detail.html", meta=m, doc=doc, lines=load_lines(doc_id), status_label=status_label)

    def copy_document(doc_type, doc_id):
        m = meta(doc_type)
        ensure_schema()
        doc = load_document(doc_type, doc_id)
        if not doc:
            flash(f"{m['title']}不存在，不能复制。", "warning")
            return redirect(m["list_url"])
        lines = load_lines(doc_id)
        if not lines:
            flash(f"原{m['title']}没有明细，不能复制。", "warning")
            return redirect(f"{m['detail_prefix']}/{doc_id}")
        new_no = next_doc_no(m["prefix"], "pick_lists", "doc_no")

        def operation(cursor):
            _query_one, _query_rows, tx_execute_db = transaction_callables(cursor)
            tx_execute_db(
                """
                INSERT INTO pick_lists
                    (doc_type, doc_no, pick_no, doc_date, pick_date, work_order_id, warehouse_id, location_id,
                     project_code, serial_no, status, created_by, remark)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'draft',%s,%s)
                """,
                (
                    doc_type,
                    new_no,
                    new_no,
                    datetime.now().date().isoformat(),
                    datetime.now().date().isoformat(),
                    doc.get("work_order_id"),
                    doc.get("warehouse_id"),
                    doc.get("location_id"),
                    doc.get("project_code"),
                    doc.get("serial_no"),
                    session.get("user_id") or doc.get("created_by"),
                    doc.get("remark"),
                ),
            )
            new_doc = _query_one("SELECT id FROM pick_lists WHERE doc_no=%s ORDER BY id DESC LIMIT 1", (new_no,))
            new_id = new_doc.get("id")
            for line in lines:
                tx_execute_db(
                    """
                    INSERT INTO pick_list_items
                        (pick_list_id, pick_id, wo_material_item_id, product_id, material_code, material_name,
                         material_spec, material_unit, quantity, posted_qty, unit_cost, warehouse_id, location_id,
                         lot_no, serial_no, source_line_no, line_project_code, line_serial_no, remark)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,0,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        new_id,
                        new_id,
                        line.get("wo_material_item_id"),
                        line.get("product_id"),
                        line.get("material_code"),
                        line.get("material_name"),
                        line.get("material_spec"),
                        line.get("material_unit"),
                        line.get("quantity"),
                        line.get("unit_cost") or 0,
                        line.get("warehouse_id"),
                        line.get("location_id"),
                        line.get("lot_no"),
                        line.get("serial_no"),
                        line.get("source_line_no"),
                        line.get("line_project_code"),
                        line.get("line_serial_no"),
                        line.get("remark"),
                    ),
                )
            return new_id

        new_id = run_in_transaction(operation)
        log_action(f"复制{m['title']}", f"{doc.get('doc_no') or doc.get('pick_no')} -> {new_no}")
        flash(f"已复制为新草稿单据 {new_no}，请检查后提交/审核。", "success")
        return redirect(f"{m['detail_prefix']}/{new_id}")

    def action(doc_type, doc_id, action_name):
        m = meta(doc_type)
        if action_name == "copy":
            return copy_document(doc_type, doc_id)
        if action_name == "submit":
            execute_db(
                "UPDATE pick_lists SET status='assigned' WHERE id=%s AND doc_type=%s AND COALESCE(status,'draft') IN ('draft','草稿','')",
                (doc_id, doc_type),
            )
            flash("单据已提交。下一步可在详情页执行过账。", "success")
        elif action_name == "submit_post":
            execute_db(
                "UPDATE pick_lists SET status='assigned' WHERE id=%s AND doc_type=%s AND COALESCE(status,'draft') IN ('draft','草稿','')",
                (doc_id, doc_type),
            )
            return post_document(doc_type, doc_id)
        elif action_name == "post":
            return post_document(doc_type, doc_id)
        elif action_name == "unaudit":
            return unaudit_document(doc_type, doc_id)
        elif action_name == "void":
            execute_db(
                "UPDATE pick_lists SET status='cancelled', voided_at=NOW() WHERE id=%s AND doc_type=%s AND COALESCE(status,'') IN ('draft','草稿','assigned','submitted','已提交','')",
                (doc_id, doc_type),
            )
            flash("单据已作废。", "success")
        else:
            flash("不支持的单据动作。", "warning")
        return redirect(f"{m['detail_prefix']}/{doc_id}")

    @app.get("/production-issues", endpoint="production_issue_list")
    @login_required
    def production_issue_list():
        return list_page("production_issue")

    @app.route("/production-issues/new", methods=["GET", "POST"], endpoint="production_issue_new")
    @login_required
    def production_issue_new():
        return form_page("production_issue")

    @app.get("/production-issues/<int:doc_id>", endpoint="production_issue_detail")
    @login_required
    def production_issue_detail(doc_id):
        return detail_page("production_issue", doc_id)

    @app.route("/production-issues/<int:doc_id>/edit", methods=["GET", "POST"], endpoint="production_issue_edit")
    @login_required
    def production_issue_edit(doc_id):
        return edit_page("production_issue", doc_id)

    @app.post("/production-issues/<int:doc_id>/<action_name>", endpoint="production_issue_action")
    @login_required
    def production_issue_action(doc_id, action_name):
        return action("production_issue", doc_id, action_name)

    @app.post("/production-issues/<int:doc_id>/copy", endpoint="production_issue_copy")
    @login_required
    def production_issue_copy(doc_id):
        return copy_document("production_issue", doc_id)

    @app.get("/production-returns", endpoint="production_return_list")
    @login_required
    def production_return_list():
        return list_page("production_return")

    @app.route("/production-returns/new", methods=["GET", "POST"], endpoint="production_return_new")
    @login_required
    def production_return_new():
        return form_page("production_return")

    @app.get("/production-returns/<int:doc_id>", endpoint="production_return_detail")
    @login_required
    def production_return_detail(doc_id):
        return detail_page("production_return", doc_id)

    @app.route("/production-returns/<int:doc_id>/edit", methods=["GET", "POST"], endpoint="production_return_edit")
    @login_required
    def production_return_edit(doc_id):
        return edit_page("production_return", doc_id)

    @app.post("/production-returns/<int:doc_id>/<action_name>", endpoint="production_return_action")
    @login_required
    def production_return_action(doc_id, action_name):
        return action("production_return", doc_id, action_name)

    @app.post("/production-returns/<int:doc_id>/copy", endpoint="production_return_copy")
    @login_required
    def production_return_copy(doc_id):
        return copy_document("production_return", doc_id)
