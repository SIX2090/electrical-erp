"""Purchase receipt routes: receipt list, receipt form, and warehouse inbound."""
from datetime import datetime
from decimal import Decimal

from flask import render_template

from .display_helpers import _looks_corrupt_text, _looks_non_business_text
from .document_print_routes import build_template_grid_for_document


def _operator_clean_rows(rows, *fields):
    clean = []
    for row in rows or []:
        if any(_looks_corrupt_text(row.get(field)) or _looks_non_business_text(row.get(field)) for field in fields):
            continue
        clean.append(row)
    return clean


def render_purchase_receipt_dashboard(
    query_one,
    query_rows,
    count_rows,
    qty_metric,
    money_metric,
    request_args,
):
    keyword = (request_args.get("keyword") or request_args.get("q") or "").strip()
    status = (request_args.get("status") or "").strip()
    qc_state = (request_args.get("qc_state") or "").strip()
    stock_state = (request_args.get("stock_state") or "").strip()
    where_parts = []
    params = []
    if keyword:
        where_parts.append(
            "(pr.receipt_no ILIKE %s OR po.order_no ILIKE %s OR s.name ILIKE %s OR pr.project_code ILIKE %s OR pr.cabinet_no ILIKE %s)"
        )
        params.extend([f"%{keyword}%"] * 5)
    if status:
        where_parts.append("COALESCE(pr.status, '') = %s")
        params.append(status)
    if qc_state == "pending":
        where_parts.append("COALESCE(qc.pending_count, 0) > 0")
    elif qc_state == "checked":
        where_parts.append("COALESCE(qc.checked_count, 0) > 0")
    if stock_state == "posted":
        where_parts.append("COALESCE(st.stock_txn_count, 0) > 0")
    elif stock_state == "unposted":
        where_parts.append("COALESCE(st.stock_txn_count, 0) = 0")
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    receivable_statuses = ("已审核", "已审批", "待收货", "部分收货")
    receivable_status_params = tuple(receivable_statuses)

    receipt_summary = query_one(
        """
        SELECT COUNT(DISTINCT pr.id) AS receipt_count,
               COALESCE(SUM(pri.quantity), 0) AS received_qty,
               COALESCE(SUM(pri.quantity * COALESCE(pri.unit_cost, 0)), 0) AS received_amount,
               COALESCE(SUM(pri.amount_with_tax), 0) AS amount_with_tax
        FROM purchase_receipts pr
        LEFT JOIN purchase_receipt_items pri ON pri.receipt_id=pr.id
        """
    ) or {}
    pending_summary = query_one(
        """
        SELECT COUNT(DISTINCT po.id) AS order_count,
               COALESCE(SUM(GREATEST(COALESCE(poi.quantity, 0) - COALESCE(poi.received_qty, 0), 0)), 0) AS pending_qty
        FROM purchase_orders po
        JOIN purchase_order_items poi ON poi.order_id=po.id
        WHERE COALESCE(po.status, '') IN %s
          AND GREATEST(COALESCE(poi.quantity, 0) - COALESCE(poi.received_qty, 0), 0) > 0
        """,
        (receivable_status_params,),
    ) or {}
    today_receipts = query_one("SELECT COUNT(*) AS value FROM purchase_receipts WHERE receipt_date=CURRENT_DATE")
    metrics = [
        {"label": "入库单数", "value": receipt_summary.get("receipt_count", 0), "hint": "已生成采购入库单"},
        {"label": "累计入库数量", "value": qty_metric(receipt_summary.get("received_qty", 0)), "hint": "入库明细数量合计"},
        {"label": "累计入库金额", "value": money_metric(receipt_summary.get("received_amount", 0)), "hint": "按入库成本汇总"},
        {
            "label": "可入库采购订单",
            "value": pending_summary.get("order_count", 0),
            "hint": f"未收数量 {qty_metric(pending_summary.get('pending_qty', 0))}",
        },
    ]
    statuses = query_rows(
        """
        SELECT status, COUNT(*) AS count
        FROM purchase_receipts
        WHERE COALESCE(status, '') <> ''
        GROUP BY status
        ORDER BY count DESC, status
        """
    )
    statuses = _operator_clean_rows(statuses, "status")
    receipts = query_rows(
        f"""
        SELECT pr.id, pr.receipt_no, pr.receipt_date, pr.status, pr.project_code, pr.cabinet_no,
               po.order_no, po.id AS order_id, s.name AS supplier_name, w.name AS warehouse_name,
               COALESCE(SUM(pri.quantity), 0) AS received_qty,
               COALESCE(SUM(pri.quantity * COALESCE(pri.unit_cost, 0)), 0) AS received_amount,
               COUNT(pri.id) AS item_count,
               COALESCE(qc.pending_count, 0) AS qc_pending_count,
               COALESCE(qc.checked_count, 0) AS qc_checked_count,
               COALESCE(st.stock_txn_count, 0) AS stock_txn_count
        FROM purchase_receipts pr
        LEFT JOIN purchase_orders po ON po.id=pr.order_id
        LEFT JOIN suppliers s ON s.id=po.supplier_id
        LEFT JOIN warehouses w ON w.id=pr.warehouse_id
        LEFT JOIN purchase_receipt_items pri ON pri.receipt_id=pr.id
        LEFT JOIN LATERAL (
            SELECT COUNT(*) FILTER (WHERE COALESCE(q.status, '') IN ('待检','待质检','pending','')) AS pending_count,
                   COUNT(*) FILTER (WHERE COALESCE(q.status, '') NOT IN ('待检','待质检','pending','')) AS checked_count
            FROM quality_inspection_records q
            WHERE q.source_document_type='purchase_receipt' AND q.source_document_id=pr.id
        ) qc ON TRUE
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS stock_txn_count
            FROM stock_transactions st
            WHERE st.reference_no=pr.receipt_no OR st.source_doc_no=pr.receipt_no
        ) st ON TRUE
        {where_sql}
        GROUP BY pr.id, po.order_no, po.id, s.name, w.name, qc.pending_count, qc.checked_count, st.stock_txn_count
        ORDER BY pr.id DESC
        LIMIT 80
        """,
        tuple(params),
    )
    receipts = _operator_clean_rows(receipts, "receipt_no", "order_no", "supplier_name", "project_code", "cabinet_no")
    for row in receipts:
        row["qc_state_label"] = "质检待检" if row.get("qc_pending_count") else ("质检已检" if row.get("qc_checked_count") else "未建质检")
        row["stock_state_label"] = "已入库记账" if row.get("stock_txn_count") else "未见库存流水"
    pending_orders = query_rows(
        """
        SELECT po.id, po.order_no, po.order_date, po.expected_date, po.status,
               po.project_code, po.cabinet_no, s.name AS supplier_name,
               COALESCE(SUM(poi.quantity), 0) AS ordered_qty,
               COALESCE(SUM(poi.received_qty), 0) AS received_qty,
               COALESCE(SUM(GREATEST(COALESCE(poi.quantity, 0) - COALESCE(poi.received_qty, 0), 0)), 0) AS pending_qty,
               COALESCE(SUM(GREATEST(COALESCE(poi.quantity, 0) - COALESCE(poi.received_qty, 0), 0) * COALESCE(poi.unit_price, 0)), 0) AS pending_amount
        FROM purchase_orders po
        JOIN purchase_order_items poi ON poi.order_id=po.id
        LEFT JOIN suppliers s ON s.id=po.supplier_id
        WHERE COALESCE(po.status, '') IN %s
        GROUP BY po.id, s.name
        HAVING COALESCE(SUM(GREATEST(COALESCE(poi.quantity, 0) - COALESCE(poi.received_qty, 0), 0)), 0) > 0
        ORDER BY po.expected_date NULLS LAST, po.id DESC
        LIMIT 40
        """,
        (receivable_status_params,),
    )
    pending_orders = _operator_clean_rows(pending_orders, "order_no", "supplier_name", "project_code", "cabinet_no", "status")
    recent_transactions = query_rows(
        """
        SELECT st.id, st.transaction_date, st.transaction_type, st.reference_no,
               p.code AS product_code, p.name AS product_name, st.quantity, st.unit_cost,
               st.lot_no, st.cabinet_no
        FROM stock_transactions st
        LEFT JOIN products p ON p.id=st.product_id
        WHERE st.reference_no IN (SELECT receipt_no FROM purchase_receipts ORDER BY id DESC LIMIT 200)
        ORDER BY st.id DESC
        LIMIT 30
        """
    )
    recent_transactions = _operator_clean_rows(recent_transactions, "reference_no", "product_code", "product_name", "cabinet_no")
    return render_template(
        "purchase_receipt_dashboard.html",
        title="采购入库单",
        subtitle="采购入库：从已审核采购订单生成采购入库单，入库后跟踪库存流水和应付。",
        metrics=metrics,
        receipts=receipts,
        pending_orders=pending_orders,
        recent_transactions=recent_transactions,
        statuses=statuses,
        filters={"keyword": keyword, "status": status},
        qc_state=qc_state,
        stock_state=stock_state,
        today_receipts=today_receipts.get("value", 0) if today_receipts else 0,
    )


def render_purchase_receipt_detail(
    receipt_id,
    query_one,
    query_rows,
    count_rows,
    as_decimal,
    receipt_display_amount,
    qty_metric,
    money_metric,
    document_attachments,
    document_activity_logs,
    back_url="/purchase_receipts",
):
    receipt = query_one(
        """
        SELECT pr.*, po.order_no, po.order_date, po.expected_date, po.total_amount AS order_amount,
               po.received_amount AS order_received_amount, po.status AS order_status,
               s.name AS supplier_name, s.contact_person, s.phone AS supplier_phone,
               w.name AS warehouse_name, u.username AS operator_name
        FROM purchase_receipts pr
        LEFT JOIN purchase_orders po ON po.id=pr.order_id
        LEFT JOIN suppliers s ON s.id=po.supplier_id
        LEFT JOIN warehouses w ON w.id=pr.warehouse_id
        LEFT JOIN users u ON u.id=pr.operator_id
        WHERE pr.id=%s
        """,
        (receipt_id,),
    )
    if not receipt:
        return render_template("simple_detail.html", title="采购入库详情", row=None, back_url=back_url, labels={})

    items = query_rows(
        """
        SELECT pri.*, p.code AS product_code, p.name AS product_name, p.specification,
               COALESCE(p.unit, '') AS product_unit,
               COALESCE(lw.name, hw.name) AS line_warehouse_name,
               l.code AS location_code, l.name AS location_name,
               poi.quantity AS ordered_qty, poi.received_qty AS order_received_qty, poi.unit_price AS order_unit_price
        FROM purchase_receipt_items pri
        LEFT JOIN purchase_receipts pr ON pr.id=pri.receipt_id
        LEFT JOIN products p ON p.id=pri.product_id
        LEFT JOIN warehouses lw ON lw.id=pri.warehouse_id
        LEFT JOIN warehouses hw ON hw.id=pr.warehouse_id
        LEFT JOIN locations l ON l.id=pri.location_id
        LEFT JOIN purchase_order_items poi ON poi.id=pri.order_item_id
        WHERE pri.receipt_id=%s
        ORDER BY pri.id
        """,
        (receipt_id,),
    )
    total_qty = sum((as_decimal(row.get("quantity")) for row in items), Decimal("0"))
    total_amount = sum((receipt_display_amount(row) for row in items), Decimal("0"))
    project_code = receipt.get("project_code")
    cabinet_no = receipt.get("cabinet_no")
    context = {
        "back_url": back_url,
        "receipt": receipt,
        "items": items,
        "metrics": [
            {"label": "入库数量", "value": qty_metric(total_qty), "hint": f"{len(items)} 行物料"},
            {"label": "入库金额", "value": money_metric(total_amount), "hint": "数量 x 单位成本"},
            {"label": "采购订单金额", "value": money_metric(receipt.get("order_amount")), "hint": receipt.get("order_no") or "-"},
            {"label": "今日入库", "value": count_rows("purchase_receipts", "receipt_date=CURRENT_DATE"), "hint": "当天采购入库单数量"},
        ],
        "stock_transactions": query_rows(
            """
            SELECT st.id, st.transaction_date, st.transaction_type, p.code AS product_code,
                   p.name AS product_name, p.specification, p.unit, st.quantity, st.unit_cost, st.reference_no,
                   st.lot_no, st.cabinet_no, st.location, w.name AS warehouse_name
            FROM stock_transactions st
            LEFT JOIN products p ON p.id=st.product_id
            LEFT JOIN warehouses w ON w.id=st.warehouse_id
            WHERE st.reference_no=%s OR st.source_doc_no=%s
            ORDER BY st.id DESC
            LIMIT 50
            """,
            (receipt.get("receipt_no"), receipt.get("receipt_no")),
        ),
        "payables": query_rows(
            """
            SELECT id, doc_no, doc_date, amount, paid_amount, balance, status
            FROM supplier_payables
            WHERE doc_id=%s OR doc_no=%s OR doc_no=%s
            ORDER BY id DESC
            LIMIT 20
            """,
            (receipt.get("order_id"), receipt.get("order_no"), receipt.get("receipt_no")),
        ),
        "same_project_receipts": query_rows(
            """
            SELECT id, receipt_no, receipt_date, status
            FROM purchase_receipts
            WHERE id<>%s AND ((%s IS NOT NULL AND project_code=%s) OR (%s IS NOT NULL AND cabinet_no=%s))
            ORDER BY id DESC
            LIMIT 20
            """,
            (receipt_id, project_code, project_code, cabinet_no, cabinet_no),
        ),
        "attachments": document_attachments("purchase_receipt", receipt_id),
        "activity_logs": document_activity_logs("purchase_receipt", receipt),
        "print_url": f"/purchase_receipts/{receipt_id}/print",
        "action_prefix": "/purchase_receipts",
    }
    return render_template("purchase_receipt_detail.html", **context)


def render_purchase_receipt_print(receipt_id, query_one, query_rows, as_decimal):
    receipt = query_one(
        """
        SELECT pr.*, po.order_no, s.name AS supplier_name, s.contact_person, s.phone AS supplier_phone,
               w.name AS warehouse_name
        FROM purchase_receipts pr
        LEFT JOIN purchase_orders po ON po.id=pr.order_id
        LEFT JOIN suppliers s ON s.id=po.supplier_id
        LEFT JOIN warehouses w ON w.id=pr.warehouse_id
        WHERE pr.id=%s
        """,
        (receipt_id,),
    )
    if not receipt:
        return render_template("simple_detail.html", title="采购入库打印", row=None, back_url="/purchase_receipts", labels={})
    rows = query_rows(
        """
        SELECT p.code AS product_code, p.name AS product_name, p.specification,
               COALESCE(p.unit, '') AS unit, pri.quantity, pri.unit_cost,
               (COALESCE(pri.quantity,0) * COALESCE(pri.unit_cost,0)) AS amount,
               pri.lot_no, COALESCE(lw.name, hw.name) AS warehouse_name,
               l.code AS location_code, l.name AS location_name
        FROM purchase_receipt_items pri
        LEFT JOIN purchase_receipts pr ON pr.id=pri.receipt_id
        LEFT JOIN products p ON p.id=pri.product_id
        LEFT JOIN warehouses lw ON lw.id=pri.warehouse_id
        LEFT JOIN warehouses hw ON hw.id=pr.warehouse_id
        LEFT JOIN locations l ON l.id=pri.location_id
        WHERE pri.receipt_id=%s
        ORDER BY pri.id
        """,
        (receipt_id,),
    )
    for row in rows:
        row["location_display"] = row.get("location_code") or row.get("location_name") or ""
    doc = {
        "title": "采购入库单",
        "subtitle": "机床 ERP 单据打印",
        "number": receipt.get("receipt_no"),
        "number_label": "入库单号",
        "date": receipt.get("receipt_date"),
        "date_label": "入库日期",
        "status_label": receipt.get("status") or "未定",
        "info": [
            ("供应商", receipt.get("supplier_name")),
            ("联系人", receipt.get("contact_person")),
            ("电话", receipt.get("supplier_phone")),
            ("来源采购订单", receipt.get("order_no")),
            ("仓库", receipt.get("warehouse_name")),
            ("项目号", receipt.get("project_code")),
            ("柜号", receipt.get("cabinet_no")),
        ],
        "columns": [
            ("product_code", "物料编码", ""),
            ("product_name", "物料名称", ""),
            ("specification", "规格", ""),
            ("unit", "单位", "center"),
            ("quantity", "数量", "right"),
            ("unit_cost", "单位成本", "right money"),
            ("amount", "金额", "right money"),
            ("warehouse_name", "收货仓库", ""),
            ("location_display", "库位", ""),
            ("lot_no", "批号", ""),
        ],
        "rows": rows,
        "total_quantity": sum((as_decimal(row.get("quantity")) for row in rows), Decimal("0")),
        "total_amount": sum((as_decimal(row.get("amount")) for row in rows), Decimal("0")),
        "remark": receipt.get("remark"),
        "signatures": ["制单", "收货", "质检", "仓库", "财务"],
        "print_time": datetime.now(),
        "back_url": f"/purchase_receipts/{receipt_id}",
    }
    doc["partner_name"] = receipt.get("supplier_name")
    doc["contact_person"] = receipt.get("contact_person")
    doc["partner_phone"] = receipt.get("supplier_phone")
    doc["project_code"] = receipt.get("project_code")
    doc["cabinet_no"] = receipt.get("cabinet_no")
    doc["warehouse_name"] = receipt.get("warehouse_name")
    template_grid = build_template_grid_for_document("purchase_receipt", doc, query_one)
    return render_template("document_print.html", doc=doc, template_grid=template_grid)
