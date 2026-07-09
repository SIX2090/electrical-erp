"""Project routes: project master, project cost, and project delivery workbench."""
from datetime import date, datetime
from decimal import Decimal
import csv
import io
from urllib.parse import urlencode

from flask import Response, jsonify, redirect, render_template, request
from routes.read_query_helpers import _export_format, _xlsx_response


def _project_delivery_state(delivery_date, today):
    if not delivery_date:
        return "未定交期", "secondary"
    if delivery_date < today:
        return "已逾期", "danger"
    days = (delivery_date - today).days
    if days <= 7:
        return f"{days}天内到期", "warning"
    return f"{days}天后到期", "success"


def _project_csv_response(rows):
    if _export_format() == "xlsx":
        headers = [
            ("order_no", "销售订单"),
            ("customer_name", "客户"),
            ("project_code", "项目号"),
            ("serial_no", "机号"),
            ("delivery_date", "交期"),
            ("delivery_state", "交期状态"),
            ("status", "销售状态"),
            ("acceptance_status", "验收状态"),
            ("acceptance_gaps", "验收缺口"),
            ("acceptance_owner_roles", "责任归口"),
            ("acceptance_primary_gap", "首要处理项"),
            ("acceptance_primary_owner", "首要责任归口"),
            ("next_action", "下一步"),
            ("owner_role", "责任"),
            ("blocked_reason", "阻塞原因"),
        ]
        output_rows = [[label for _key, label in headers]]
        output_rows.extend([[row.get(key, "") for key, _label in headers] for row in rows])
        return _xlsx_response(output_rows, "project_acceptance")
    output = io.StringIO()
    writer = csv.writer(output)
    headers = [
        ("order_no", "销售订单"),
        ("customer_name", "客户"),
        ("project_code", "项目号"),
        ("serial_no", "机号"),
        ("delivery_date", "交期"),
        ("delivery_state", "交期状态"),
        ("status", "销售状态"),
        ("acceptance_status", "验收状态"),
        ("acceptance_gaps", "验收缺口"),
        ("acceptance_owner_roles", "责任归口"),
        ("acceptance_primary_gap", "首要处理项"),
        ("acceptance_primary_owner", "首要责任归口"),
        ("next_action", "下一步"),
        ("owner_role", "责任"),
        ("blocked_reason", "阻塞原因"),
    ]
    writer.writerow([label for _, label in headers])
    for row in rows:
        writer.writerow([row.get(key, "") for key, _ in headers])
    return Response(
        output.getvalue().encode("utf-8-sig"),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=project_acceptance.csv"},
    )


def _acceptance_owner_roles(gaps):
    owner_by_gap = {
        "项目/机号": "销售/项目",
        "缺料": "计划/采购",
        "采购未到": "采购",
        "未完工单": "生产",
        "未发货": "仓库/销售",
        "服务档案": "售后",
        "应收": "财务/销售",
        "应付": "采购/财务",
        "成本": "财务/成本",
    }
    owners = []
    for gap in gaps:
        owner = owner_by_gap.get(gap)
        if owner and owner not in owners:
            owners.append(owner)
    return "、".join(owners) if owners else "无"


def _acceptance_primary_gap(gaps):
    if not gaps:
        return "无", "无"
    primary_gap = gaps[0]
    return primary_gap, _acceptance_owner_roles([primary_gap])


def _project_next_action(row, as_decimal):
    if not row.get("project_code") or not row.get("serial_no"):
        return "补齐项目号/机号", "销售/项目", "主线追溯字段不完整"
    if row.get("shortage_lines"):
        return "处理缺料并生成采购申请", "采购/计划", "BOM/MRP缺料"
    if as_decimal(row.get("pending_purchase_qty")) > 0:
        return "跟催采购到货", "采购", "采购未到"
    if row.get("open_work_order_count"):
        return "推进工单领料、完工和终检", "生产", "生产未完"
    if not row.get("shipment_count"):
        return "按销售订单生成发货单", "仓库/销售", "未发货"
    if as_decimal(row.get("receivable_balance")) > 0:
        return "跟进客户回款", "财务/销售", "应收未清"
    if row.get("service_order_count"):
        return "跟进售后服务闭环", "售后", "售后处理中"
    return "维护项目档案并准备关闭", "项目/销售", "暂无阻塞"


def _build_project_diagnostics(order, context, finance_summary):
    diagnostics = []
    if not order:
        return diagnostics
    if not order.get("project_code") or not order.get("serial_no"):
        diagnostics.append({"level": "danger", "label": "追溯缺口", "text": "销售项目缺项目号或机号，后续采购、生产、库存、售后无法稳定归集。", "owner": "销售/项目"})
    kit_summary = context.get("kit_summary") or {}
    if kit_summary.get("shortage_count"):
        diagnostics.append({"level": "danger", "label": "齐套缺料", "text": f"仍有 {kit_summary.get('shortage_count')} 个物料缺口，优先生成采购申请或处理替代料。", "owner": "计划/采购"})
    if context.get("purchase_orders") and any((row.get("status") or "") not in {"已收货", "已关闭", "已作废"} for row in context.get("purchase_orders")):
        diagnostics.append({"level": "warning", "label": "采购未闭环", "text": "存在未完成采购单，需要跟催到货并完成收货入库。", "owner": "采购"})
    if context.get("work_orders") and any((row.get("status") or "") not in {"已完工", "已关闭", "已作废"} for row in context.get("work_orders")):
        diagnostics.append({"level": "warning", "label": "生产未完", "text": "存在未完工单，需要确认领料、装配、调试和终检状态。", "owner": "生产"})
    if not context.get("shipments"):
        diagnostics.append({"level": "info", "label": "尚未发货", "text": "项目还没有发货记录，完工后需要生成销售发货并更新服务档案。", "owner": "仓库/销售"})
    if as_decimal_safe(finance_summary.get("receivable_balance")) > 0:
        diagnostics.append({"level": "warning", "label": "应收未清", "text": "存在未清应收，需要进入应收模块跟进回款。", "owner": "财务/销售"})
    if context.get("service_rmas") and any((row.get("status") or "") not in {"已关闭", "已完成", "closed", "completed"} for row in context.get("service_rmas")):
        diagnostics.append({"level": "warning", "label": "RMA未闭环", "text": "存在未关闭 RMA，需要完成诊断、索赔、追回或关闭。", "owner": "售后/质量"})
    if not diagnostics:
        diagnostics.append({"level": "success", "label": "主线正常", "text": "当前项目没有明显阻塞，继续维护发货、回款和售后资料。", "owner": "项目"})
    return diagnostics


def as_decimal_safe(value):
    try:
        return Decimal(str(value if value is not None else 0))
    except (TypeError, ValueError):
        return Decimal("0")


def _json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _project_axis_order(query_one, keyword=None, project_code=None, serial_no=None, order_no=None):
    exact_value = (serial_no or project_code or order_no or keyword or "").strip()
    if not exact_value:
        return None
    like_value = f"%{exact_value}%"
    return query_one(
        """
        SELECT so.id, so.order_no, so.order_date, so.delivery_date,
               so.project_code, so.serial_no, so.status, so.total_amount,
               so.shipped_amount, so.cost_object_id, c.name AS customer_name
        FROM sales_orders so
        LEFT JOIN customers c ON c.id=so.customer_id
        WHERE so.order_no ILIKE %s
           OR so.project_code ILIKE %s
           OR so.serial_no ILIKE %s
           OR c.name ILIKE %s
        ORDER BY CASE
            WHEN %s <> '' AND so.serial_no=%s THEN 0
            WHEN %s <> '' AND so.project_code=%s THEN 1
            WHEN %s <> '' AND so.order_no=%s THEN 2
            ELSE 3
        END, so.id DESC
        LIMIT 1
        """,
        (
            like_value,
            like_value,
            like_value,
            like_value,
            serial_no or "",
            serial_no or "",
            project_code or "",
            project_code or "",
            order_no or "",
            order_no or "",
        ),
    )


def _project_order_by_id(query_one, order_id):
    return query_one(
        """
        SELECT so.id, so.order_no, so.order_date, so.delivery_date,
               so.project_code, so.serial_no, so.status, so.total_amount,
               so.shipped_amount, so.cost_object_id, c.name AS customer_name
        FROM sales_orders so
        LEFT JOIN customers c ON c.id=so.customer_id
        WHERE so.id=%s
        """,
        (order_id,),
    )


def _project_axis_search_rows(query_rows, keyword, limit):
    keyword = (keyword or "").strip()
    if not keyword:
        return []
    like_value = f"%{keyword}%"
    return query_rows(
        """
        SELECT so.id, so.order_no, so.order_date, so.delivery_date,
               so.project_code, so.serial_no, so.status, so.total_amount,
               so.shipped_amount, so.cost_object_id, c.name AS customer_name
        FROM sales_orders so
        LEFT JOIN customers c ON c.id=so.customer_id
        WHERE so.order_no ILIKE %s
           OR so.project_code ILIKE %s
           OR so.serial_no ILIKE %s
           OR c.name ILIKE %s
        ORDER BY CASE
            WHEN so.serial_no=%s THEN 0
            WHEN so.project_code=%s THEN 1
            WHEN so.order_no=%s THEN 2
            ELSE 3
        END, so.id DESC
        LIMIT %s
        """,
        (like_value, like_value, like_value, like_value, keyword, keyword, keyword, limit),
    )


def _project_axis_counts(query_one, order):
    if not order:
        return {}
    order_id = order.get("id")
    project_code = order.get("project_code")
    serial_no = order.get("serial_no")
    cost_object_id = order.get("cost_object_id")
    return query_one(
        """
        SELECT
          (
            SELECT COUNT(*)
            FROM purchase_orders po
            WHERE (%s IS NOT NULL AND po.cost_object_id=%s)
               OR (%s IS NOT NULL AND po.project_code=%s)
               OR (%s IS NOT NULL AND po.serial_no=%s)
          ) AS purchase_order_count,
          (
            SELECT COALESCE(SUM(GREATEST(COALESCE(poi.quantity, 0)-COALESCE(poi.received_qty, 0), 0)), 0)
            FROM purchase_orders po
            LEFT JOIN purchase_order_items poi ON poi.order_id=po.id
            WHERE (%s IS NOT NULL AND po.cost_object_id=%s)
               OR (%s IS NOT NULL AND po.project_code=%s)
               OR (%s IS NOT NULL AND po.serial_no=%s)
          ) AS pending_purchase_qty,
          (
            SELECT COUNT(*)
            FROM subcontract_orders sc
            WHERE (%s IS NOT NULL AND sc.cost_object_id=%s)
               OR (%s IS NOT NULL AND sc.project_code=%s)
               OR (%s IS NOT NULL AND sc.serial_no=%s)
          ) AS subcontract_order_count,
          (
            SELECT COUNT(*)
            FROM work_orders wo
            WHERE (%s IS NOT NULL AND wo.cost_object_id=%s)
               OR (%s IS NOT NULL AND wo.project_code=%s)
               OR (%s IS NOT NULL AND wo.serial_no=%s)
          ) AS work_order_count,
          (
            SELECT COUNT(*)
            FROM work_orders wo
            WHERE (
                (%s IS NOT NULL AND wo.cost_object_id=%s)
                OR (%s IS NOT NULL AND wo.project_code=%s)
                OR (%s IS NOT NULL AND wo.serial_no=%s)
              )
              AND COALESCE(wo.status, '') NOT IN ('closed','completed','void','cancelled','已完工','已关闭','已作废','已完成')
          ) AS open_work_order_count,
          (
            SELECT COUNT(*)
            FROM sales_shipments ss
            WHERE ss.order_id=%s
               OR (%s IS NOT NULL AND ss.project_code=%s)
               OR (%s IS NOT NULL AND ss.serial_no=%s)
          ) AS shipment_count,
          (
            SELECT COUNT(*)
            FROM machine_service_cards scard
            WHERE scard.sales_order_id=%s
               OR (%s IS NOT NULL AND scard.cost_object_id=%s)
               OR (%s IS NOT NULL AND scard.project_code=%s)
               OR (%s IS NOT NULL AND scard.serial_no=%s)
          ) AS service_card_count,
          (
            SELECT COUNT(*)
            FROM machine_service_orders mso
            WHERE mso.sales_order_id=%s
               OR (%s IS NOT NULL AND mso.cost_object_id=%s)
               OR (%s IS NOT NULL AND mso.project_code=%s)
               OR (%s IS NOT NULL AND mso.serial_no=%s)
          ) AS service_order_count,
          (
            SELECT COUNT(*)
            FROM stock_transactions st
            WHERE (%s IS NOT NULL AND st.reference_no=%s)
               OR (%s IS NOT NULL AND st.project_code=%s)
               OR (%s IS NOT NULL AND st.serial_no=%s)
          ) AS stock_transaction_count
        """,
        (
            cost_object_id,
            cost_object_id,
            project_code,
            project_code,
            serial_no,
            serial_no,
            cost_object_id,
            cost_object_id,
            project_code,
            project_code,
            serial_no,
            serial_no,
            cost_object_id,
            cost_object_id,
            project_code,
            project_code,
            serial_no,
            serial_no,
            cost_object_id,
            cost_object_id,
            project_code,
            project_code,
            serial_no,
            serial_no,
            cost_object_id,
            cost_object_id,
            project_code,
            project_code,
            serial_no,
            serial_no,
            order_id,
            project_code,
            project_code,
            serial_no,
            serial_no,
            order_id,
            cost_object_id,
            cost_object_id,
            project_code,
            project_code,
            serial_no,
            serial_no,
            order_id,
            cost_object_id,
            cost_object_id,
            project_code,
            project_code,
            serial_no,
            serial_no,
            order.get("order_no"),
            order.get("order_no"),
            project_code,
            project_code,
            serial_no,
            serial_no,
        ),
    ) or {}


def _append_project_events(events, rows, *, event_type, number_key, date_key, url_prefix, amount_key=None, quantity_key=None):
    for row in rows or []:
        events.append(
            {
                "event_type": event_type,
                "source_id": row.get("id"),
                "source_no": row.get(number_key),
                "event_date": row.get(date_key),
                "status": row.get("status"),
                "amount": row.get(amount_key) if amount_key else None,
                "quantity": row.get(quantity_key) if quantity_key else None,
                "detail_url": f"{url_prefix}/{row.get('id')}" if url_prefix and row.get("id") is not None else None,
            }
        )


def _project_event_sort_value(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    return datetime.min


def _project_axis_events(query_rows, order, limit=80):
    if not order:
        return []
    order_id = order.get("id")
    project_code = order.get("project_code")
    serial_no = order.get("serial_no")
    cost_object_id = order.get("cost_object_id")
    events = []
    _append_project_events(
        events,
        [order],
        event_type="sales_order",
        number_key="order_no",
        date_key="order_date",
        url_prefix="/projects",
        amount_key="total_amount",
    )
    _append_project_events(
        events,
        query_rows(
            """
            SELECT id, confirm_no, confirm_date, status
            FROM engineering_technical_confirmations
            WHERE sales_order_id=%s
               OR (%s IS NOT NULL AND project_code=%s)
               OR (%s IS NOT NULL AND serial_no=%s)
            ORDER BY confirm_date DESC NULLS LAST, id DESC
            LIMIT 40
            """,
            (order_id, project_code, project_code, serial_no, serial_no),
        ),
        event_type="technical_confirmation",
        number_key="confirm_no",
        date_key="confirm_date",
        url_prefix="/engineering/technical-confirmations",
    )
    _append_project_events(
        events,
        query_rows(
            """
            SELECT DISTINCT pr.id, pr.req_no, pr.req_date, pr.status
            FROM purchase_requisitions pr
            LEFT JOIN purchase_requisition_items pri ON pri.req_id=pr.id
            WHERE (%s IS NOT NULL AND (pr.project_code=%s OR pri.project_code=%s))
               OR (%s IS NOT NULL AND (pr.serial_no=%s OR pri.serial_no=%s))
            ORDER BY pr.req_date DESC NULLS LAST, pr.id DESC
            LIMIT 40
            """,
            (project_code, project_code, project_code, serial_no, serial_no, serial_no),
        ),
        event_type="purchase_request",
        number_key="req_no",
        date_key="req_date",
        url_prefix="/purchase_request",
    )
    _append_project_events(
        events,
        query_rows(
            """
            SELECT id, order_no, order_date, status, total_amount
            FROM purchase_orders
            WHERE (%s IS NOT NULL AND cost_object_id=%s)
               OR (%s IS NOT NULL AND project_code=%s)
               OR (%s IS NOT NULL AND serial_no=%s)
            ORDER BY order_date DESC NULLS LAST, id DESC
            LIMIT 40
            """,
            (cost_object_id, cost_object_id, project_code, project_code, serial_no, serial_no),
        ),
        event_type="purchase_order",
        number_key="order_no",
        date_key="order_date",
        url_prefix="/purchase_order",
        amount_key="total_amount",
    )
    _append_project_events(
        events,
        query_rows(
            """
            SELECT DISTINCT pr.id, pr.receipt_no, pr.receipt_date, pr.status,
                   COALESCE(SUM(pri.quantity), 0) AS received_qty,
                   COALESCE(SUM(pri.quantity * COALESCE(pri.unit_cost, 0)), 0) AS received_amount
            FROM purchase_receipts pr
            LEFT JOIN purchase_receipt_items pri ON pri.receipt_id=pr.id
            LEFT JOIN purchase_orders po ON po.id=pr.order_id
            WHERE (%s IS NOT NULL AND (pr.cost_object_id=%s OR po.cost_object_id=%s))
               OR (%s IS NOT NULL AND (pr.project_code=%s OR po.project_code=%s))
               OR (%s IS NOT NULL AND (pr.serial_no=%s OR po.serial_no=%s))
            GROUP BY pr.id
            ORDER BY pr.receipt_date DESC NULLS LAST, pr.id DESC
            LIMIT 40
            """,
            (
                cost_object_id,
                cost_object_id,
                cost_object_id,
                project_code,
                project_code,
                project_code,
                serial_no,
                serial_no,
                serial_no,
            ),
        ),
        event_type="purchase_receipt",
        number_key="receipt_no",
        date_key="receipt_date",
        url_prefix="/purchase_receipts",
        amount_key="received_amount",
        quantity_key="received_qty",
    )
    _append_project_events(
        events,
        query_rows(
            """
            SELECT DISTINCT sp.id, sp.doc_no, sp.doc_date, sp.status, sp.balance AS amount
            FROM supplier_payables sp
            LEFT JOIN purchase_orders po_ap
              ON sp.doc_type='purchase_order' AND (po_ap.id=sp.doc_id OR po_ap.order_no=sp.doc_no)
            LEFT JOIN subcontract_orders sc_ap
              ON sp.doc_type='subcontract_order' AND (sc_ap.id=sp.doc_id OR sc_ap.order_no=sp.doc_no)
            WHERE (%s IS NOT NULL AND (
                    sp.cost_object_id=%s OR po_ap.cost_object_id=%s OR sc_ap.cost_object_id=%s
                  ))
               OR (%s IS NOT NULL AND (
                    sp.project_code=%s OR po_ap.project_code=%s OR sc_ap.project_code=%s
                  ))
               OR (%s IS NOT NULL AND (
                    sp.serial_no=%s OR po_ap.serial_no=%s OR sc_ap.serial_no=%s
                  ))
            ORDER BY sp.doc_date DESC NULLS LAST, sp.id DESC
            LIMIT 40
            """,
            (
                cost_object_id,
                cost_object_id,
                cost_object_id,
                cost_object_id,
                project_code,
                project_code,
                project_code,
                project_code,
                serial_no,
                serial_no,
                serial_no,
                serial_no,
            ),
        ),
        event_type="supplier_payable",
        number_key="doc_no",
        date_key="doc_date",
        url_prefix="/payables",
        amount_key="amount",
    )
    _append_project_events(
        events,
        query_rows(
            """
            SELECT id, order_no, order_date, status, total_amount, quantity
            FROM subcontract_orders
            WHERE (%s IS NOT NULL AND cost_object_id=%s)
               OR (%s IS NOT NULL AND project_code=%s)
               OR (%s IS NOT NULL AND serial_no=%s)
            ORDER BY order_date DESC NULLS LAST, id DESC
            LIMIT 40
            """,
            (cost_object_id, cost_object_id, project_code, project_code, serial_no, serial_no),
        ),
        event_type="subcontract_order",
        number_key="order_no",
        date_key="order_date",
        url_prefix="/subcontract",
        amount_key="total_amount",
        quantity_key="quantity",
    )
    _append_project_events(
        events,
        query_rows(
            """
            SELECT DISTINCT sio.id, sio.issue_no, sio.date AS issue_date, sio.status,
                   sio.total_quantity
            FROM subcontract_issue_orders sio
            LEFT JOIN subcontract_orders sc ON sc.id=sio.subcontract_order_id
            WHERE (%s IS NOT NULL AND sc.cost_object_id=%s)
               OR (%s IS NOT NULL AND (sc.project_code=%s OR EXISTS (
                    SELECT 1 FROM subcontract_issue_lines sil
                    WHERE sil.issue_id=sio.id AND sil.project_code=%s
               )))
               OR (%s IS NOT NULL AND (sc.serial_no=%s OR EXISTS (
                    SELECT 1 FROM subcontract_issue_lines sil
                    WHERE sil.issue_id=sio.id AND sil.serial_no=%s
               )))
            ORDER BY sio.date DESC NULLS LAST, sio.id DESC
            LIMIT 40
            """,
            (
                cost_object_id,
                cost_object_id,
                project_code,
                project_code,
                project_code,
                serial_no,
                serial_no,
                serial_no,
            ),
        ),
        event_type="subcontract_issue",
        number_key="issue_no",
        date_key="issue_date",
        url_prefix="/subcontract_issue",
        quantity_key="total_quantity",
    )
    _append_project_events(
        events,
        query_rows(
            """
            SELECT DISTINCT sro.id, sro.receive_no, sro.date AS receive_date, sro.status,
                   sro.total_quantity
            FROM subcontract_receive_orders sro
            LEFT JOIN subcontract_orders sc ON sc.id=sro.subcontract_order_id
            WHERE (%s IS NOT NULL AND sc.cost_object_id=%s)
               OR (%s IS NOT NULL AND (sc.project_code=%s OR EXISTS (
                    SELECT 1 FROM subcontract_receive_lines srl
                    WHERE srl.receive_id=sro.id AND srl.project_code=%s
               )))
               OR (%s IS NOT NULL AND (sc.serial_no=%s OR EXISTS (
                    SELECT 1 FROM subcontract_receive_lines srl
                    WHERE srl.receive_id=sro.id AND srl.serial_no=%s
               )))
            ORDER BY sro.date DESC NULLS LAST, sro.id DESC
            LIMIT 40
            """,
            (
                cost_object_id,
                cost_object_id,
                project_code,
                project_code,
                project_code,
                serial_no,
                serial_no,
                serial_no,
            ),
        ),
        event_type="subcontract_receive",
        number_key="receive_no",
        date_key="receive_date",
        url_prefix="/subcontract_receive",
        quantity_key="total_quantity",
    )
    _append_project_events(
        events,
        query_rows(
            """
            SELECT id, wo_no, wo_date, status, quantity
            FROM work_orders
            WHERE (%s IS NOT NULL AND cost_object_id=%s)
               OR (%s IS NOT NULL AND project_code=%s)
               OR (%s IS NOT NULL AND serial_no=%s)
            ORDER BY wo_date DESC NULLS LAST, id DESC
            LIMIT 40
            """,
            (cost_object_id, cost_object_id, project_code, project_code, serial_no, serial_no),
        ),
        event_type="work_order",
        number_key="wo_no",
        date_key="wo_date",
        url_prefix="/work-orders",
        quantity_key="quantity",
    )
    _append_project_events(
        events,
        query_rows(
            """
            SELECT id, doc_no, doc_date, status
            FROM pick_lists
            WHERE doc_type='production_issue'
              AND (
                   (%s IS NOT NULL AND project_code=%s)
                   OR (%s IS NOT NULL AND serial_no=%s)
                   OR work_order_id IN (
                       SELECT id FROM work_orders wo
                       WHERE (%s IS NOT NULL AND wo.cost_object_id=%s)
                          OR (%s IS NOT NULL AND wo.project_code=%s)
                          OR (%s IS NOT NULL AND wo.serial_no=%s)
                   )
              )
            ORDER BY doc_date DESC NULLS LAST, id DESC
            LIMIT 40
            """,
            (
                project_code,
                project_code,
                serial_no,
                serial_no,
                cost_object_id,
                cost_object_id,
                project_code,
                project_code,
                serial_no,
                serial_no,
            ),
        ),
        event_type="production_issue",
        number_key="doc_no",
        date_key="doc_date",
        url_prefix="/production-issues",
    )
    _append_project_events(
        events,
        query_rows(
            """
            SELECT id, doc_no, doc_date, status
            FROM pick_lists
            WHERE doc_type='production_return'
              AND (
                   (%s IS NOT NULL AND project_code=%s)
                   OR (%s IS NOT NULL AND serial_no=%s)
                   OR work_order_id IN (
                       SELECT id FROM work_orders wo
                       WHERE (%s IS NOT NULL AND wo.cost_object_id=%s)
                          OR (%s IS NOT NULL AND wo.project_code=%s)
                          OR (%s IS NOT NULL AND wo.serial_no=%s)
                   )
              )
            ORDER BY doc_date DESC NULLS LAST, id DESC
            LIMIT 40
            """,
            (
                project_code,
                project_code,
                serial_no,
                serial_no,
                cost_object_id,
                cost_object_id,
                project_code,
                project_code,
                serial_no,
                serial_no,
            ),
        ),
        event_type="production_return",
        number_key="doc_no",
        date_key="doc_date",
        url_prefix="/production-returns",
    )
    _append_project_events(
        events,
        query_rows(
            """
            SELECT pc.id, pc.completion_no, pc.completion_date, pc.status,
                   pc.quantity, pc.quantity * COALESCE(pc.unit_cost, 0) AS amount
            FROM production_completion_orders pc
            LEFT JOIN work_orders wo ON wo.id=pc.work_order_id
            WHERE (%s IS NOT NULL AND wo.cost_object_id=%s)
               OR (%s IS NOT NULL AND (pc.project_code=%s OR wo.project_code=%s))
               OR (%s IS NOT NULL AND (pc.serial_no=%s OR wo.serial_no=%s))
            ORDER BY pc.completion_date DESC NULLS LAST, pc.id DESC
            LIMIT 40
            """,
            (
                cost_object_id,
                cost_object_id,
                project_code,
                project_code,
                project_code,
                serial_no,
                serial_no,
                serial_no,
            ),
        ),
        event_type="production_completion",
        number_key="completion_no",
        date_key="completion_date",
        url_prefix="/production-completions",
        amount_key="amount",
        quantity_key="quantity",
    )
    _append_project_events(
        events,
        query_rows(
            """
            SELECT qi.id, qi.inspection_no, qi.inspection_date, qi.status,
                   COALESCE(qi.sample_size, 0) AS sample_size
            FROM quality_inspection_records qi
            LEFT JOIN work_orders wo
              ON qi.source_document_type='work_order' AND wo.id=qi.source_document_id
            WHERE (%s IS NOT NULL AND (qi.cost_object_id=%s OR wo.cost_object_id=%s))
               OR (%s IS NOT NULL AND (qi.project_code=%s OR wo.project_code=%s))
               OR (%s IS NOT NULL AND (qi.serial_no=%s OR wo.serial_no=%s))
            ORDER BY qi.inspection_date DESC NULLS LAST, qi.id DESC
            LIMIT 40
            """,
            (
                cost_object_id,
                cost_object_id,
                cost_object_id,
                project_code,
                project_code,
                project_code,
                serial_no,
                serial_no,
                serial_no,
            ),
        ),
        event_type="quality_inspection",
        number_key="inspection_no",
        date_key="inspection_date",
        url_prefix="/production-enhance/quality-inspections",
        quantity_key="sample_size",
    )
    _append_project_events(
        events,
        query_rows(
            """
            SELECT wcl.work_order_id AS id, COALESCE(wcl.source_no, wo.wo_no) AS source_no,
                   wcl.created_at::date AS cost_date, wcl.source_type AS status,
                   wcl.amount, wcl.quantity
            FROM work_order_cost_lines wcl
            LEFT JOIN work_orders wo ON wo.id=wcl.work_order_id
            WHERE (%s IS NOT NULL AND wcl.cost_object_id=%s)
               OR (%s IS NOT NULL AND wo.project_code=%s)
               OR (%s IS NOT NULL AND wo.serial_no=%s)
            ORDER BY wcl.created_at DESC NULLS LAST, wcl.id DESC
            LIMIT 60
            """,
            (cost_object_id, cost_object_id, project_code, project_code, serial_no, serial_no),
        ),
        event_type="work_order_cost",
        number_key="source_no",
        date_key="cost_date",
        url_prefix="/work-orders",
        amount_key="amount",
        quantity_key="quantity",
    )
    _append_project_events(
        events,
        query_rows(
            """
            SELECT id, shipment_no, shipment_date, status, shipped_amount
            FROM sales_shipments
            WHERE order_id=%s
               OR (%s IS NOT NULL AND project_code=%s)
               OR (%s IS NOT NULL AND serial_no=%s)
            ORDER BY shipment_date DESC NULLS LAST, id DESC
            LIMIT 40
            """,
            (order_id, project_code, project_code, serial_no, serial_no),
        ),
        event_type="sales_shipment",
        number_key="shipment_no",
        date_key="shipment_date",
        url_prefix="/shipments",
        amount_key="shipped_amount",
    )
    _append_project_events(
        events,
        query_rows(
            """
            SELECT id, source_no, due_date, status, balance AS amount
            FROM customer_receivables
            WHERE source_id=%s
               OR (%s IS NOT NULL AND cost_object_id=%s)
               OR (%s IS NOT NULL AND project_code=%s)
               OR (%s IS NOT NULL AND serial_no=%s)
            ORDER BY due_date DESC NULLS LAST, id DESC
            LIMIT 40
            """,
            (order_id, cost_object_id, cost_object_id, project_code, project_code, serial_no, serial_no),
        ),
        event_type="customer_receivable",
        number_key="source_no",
        date_key="due_date",
        url_prefix="/receivables",
        amount_key="amount",
    )
    _append_project_events(
        events,
        query_rows(
            """
            SELECT id, serial_no AS card_no, install_date, status
            FROM machine_service_cards
            WHERE sales_order_id=%s
               OR (%s IS NOT NULL AND cost_object_id=%s)
               OR (%s IS NOT NULL AND project_code=%s)
               OR (%s IS NOT NULL AND serial_no=%s)
            ORDER BY install_date DESC NULLS LAST, id DESC
            LIMIT 40
            """,
            (order_id, cost_object_id, cost_object_id, project_code, project_code, serial_no, serial_no),
        ),
        event_type="service_card",
        number_key="card_no",
        date_key="install_date",
        url_prefix="/service-cards",
    )
    _append_project_events(
        events,
        query_rows(
            """
            SELECT id, COALESCE(NULLIF(acceptance_no, ''), item_name, id::text) AS acceptance_no, check_date, result AS status
            FROM machine_service_acceptance_checks
            WHERE sales_order_id=%s
               OR (%s IS NOT NULL AND cost_object_id=%s)
               OR (%s IS NOT NULL AND project_code=%s)
               OR (%s IS NOT NULL AND serial_no=%s)
            ORDER BY check_date DESC NULLS LAST, id DESC
            LIMIT 40
            """,
            (order_id, cost_object_id, cost_object_id, project_code, project_code, serial_no, serial_no),
        ),
        event_type="service_acceptance",
        number_key="acceptance_no",
        date_key="check_date",
        url_prefix="/service-acceptance",
    )
    _append_project_events(
        events,
        query_rows(
            """
            SELECT id, order_no, service_date, status, total_cost
            FROM machine_service_orders
            WHERE sales_order_id=%s
               OR (%s IS NOT NULL AND cost_object_id=%s)
               OR (%s IS NOT NULL AND project_code=%s)
               OR (%s IS NOT NULL AND serial_no=%s)
            ORDER BY service_date DESC NULLS LAST, id DESC
            LIMIT 40
            """,
            (order_id, cost_object_id, cost_object_id, project_code, project_code, serial_no, serial_no),
        ),
        event_type="service_order",
        number_key="order_no",
        date_key="service_date",
        url_prefix="/service-orders",
        amount_key="total_cost",
    )
    _append_project_events(
        events,
        query_rows(
            """
            SELECT id, rma_no, rma_date, status, amount
            FROM machine_service_rmas
            WHERE sales_order_id=%s
               OR (%s IS NOT NULL AND project_code=%s)
               OR (%s IS NOT NULL AND serial_no=%s)
            ORDER BY rma_date DESC NULLS LAST, id DESC
            LIMIT 40
            """,
            (order_id, project_code, project_code, serial_no, serial_no),
        ),
        event_type="service_rma",
        number_key="rma_no",
        date_key="rma_date",
        url_prefix="/service-rmas",
        amount_key="amount",
    )
    events.sort(
        key=lambda event: (
            event.get("event_date") is not None,
            _project_event_sort_value(event.get("event_date")),
            event.get("source_id") or 0,
        ),
        reverse=True,
    )
    return events[:limit]


def _project_axis_overview_payload(
    query_one,
    order,
    project_kit_rows,
    project_items_without_bom,
    project_finance_summary,
    build_kit_summary,
):
    project_code = order.get("project_code")
    serial_no = order.get("serial_no")
    cost_object_id = order.get("cost_object_id")
    finance_summary = project_finance_summary(order, project_code, serial_no, cost_object_id)
    kit_rows = project_kit_rows(order.get("id"), project_code, serial_no, cost_object_id)
    no_bom_items = project_items_without_bom(order.get("id"))
    kit_summary = build_kit_summary(kit_rows, no_bom_items)
    counts = _project_axis_counts(query_one, order)
    engineering_readiness = _project_engineering_readiness(query_one, order, kit_summary)
    next_action, owner_role, blocked_reason = _project_next_action(
        {
            "project_code": project_code,
            "serial_no": serial_no,
            "shortage_lines": (kit_summary or {}).get("shortage_count"),
            "pending_purchase_qty": counts.get("pending_purchase_qty"),
            "open_work_order_count": counts.get("open_work_order_count"),
            "shipment_count": counts.get("shipment_count"),
            "receivable_balance": (finance_summary or {}).get("receivable_balance"),
            "service_order_count": counts.get("service_order_count"),
        },
        lambda value: as_decimal_safe(value),
    )
    if not engineering_readiness.get("ready"):
        next_action = engineering_readiness.get("next_action")
        owner_role = engineering_readiness.get("owner_role")
        blocked_reason = engineering_readiness.get("blocked_reason")
    return {
        "found": True,
        "order": order,
        "ledger_url": f"/projects/{order.get('id')}",
        "axis": {
            "project_code": project_code,
            "serial_no": serial_no,
            "cost_object_id": cost_object_id,
        },
        "counts": counts,
        "engineering_readiness": engineering_readiness,
        "kit_summary": kit_summary,
        "finance_summary": finance_summary,
        "next_action": next_action,
        "owner_role": owner_role,
        "blocked_reason": blocked_reason,
    }


def _project_axis_engineering_readiness_payload(
    query_one,
    order,
    project_kit_rows,
    project_items_without_bom,
    build_kit_summary,
):
    kit_rows = project_kit_rows(
        order.get("id"),
        order.get("project_code"),
        order.get("serial_no"),
        order.get("cost_object_id"),
    )
    no_bom_items = project_items_without_bom(order.get("id"))
    kit_summary = build_kit_summary(kit_rows, no_bom_items)
    readiness = _project_engineering_readiness(query_one, order, kit_summary)
    return {
        "found": True,
        "order_id": order.get("id"),
        "order_no": order.get("order_no"),
        "project_code": order.get("project_code"),
        "serial_no": order.get("serial_no"),
        "ledger_url": f"/projects/{order.get('id')}",
        "engineering_readiness": readiness,
        "kit_summary": kit_summary,
        "next_action": readiness.get("next_action"),
        "owner_role": readiness.get("owner_role"),
        "blocked_reason": readiness.get("blocked_reason"),
    }


def _project_axis_procurement_closure_payload(
    query_one,
    order,
    project_kit_rows,
    project_items_without_bom,
    build_kit_summary,
):
    kit_rows = project_kit_rows(
        order.get("id"),
        order.get("project_code"),
        order.get("serial_no"),
        order.get("cost_object_id"),
    )
    no_bom_items = project_items_without_bom(order.get("id"))
    kit_summary = build_kit_summary(kit_rows, no_bom_items)
    readiness = _project_engineering_readiness(query_one, order, kit_summary)
    project_code = order.get("project_code")
    serial_no = order.get("serial_no")
    cost_object_id = order.get("cost_object_id")
    counts = query_one(
        """
        SELECT
          (
            SELECT COUNT(*)
            FROM mrp_requirements mr
            WHERE COALESCE(mr.shortage_quantity, 0) > 0
              AND (
                    (%s IS NOT NULL AND mr.project_code=%s)
                    OR (%s IS NOT NULL AND mr.serial_no=%s)
                  )
          ) AS shortage_line_count,
          (
            SELECT COALESCE(SUM(mr.shortage_quantity), 0)
            FROM mrp_requirements mr
            WHERE COALESCE(mr.shortage_quantity, 0) > 0
              AND (
                    (%s IS NOT NULL AND mr.project_code=%s)
                    OR (%s IS NOT NULL AND mr.serial_no=%s)
                  )
          ) AS shortage_qty,
          (
            SELECT COUNT(DISTINCT pr.id)
            FROM purchase_requisitions pr
            LEFT JOIN purchase_requisition_items pri ON pri.req_id=pr.id
            WHERE (%s IS NOT NULL AND (pr.project_code=%s OR pri.project_code=%s))
               OR (%s IS NOT NULL AND (pr.serial_no=%s OR pri.serial_no=%s))
          ) AS purchase_request_count,
          (
            SELECT COUNT(*)
            FROM purchase_orders po
            WHERE (%s IS NOT NULL AND po.cost_object_id=%s)
               OR (%s IS NOT NULL AND po.project_code=%s)
               OR (%s IS NOT NULL AND po.serial_no=%s)
          ) AS purchase_order_count,
          (
            SELECT COALESCE(SUM(GREATEST(COALESCE(poi.quantity, 0)-COALESCE(poi.received_qty, 0), 0)), 0)
            FROM purchase_orders po
            LEFT JOIN purchase_order_items poi ON poi.order_id=po.id
            WHERE (%s IS NOT NULL AND po.cost_object_id=%s)
               OR (%s IS NOT NULL AND po.project_code=%s)
               OR (%s IS NOT NULL AND po.serial_no=%s)
          ) AS pending_receipt_qty,
          (
            SELECT COUNT(DISTINCT pr.id)
            FROM purchase_receipts pr
            LEFT JOIN purchase_orders po ON po.id=pr.order_id
            WHERE (%s IS NOT NULL AND (pr.cost_object_id=%s OR po.cost_object_id=%s))
               OR (%s IS NOT NULL AND (pr.project_code=%s OR po.project_code=%s))
               OR (%s IS NOT NULL AND (pr.serial_no=%s OR po.serial_no=%s))
          ) AS purchase_receipt_count,
          (
            SELECT COUNT(DISTINCT sp.id)
            FROM supplier_payables sp
            LEFT JOIN purchase_orders po_ap
              ON sp.doc_type='purchase_order' AND (po_ap.id=sp.doc_id OR po_ap.order_no=sp.doc_no)
            LEFT JOIN subcontract_orders sc_ap
              ON sp.doc_type='subcontract_order' AND (sc_ap.id=sp.doc_id OR sc_ap.order_no=sp.doc_no)
            WHERE (%s IS NOT NULL AND (
                    sp.cost_object_id=%s OR po_ap.cost_object_id=%s OR sc_ap.cost_object_id=%s
                  ))
               OR (%s IS NOT NULL AND (
                    sp.project_code=%s OR po_ap.project_code=%s OR sc_ap.project_code=%s
                  ))
               OR (%s IS NOT NULL AND (
                    sp.serial_no=%s OR po_ap.serial_no=%s OR sc_ap.serial_no=%s
                  ))
          ) AS supplier_payable_count,
          (
            SELECT COALESCE(SUM(sp.balance), 0)
            FROM supplier_payables sp
            LEFT JOIN purchase_orders po_ap
              ON sp.doc_type='purchase_order' AND (po_ap.id=sp.doc_id OR po_ap.order_no=sp.doc_no)
            LEFT JOIN subcontract_orders sc_ap
              ON sp.doc_type='subcontract_order' AND (sc_ap.id=sp.doc_id OR sc_ap.order_no=sp.doc_no)
            WHERE (%s IS NOT NULL AND (
                    sp.cost_object_id=%s OR po_ap.cost_object_id=%s OR sc_ap.cost_object_id=%s
                  ))
               OR (%s IS NOT NULL AND (
                    sp.project_code=%s OR po_ap.project_code=%s OR sc_ap.project_code=%s
                  ))
               OR (%s IS NOT NULL AND (
                    sp.serial_no=%s OR po_ap.serial_no=%s OR sc_ap.serial_no=%s
                  ))
          ) AS payable_balance
        """,
        (
            project_code,
            project_code,
            serial_no,
            serial_no,
            project_code,
            project_code,
            serial_no,
            serial_no,
            project_code,
            project_code,
            project_code,
            serial_no,
            serial_no,
            serial_no,
            cost_object_id,
            cost_object_id,
            project_code,
            project_code,
            serial_no,
            serial_no,
            cost_object_id,
            cost_object_id,
            project_code,
            project_code,
            serial_no,
            serial_no,
            cost_object_id,
            cost_object_id,
            cost_object_id,
            project_code,
            project_code,
            project_code,
            serial_no,
            serial_no,
            serial_no,
            cost_object_id,
            cost_object_id,
            cost_object_id,
            cost_object_id,
            project_code,
            project_code,
            project_code,
            project_code,
            serial_no,
            serial_no,
            serial_no,
            serial_no,
            cost_object_id,
            cost_object_id,
            cost_object_id,
            cost_object_id,
            project_code,
            project_code,
            project_code,
            project_code,
            serial_no,
            serial_no,
            serial_no,
            serial_no,
        ),
    ) or {}
    if not readiness.get("ready"):
        status = "blocked"
        blocked_reason = readiness.get("blocked_reason") or "工程准备未就绪"
        next_action = readiness.get("next_action") or "先补技术确认、BOM或图纸"
        owner_role = readiness.get("owner_role") or "技术/工艺"
    elif counts.get("shortage_line_count"):
        status = "shortage_to_request"
        blocked_reason = "存在缺料，需要从采购建议生成采购申请"
        next_action = "进入采购建议，按工程已就绪缺料生成采购申请"
        owner_role = "计划/采购"
    elif counts.get("purchase_request_count") and not counts.get("purchase_order_count"):
        status = "request_to_order"
        blocked_reason = "采购申请尚未下推采购订单"
        next_action = "审核采购申请并下推采购订单"
        owner_role = "采购"
    elif counts.get("purchase_order_count") and counts.get("pending_receipt_qty"):
        status = "order_to_receipt"
        blocked_reason = "采购订单仍有未收数量"
        next_action = "按采购订单办理采购入库"
        owner_role = "仓库/采购"
    elif counts.get("purchase_receipt_count") and counts.get("payable_balance"):
        status = "payable_open"
        blocked_reason = "供应商应付仍有未付余额"
        next_action = "核对应付余额并办理付款核销"
        owner_role = "财务/采购"
    else:
        status = "closed_or_not_started"
        blocked_reason = "暂无采购闭环阻塞"
        next_action = "按项目交付节奏继续跟踪采购、库存和应付"
        owner_role = "项目/计划"
    return {
        "found": True,
        "order_id": order.get("id"),
        "order_no": order.get("order_no"),
        "project_code": project_code,
        "serial_no": serial_no,
        "ledger_url": f"/projects/{order.get('id')}",
        "status": status,
        "blocked_reason": blocked_reason,
        "next_action": next_action,
        "owner_role": owner_role,
        "counts": counts,
        "engineering_readiness": readiness,
        "kit_summary": kit_summary,
        "links": {
            "purchase_suggestions": "/procurement/suggestions",
            "purchase_request": "/purchase_request",
            "purchase_orders": "/purchase-orders",
            "purchase_receipts": "/purchase_receipts",
            "supplier_payables": "/payables",
        },
    }


def _project_axis_production_closure_payload(query_one, order):
    if not order:
        return {"found": False}
    project_code = order.get("project_code")
    serial_no = order.get("serial_no")
    cost_object_id = order.get("cost_object_id")
    axis6 = (cost_object_id, cost_object_id, project_code, project_code, serial_no, serial_no)
    doc8 = (
        cost_object_id,
        cost_object_id,
        project_code,
        project_code,
        project_code,
        serial_no,
        serial_no,
        serial_no,
    )
    stock16 = (
        project_code,
        project_code,
        serial_no,
        serial_no,
        cost_object_id,
        cost_object_id,
        project_code,
        project_code,
        serial_no,
        serial_no,
        cost_object_id,
        cost_object_id,
        project_code,
        project_code,
        serial_no,
        serial_no,
    )
    counts = query_one(
        """
        SELECT
          (
            SELECT COUNT(*)
            FROM work_orders wo
            WHERE (%s IS NOT NULL AND wo.cost_object_id=%s)
               OR (%s IS NOT NULL AND wo.project_code=%s)
               OR (%s IS NOT NULL AND wo.serial_no=%s)
          ) AS work_order_count,
          (
            SELECT COUNT(*)
            FROM work_orders wo
            WHERE (
                (%s IS NOT NULL AND wo.cost_object_id=%s)
                OR (%s IS NOT NULL AND wo.project_code=%s)
                OR (%s IS NOT NULL AND wo.serial_no=%s)
              )
              AND COALESCE(wo.status, '') NOT IN ('closed','completed','void','cancelled','已完工','已关闭','已作废','已完成')
          ) AS open_work_order_count,
          (
            SELECT COALESCE(SUM(mi.required_qty), 0)
            FROM wo_material_items mi
            JOIN work_orders wo ON wo.id=mi.wo_id
            WHERE (%s IS NOT NULL AND wo.cost_object_id=%s)
               OR (%s IS NOT NULL AND wo.project_code=%s)
               OR (%s IS NOT NULL AND wo.serial_no=%s)
          ) AS material_required_qty,
          (
            SELECT COALESCE(SUM(mi.issued_qty), 0)
            FROM wo_material_items mi
            JOIN work_orders wo ON wo.id=mi.wo_id
            WHERE (%s IS NOT NULL AND wo.cost_object_id=%s)
               OR (%s IS NOT NULL AND wo.project_code=%s)
               OR (%s IS NOT NULL AND wo.serial_no=%s)
          ) AS material_issued_qty,
          (
            SELECT COALESCE(SUM(mi.returned_qty), 0)
            FROM wo_material_items mi
            JOIN work_orders wo ON wo.id=mi.wo_id
            WHERE (%s IS NOT NULL AND wo.cost_object_id=%s)
               OR (%s IS NOT NULL AND wo.project_code=%s)
               OR (%s IS NOT NULL AND wo.serial_no=%s)
          ) AS material_returned_qty,
          (
            SELECT COALESCE(SUM(GREATEST(COALESCE(mi.required_qty, 0)-COALESCE(mi.issued_qty, 0)+COALESCE(mi.returned_qty, 0), 0)), 0)
            FROM wo_material_items mi
            JOIN work_orders wo ON wo.id=mi.wo_id
            WHERE (%s IS NOT NULL AND wo.cost_object_id=%s)
               OR (%s IS NOT NULL AND wo.project_code=%s)
               OR (%s IS NOT NULL AND wo.serial_no=%s)
          ) AS pending_issue_qty,
          (
            SELECT COUNT(*)
            FROM pick_lists pl
            LEFT JOIN work_orders wo ON wo.id=pl.work_order_id
            WHERE pl.doc_type='production_issue'
              AND (
                   (%s IS NOT NULL AND wo.cost_object_id=%s)
                   OR (%s IS NOT NULL AND (pl.project_code=%s OR wo.project_code=%s))
                   OR (%s IS NOT NULL AND (pl.serial_no=%s OR wo.serial_no=%s))
              )
          ) AS issue_doc_count,
          (
            SELECT COUNT(*)
            FROM pick_lists pl
            LEFT JOIN work_orders wo ON wo.id=pl.work_order_id
            WHERE pl.doc_type='production_return'
              AND (
                   (%s IS NOT NULL AND wo.cost_object_id=%s)
                   OR (%s IS NOT NULL AND (pl.project_code=%s OR wo.project_code=%s))
                   OR (%s IS NOT NULL AND (pl.serial_no=%s OR wo.serial_no=%s))
              )
          ) AS return_doc_count,
          (
            SELECT COUNT(*)
            FROM production_completion_orders pc
            LEFT JOIN work_orders wo ON wo.id=pc.work_order_id
            WHERE (%s IS NOT NULL AND wo.cost_object_id=%s)
               OR (%s IS NOT NULL AND (pc.project_code=%s OR wo.project_code=%s))
               OR (%s IS NOT NULL AND (pc.serial_no=%s OR wo.serial_no=%s))
          ) AS completion_doc_count,
          (
            SELECT COALESCE(SUM(wc.qty), 0)
            FROM wo_complete_items wc
            JOIN work_orders wo ON wo.id=wc.wo_id
            WHERE (%s IS NOT NULL AND wo.cost_object_id=%s)
               OR (%s IS NOT NULL AND wo.project_code=%s)
               OR (%s IS NOT NULL AND wo.serial_no=%s)
          ) AS completed_qty,
          (
            SELECT COUNT(*)
            FROM stock_transactions st
            WHERE st.transaction_type IN ('工单领料','生产领料','工单退料','生产退料','工单完工入库')
              AND (
                   (%s IS NOT NULL AND st.project_code=%s)
                   OR (%s IS NOT NULL AND st.serial_no=%s)
                   OR st.reference_no IN (
                       SELECT pl.doc_no FROM pick_lists pl
                       LEFT JOIN work_orders wo ON wo.id=pl.work_order_id
                       WHERE (%s IS NOT NULL AND wo.cost_object_id=%s)
                          OR (%s IS NOT NULL AND wo.project_code=%s)
                          OR (%s IS NOT NULL AND wo.serial_no=%s)
                       UNION
                       SELECT pc.completion_no FROM production_completion_orders pc
                       LEFT JOIN work_orders wo2 ON wo2.id=pc.work_order_id
                       WHERE (%s IS NOT NULL AND wo2.cost_object_id=%s)
                          OR (%s IS NOT NULL AND wo2.project_code=%s)
                          OR (%s IS NOT NULL AND wo2.serial_no=%s)
                   )
              )
          ) AS stock_tx_count,
          (
            SELECT COUNT(*)
            FROM work_order_cost_lines wcl
            LEFT JOIN work_orders wo ON wo.id=wcl.work_order_id
            WHERE (%s IS NOT NULL AND wcl.cost_object_id=%s)
               OR (%s IS NOT NULL AND wo.project_code=%s)
               OR (%s IS NOT NULL AND wo.serial_no=%s)
          ) AS cost_line_count,
          (
            SELECT COALESCE(SUM(woc.total_cost), 0)
            FROM work_order_costs woc
            LEFT JOIN work_orders wo ON wo.id=woc.work_order_id
            WHERE (%s IS NOT NULL AND woc.cost_object_id=%s)
               OR (%s IS NOT NULL AND wo.project_code=%s)
               OR (%s IS NOT NULL AND wo.serial_no=%s)
          ) AS total_cost
        """,
        (
            axis6
            + axis6
            + axis6
            + axis6
            + axis6
            + axis6
            + doc8
            + doc8
            + doc8
            + axis6
            + stock16
            + axis6
            + axis6
        ),
    ) or {}
    if not counts.get("work_order_count"):
        status = "no_work_order"
        blocked_reason = "项目尚未建立生产工单"
        next_action = "按销售项目和BOM建立生产工单"
        owner_role = "计划"
    elif as_decimal_safe(counts.get("material_required_qty")) <= 0:
        status = "material_requirement_missing"
        blocked_reason = "工单尚未形成领料需求"
        next_action = "按BOM生成或补齐工单用料需求"
        owner_role = "计划/工艺"
    elif as_decimal_safe(counts.get("pending_issue_qty")) > 0:
        status = "material_issue_open"
        blocked_reason = "工单仍有未领或需补领物料"
        next_action = "办理生产领料或补料"
        owner_role = "仓库/生产"
    elif as_decimal_safe(counts.get("completed_qty")) <= 0:
        status = "completion_open"
        blocked_reason = "工单尚未完工入库"
        next_action = "办理完工入库并核对库存流水"
        owner_role = "生产/仓库"
    elif not counts.get("cost_line_count") or as_decimal_safe(counts.get("total_cost")) <= 0:
        status = "cost_collection_open"
        blocked_reason = "工单成本尚未归集或金额为零"
        next_action = "同步并复核工单成本归集"
        owner_role = "财务/生产"
    elif counts.get("open_work_order_count"):
        status = "work_order_open"
        blocked_reason = "仍有未关闭工单"
        next_action = "复核工单状态、质量和成本后关闭"
        owner_role = "生产"
    else:
        status = "closed_or_ready"
        blocked_reason = "生产闭环暂无阻塞"
        next_action = "进入发货、应收和售后准备核对"
        owner_role = "项目/生产"
    return {
        "found": True,
        "order_id": order.get("id"),
        "order_no": order.get("order_no"),
        "project_code": project_code,
        "serial_no": serial_no,
        "ledger_url": f"/projects/{order.get('id')}",
        "status": status,
        "blocked_reason": blocked_reason,
        "next_action": next_action,
        "owner_role": owner_role,
        "counts": counts,
        "links": {
            "work_orders": "/work-orders",
            "production_issues": "/production-issues",
            "production_returns": "/production-returns",
            "production_completions": "/production-completions",
            "project_ledger": f"/projects/{order.get('id')}",
        },
    }


def _project_axis_assistant_context(query_one, query_rows, order, project_kit_rows, project_items_without_bom, build_kit_summary):
    readiness_payload = _project_axis_engineering_readiness_payload(
        query_one,
        order,
        project_kit_rows,
        project_items_without_bom,
        build_kit_summary,
    )
    events = _project_axis_events(query_rows, order, 20)
    readiness = readiness_payload.get("engineering_readiness") or {}
    summary = [
        f"销售订单：{order.get('order_no') or '-'}",
        f"项目号：{order.get('project_code') or '-'}；机号：{order.get('serial_no') or '-'}",
        f"工程准备：{readiness.get('status') or '-'}；阻塞原因：{readiness.get('blocked_reason') or '无'}",
        f"下一步：{readiness.get('next_action') or '-'}；责任：{readiness.get('owner_role') or '-'}",
    ]
    return {
        "found": True,
        "order_id": order.get("id"),
        "order_no": order.get("order_no"),
        "project_code": order.get("project_code"),
        "serial_no": order.get("serial_no"),
        "ledger_url": f"/projects/{order.get('id')}",
        "engineering_readiness": readiness,
        "kit_summary": readiness_payload.get("kit_summary"),
        "recent_events": events,
        "summary": "\n".join(summary),
        "assistant_guidance": {
            "can_answer": [
                "为什么该项目不能进入采购建议或生产准备",
                "技术确认、BOM、图纸、齐套分别由谁处理",
                "下一步应该进入哪个单据或台账核对",
            ],
            "readonly": True,
            "write_actions": "AI助手只解释和引导，不自动确认、审核、过账或生成下游单据。",
        },
    }


def _project_engineering_readiness(query_one, order, kit_summary=None):
    if not order:
        return {"ready": False, "blocked_reason": "缺少销售订单", "next_action": "选择销售订单", "owner_role": "销售"}
    order_id = order.get("id")
    project_code = order.get("project_code")
    serial_no = order.get("serial_no")
    confirmation = query_one(
        """
        SELECT etc.id, etc.confirm_no, etc.confirm_date, etc.status, etc.confirmed_at,
               etc.project_code, etc.serial_no, etc.bom_id, etc.routing_id, etc.work_center_id,
               etc.drawing_no, etc.drawing_version, etc.owner, etc.next_action,
               b.bom_no, b.version AS bom_version, b.status AS bom_status,
               COALESCE(bom_items.item_count, 0) AS bom_item_count
        FROM engineering_technical_confirmations etc
        LEFT JOIN boms b ON b.id=etc.bom_id
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS item_count
            FROM bom_items bi
            WHERE bi.bom_id=etc.bom_id
        ) bom_items ON TRUE
        WHERE etc.sales_order_id=%s
           OR (%s IS NOT NULL AND etc.project_code=%s)
           OR (%s IS NOT NULL AND etc.serial_no=%s)
        ORDER BY etc.confirmed_at DESC NULLS LAST, etc.id DESC
        LIMIT 1
        """,
        (order_id, project_code, project_code, serial_no, serial_no),
    )
    sales_bom = query_one(
        """
        SELECT b.id, b.bom_no, b.version, b.status, COUNT(bi.id) AS item_count
        FROM sales_order_items soi
        JOIN boms b ON b.product_id=soi.product_id
        LEFT JOIN bom_items bi ON bi.bom_id=b.id
        WHERE soi.order_id=%s
        GROUP BY b.id, b.bom_no, b.version, b.status
        ORDER BY CASE
            WHEN COALESCE(b.status, '') IN ('active','released','enabled','已启用','已发布') THEN 0
            ELSE 1
        END, b.id DESC
        LIMIT 1
        """,
        (order_id,),
    )
    bom_id = confirmation.get("bom_id") if confirmation else None
    if not bom_id and sales_bom:
        bom_id = sales_bom.get("id")
    drawing_no = confirmation.get("drawing_no") if confirmation else None
    drawing_version = confirmation.get("drawing_version") if confirmation else None
    released_drawing = None
    if drawing_no:
        released_drawing = query_one(
            """
            SELECT id, drawing_no, version, status
            FROM engineering_drawings
            WHERE drawing_no=%s
              AND (%s IS NULL OR version=%s)
              AND status='released'
              AND (effective_date IS NULL OR effective_date <= CURRENT_DATE)
              AND (obsolete_date IS NULL OR obsolete_date > CURRENT_DATE)
            ORDER BY effective_date DESC NULLS LAST, released_date DESC NULLS LAST, id DESC
            LIMIT 1
            """,
            (drawing_no, drawing_version, drawing_version),
        )
    confirmed = bool(
        confirmation
        and (
            confirmation.get("confirmed_at")
            or (confirmation.get("status") or "").strip() in {"已确认", "confirmed", "released"}
        )
    )
    bom_item_count = (
        confirmation.get("bom_item_count")
        if confirmation and confirmation.get("bom_id")
        else (sales_bom or {}).get("item_count", 0)
    )
    bom_status = (
        confirmation.get("bom_status")
        if confirmation and confirmation.get("bom_id")
        else (sales_bom or {}).get("status")
    )
    blockers = []
    if not confirmation:
        blockers.append("缺少技术确认单")
    elif not confirmed:
        blockers.append("技术确认未确认")
    if not bom_id:
        blockers.append("缺少BOM")
    elif not bom_item_count:
        blockers.append("BOM无明细")
    if not drawing_no or not drawing_version:
        blockers.append("缺少图纸版本")
    elif not released_drawing:
        blockers.append("图纸未发布")
    if kit_summary and kit_summary.get("shortage_count"):
        blockers.append("齐套存在缺口")
    if not blockers:
        next_action = "进入采购建议和生产准备"
        owner_role = "计划"
    elif blockers[0] == "齐套存在缺口":
        next_action = "处理齐套缺口"
        owner_role = "计划/采购"
    else:
        next_action = "补齐技术确认、BOM和图纸"
        owner_role = "技术/工艺"
    return {
        "ready": not blockers,
        "status": "就绪" if not blockers else "未就绪",
        "blocked_reason": "、".join(blockers),
        "next_action": next_action,
        "owner_role": owner_role,
        "confirmation": confirmation,
        "sales_bom": sales_bom,
        "released_drawing": released_drawing,
        "confirmed": confirmed,
        "bom_item_count": bom_item_count or 0,
        "bom_status": bom_status,
    }


def _subcontract_project_execution(row):
    status = (row.get("status") or "").strip()
    ordered_qty = as_decimal_safe(row.get("quantity"))
    issued_qty = as_decimal_safe(row.get("issued_qty"))
    received_qty = as_decimal_safe(row.get("received_qty"))
    scrap_qty = as_decimal_safe(row.get("scrap_qty"))
    payable_balance = as_decimal_safe(row.get("payable_balance"))
    if not (row.get("project_code") or "").strip() or not (row.get("serial_no") or "").strip():
        return "追溯缺失", "补齐项目号/机号"
    if status in {"已作废", "void", "cancelled"}:
        return "已作废", "保留追溯"
    if scrap_qty > 0:
        return "收货异常", "处理报废/短收并核价"
    if status in {"已关闭", "已完成", "closed", "completed"}:
        return "已完成", "保留质量和应付追溯"
    if issued_qty <= 0:
        return "待发料", "委外发料"
    if ordered_qty > 0 and received_qty + scrap_qty < ordered_qty:
        return "待收货", "跟催委外收货"
    if ordered_qty <= 0 and received_qty <= 0:
        return "数量待确认", "确认委外数量"
    if payable_balance > 0:
        return "待付款", "核对应付并安排付款"
    return "已完成", "关闭委外并归档"


def _work_order_project_execution(row):
    status = (row.get("status") or "").strip()
    required_qty = as_decimal_safe(row.get("required_issue_qty"))
    issued_qty = as_decimal_safe(row.get("issued_qty"))
    pending_qty = as_decimal_safe(row.get("pending_issue_qty"))
    completed_qty = as_decimal_safe(row.get("completed_qty"))
    if status in {"已作废", "已取消", "void", "cancelled"}:
        return "已作废", "保留追溯", "生产"
    if status in {"已关闭", "已完工", "已完成", "closed", "completed"}:
        return "已完成", "核对成本和质检记录", "生产/财务"
    if required_qty <= 0:
        return "待建领料需求", "按 BOM 生成或手工补充领料需求", "计划"
    if pending_qty > 0:
        return "待领料", "按未领数量领料", "仓库/生产"
    if completed_qty <= 0:
        return "待完工", "登记完工入库和质检", "生产"
    if issued_qty > required_qty:
        return "超领待核", "核对补料原因和工单成本", "生产/财务"
    return "已齐套", "推进完工、质检和关闭", "生产"


def _project_cost_rows(query_rows, order_id, project_code, serial_no, cost_object_id):
    rows = []
    purchase_rows = query_rows(
        """
        SELECT '采购成本' AS cost_type, order_no AS source_no, order_date AS cost_date,
               supplier_id::text AS partner, total_amount AS amount, status, '采购订单' AS source_type
        FROM purchase_orders
        WHERE (%s IS NOT NULL AND cost_object_id=%s)
           OR (%s IS NOT NULL AND project_code=%s)
           OR (%s IS NOT NULL AND serial_no=%s)
        ORDER BY id DESC
        LIMIT 40
        """,
        (cost_object_id, cost_object_id, project_code, project_code, serial_no, serial_no),
    )
    subcontract_rows = query_rows(
        """
        SELECT '委外成本' AS cost_type, order_no AS source_no, order_date AS cost_date,
               supplier_id::text AS partner, total_amount AS amount, status, '委外订单' AS source_type
        FROM subcontract_orders
        WHERE (%s IS NOT NULL AND cost_object_id=%s)
           OR (%s IS NOT NULL AND project_code=%s)
           OR (%s IS NOT NULL AND serial_no=%s)
        ORDER BY id DESC
        LIMIT 40
        """,
        (cost_object_id, cost_object_id, project_code, project_code, serial_no, serial_no),
    )
    work_rows = query_rows(
        """
        SELECT COALESCE(wcl.cost_type, '工单成本') AS cost_type,
               COALESCE(wcl.source_no, wo.wo_no) AS source_no,
               COALESCE(wcl.created_at::date, woc.last_calculated_at::date) AS cost_date,
               wo.wo_no AS partner,
               COALESCE(wcl.amount, woc.total_cost, 0) AS amount,
               wo.status,
               COALESCE(wcl.source_type, '工单') AS source_type
        FROM work_orders wo
        LEFT JOIN work_order_costs woc ON woc.work_order_id=wo.id
        LEFT JOIN work_order_cost_lines wcl ON wcl.work_order_id=wo.id
        WHERE (%s IS NOT NULL AND wo.cost_object_id=%s)
           OR (%s IS NOT NULL AND wo.project_code=%s)
           OR (%s IS NOT NULL AND wo.serial_no=%s)
        ORDER BY COALESCE(wcl.created_at, woc.last_calculated_at) DESC NULLS LAST, wo.id DESC
        LIMIT 80
        """,
        (cost_object_id, cost_object_id, project_code, project_code, serial_no, serial_no),
    )
    service_rows = query_rows(
        """
        SELECT '售后成本' AS cost_type, order_no AS source_no, service_date AS cost_date,
               service_type AS partner, total_cost AS amount, status, '服务单' AS source_type
        FROM machine_service_orders
        WHERE sales_order_id=%s
           OR (%s IS NOT NULL AND cost_object_id=%s)
           OR (%s IS NOT NULL AND project_code=%s)
           OR (%s IS NOT NULL AND serial_no=%s)
        ORDER BY id DESC
        LIMIT 40
        """,
        (order_id, cost_object_id, cost_object_id, project_code, project_code, serial_no, serial_no),
    )
    for group in (purchase_rows, subcontract_rows, work_rows, service_rows):
        rows.extend(dict(row) for row in group)
    for row in rows:
        amount = as_decimal_safe(row.get("amount"))
        row["amount"] = amount
        if amount < 0:
            row["cost_flag"] = "冲减"
        elif amount == 0:
            row["cost_flag"] = "待归集"
        else:
            row["cost_flag"] = "已归集"
    return rows[:160]


def _pilot_acceptance_answers(order, context, finance_summary):
    if not order:
        return []
    kit_summary = context.get("kit_summary") or {}
    finance_summary = finance_summary or {}
    shipments = context.get("shipments") or []
    service_cards = context.get("service_cards") or []
    service_orders = context.get("service_orders") or []
    work_orders = context.get("work_orders") or []
    subcontract_orders = context.get("subcontract_orders") or []
    purchase_orders = context.get("purchase_orders") or []
    cost_rows = context.get("cost_rows") or []
    answers = [
        {
            "question": "这台设备卖给谁",
            "answer": order.get("customer_name") or "未关联客户",
            "status": "通过" if order.get("customer_name") else "待补",
            "owner": "销售",
        },
        {
            "question": "合同金额、交期、发货状态",
            "answer": f"合同 {order.get('total_amount') or 0}，交期 {order.get('delivery_date') or '-'}，发货 {len(shipments)} 单，销售状态 {order.get('status') or '-'}",
            "status": "通过" if shipments else "待发货",
            "owner": "销售/仓库",
        },
        {
            "question": "项目号和机号",
            "answer": f"{order.get('project_code') or '-'} / {order.get('serial_no') or '-'}",
            "status": "通过" if order.get("project_code") and order.get("serial_no") else "待补",
            "owner": "销售/项目",
        },
        {
            "question": "BOM和缺料",
            "answer": f"BOM物料 {kit_summary.get('total_count', 0)} 行，缺料 {kit_summary.get('shortage_count', 0)} 行，库存缺口 {kit_summary.get('stock_shortage_count', 0)} 行",
            "status": "通过" if kit_summary.get("total_count") and not kit_summary.get("shortage_count") else "需关注",
            "owner": "计划/采购",
        },
        {
            "question": "采购到货",
            "answer": f"采购单 {len(purchase_orders)} 张，采购未到 {sum(as_decimal_safe(row.get('pending_purchase_qty')) for row in purchase_orders)}",
            "status": "通过" if purchase_orders else "待确认",
            "owner": "采购",
        },
        {
            "question": "委外发料和收货",
            "answer": f"委外单 {len(subcontract_orders)} 张，待处理 {len([row for row in subcontract_orders if row.get('execution_status') not in {'已完成','已作废'}])} 张",
            "status": "通过" if subcontract_orders and not [row for row in subcontract_orders if row.get("execution_status") not in {"已完成", "已作废"}] else "需关注",
            "owner": "采购/仓库",
        },
        {
            "question": "工单领料和完工",
            "answer": f"工单 {len(work_orders)} 张，未领 {sum(as_decimal_safe(row.get('pending_issue_qty')) for row in work_orders)}，完工 {sum(as_decimal_safe(row.get('completed_qty')) for row in work_orders)}",
            "status": "通过" if work_orders and not [row for row in work_orders if row.get("issue_state") in {"待建领料需求", "待领料", "待完工", "超领待核"}] else "需关注",
            "owner": "生产/仓库",
        },
        {
            "question": "发货和服务档案",
            "answer": f"发货 {len(shipments)} 单，服务档案 {len(service_cards)} 个",
            "status": "通过" if shipments and service_cards else "待补",
            "owner": "仓库/售后",
        },
        {
            "question": "售后服务",
            "answer": f"服务单 {len(service_orders)} 张，RMA {len(context.get('service_rmas') or [])} 张",
            "status": "通过" if service_cards else "待建档",
            "owner": "售后",
        },
        {
            "question": "应收应付",
            "answer": f"应收余额 {finance_summary.get('receivable_balance') or 0}，应付余额 {finance_summary.get('payable_balance') or 0}",
            "status": "通过" if as_decimal_safe(finance_summary.get("receivable_balance")) == 0 and as_decimal_safe(finance_summary.get("payable_balance")) == 0 else "需关注",
            "owner": "财务/销售/采购",
        },
        {
            "question": "成本和毛利",
            "answer": f"成本来源 {len(cost_rows)} 行，总成本 {finance_summary.get('total_cost') or 0}，毛利 {finance_summary.get('gross_profit') or 0}",
            "status": "通过" if cost_rows else "待归集",
            "owner": "财务/成本",
        },
    ]
    return answers


def _pilot_acceptance_summary(answers):
    blocking_answers = [row for row in answers if row.get("status") != "通过"]
    primary_blocker = blocking_answers[0] if blocking_answers else {}
    owners = []
    gaps = []
    for row in blocking_answers:
        question = row.get("question")
        owner = row.get("owner")
        if question and question not in gaps:
            gaps.append(question)
        if owner and owner not in owners:
            owners.append(owner)
    return {
        "status": "可验收" if not blocking_answers else "需关注",
        "class": "success" if not blocking_answers else "warning",
        "gap_count": len(blocking_answers),
        "gaps": "、".join(gaps) if gaps else "无",
        "owners": "、".join(owners) if owners else "无",
        "primary_question": primary_blocker.get("question", "无"),
        "primary_owner": primary_blocker.get("owner", "无"),
        "primary_status": primary_blocker.get("status", "通过") if primary_blocker else "通过",
    }


def render_project_ledger(
    query_one,
    query_rows,
    as_decimal,
    money_metric,
    filter_clean_rows,
    clean_display_text,
    args=None,
    today=None,
):
    args = args or request.args
    keyword = (args.get("keyword") or "").strip()
    status = (args.get("status") or "").strip()
    risk = (args.get("risk") or "").strip()
    owner = (args.get("owner") or "").strip()
    primary_owner = (args.get("primary_owner") or "").strip()
    try:
        page = int(args.get("page") or "1")
    except ValueError:
        page = 1
    page = max(page, 1)
    per_page = 20
    export_requested = args.get("export") in {"csv", "xlsx", "excel"} or args.get("format") in {"csv", "xlsx", "excel"}
    needs_python_filter = bool(risk or owner or primary_owner or export_requested)
    sql_limit = 1000 if needs_python_filter else per_page
    sql_offset = 0 if needs_python_filter else (page - 1) * per_page

    where_parts = []
    params = []
    if keyword:
        where_parts.append(
            """
            (
                so.order_no ILIKE %s
                OR so.project_code ILIKE %s
                OR so.serial_no ILIKE %s
                OR c.name ILIKE %s
            )
            """
        )
        params.extend([f"%{keyword}%"] * 4)
    if status:
        where_parts.append("COALESCE(so.status, '')=%s")
        params.append(status)
    where_sql = "WHERE " + " AND ".join(where_parts) if where_parts else ""

    rows = query_rows(
        f"""
        WITH base_orders AS (
            SELECT so.*, c.name AS customer_name
            FROM sales_orders so
            LEFT JOIN customers c ON c.id=so.customer_id
            {where_sql}
            ORDER BY so.id DESC
            LIMIT %s OFFSET %s
        )
        SELECT bo.id, bo.order_no, bo.order_date, bo.delivery_date,
               bo.project_code, bo.serial_no, bo.status, bo.total_amount,
               bo.shipped_amount, bo.customer_name, bo.cost_object_id,
               COALESCE(shortage.shortage_lines, 0) AS shortage_lines,
               COALESCE(shortage.shortage_qty, 0) AS shortage_qty,
               COALESCE(purchase.purchase_count, 0) AS purchase_count,
               COALESCE(purchase.pending_purchase_qty, 0) AS pending_purchase_qty,
               COALESCE(work.work_order_count, 0) AS work_order_count,
               COALESCE(work.open_work_order_count, 0) AS open_work_order_count,
               COALESCE(ship.shipment_count, 0) AS shipment_count,
               COALESCE(ar.receivable_balance, 0) AS receivable_balance,
               COALESCE(service.service_order_count, 0) AS service_order_count,
               COALESCE(card.service_card_count, 0) AS service_card_count,
               COALESCE(ap.payable_balance, 0) AS payable_balance,
               COALESCE(cost.project_cost, 0) AS project_cost
        FROM base_orders bo
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS shortage_lines,
                   COALESCE(SUM(shortage_quantity), 0) AS shortage_qty
            FROM mrp_requirements mr
            WHERE COALESCE(mr.shortage_quantity, 0) > 0
              AND (
                (mr.source_document_type='sales_order' AND mr.source_document_id=bo.id)
                OR (bo.cost_object_id IS NOT NULL AND mr.cost_object_id=bo.cost_object_id)
                OR (NULLIF(bo.project_code, '') IS NOT NULL AND mr.project_code=bo.project_code)
                OR (NULLIF(bo.serial_no, '') IS NOT NULL AND mr.serial_no=bo.serial_no)
              )
        ) shortage ON TRUE
        LEFT JOIN LATERAL (
            SELECT COUNT(DISTINCT po.id) AS purchase_count,
                   COALESCE(SUM(GREATEST(COALESCE(poi.quantity, 0)-COALESCE(poi.received_qty, 0), 0)), 0) AS pending_purchase_qty
            FROM purchase_orders po
            LEFT JOIN purchase_order_items poi ON poi.order_id=po.id
            WHERE (bo.cost_object_id IS NOT NULL AND po.cost_object_id=bo.cost_object_id)
               OR (NULLIF(bo.project_code, '') IS NOT NULL AND po.project_code=bo.project_code)
               OR (NULLIF(bo.serial_no, '') IS NOT NULL AND po.serial_no=bo.serial_no)
        ) purchase ON TRUE
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS work_order_count,
                   COUNT(*) FILTER (WHERE COALESCE(status, '') NOT IN ('已完工','已关闭','已作废')) AS open_work_order_count
            FROM work_orders wo
            WHERE (bo.cost_object_id IS NOT NULL AND wo.cost_object_id=bo.cost_object_id)
               OR (NULLIF(bo.project_code, '') IS NOT NULL AND wo.project_code=bo.project_code)
               OR (NULLIF(bo.serial_no, '') IS NOT NULL AND wo.serial_no=bo.serial_no)
        ) work ON TRUE
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS shipment_count
            FROM sales_shipments ss
            WHERE ss.order_id=bo.id
               OR (NULLIF(bo.project_code, '') IS NOT NULL AND ss.project_code=bo.project_code)
               OR (NULLIF(bo.serial_no, '') IS NOT NULL AND ss.serial_no=bo.serial_no)
        ) ship ON TRUE
        LEFT JOIN LATERAL (
            SELECT COALESCE(SUM(balance), 0) AS receivable_balance
            FROM customer_receivables cr
            WHERE cr.source_id=bo.id
               OR (bo.cost_object_id IS NOT NULL AND cr.cost_object_id=bo.cost_object_id)
               OR (NULLIF(bo.project_code, '') IS NOT NULL AND cr.project_code=bo.project_code)
               OR (NULLIF(bo.serial_no, '') IS NOT NULL AND cr.serial_no=bo.serial_no)
        ) ar ON TRUE
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS service_order_count
            FROM machine_service_orders mso
            WHERE mso.sales_order_id=bo.id
               OR (bo.cost_object_id IS NOT NULL AND mso.cost_object_id=bo.cost_object_id)
               OR (NULLIF(bo.project_code, '') IS NOT NULL AND mso.project_code=bo.project_code)
               OR (NULLIF(bo.serial_no, '') IS NOT NULL AND mso.serial_no=bo.serial_no)
        ) service ON TRUE
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS service_card_count
            FROM machine_service_cards sc
            WHERE sc.sales_order_id=bo.id
               OR (bo.cost_object_id IS NOT NULL AND sc.cost_object_id=bo.cost_object_id)
               OR (NULLIF(bo.project_code, '') IS NOT NULL AND sc.project_code=bo.project_code)
               OR (NULLIF(bo.serial_no, '') IS NOT NULL AND sc.serial_no=bo.serial_no)
        ) card ON TRUE
        LEFT JOIN LATERAL (
            SELECT COALESCE(SUM(sp.balance), 0) AS payable_balance
            FROM supplier_payables sp
            LEFT JOIN purchase_orders po_ap ON po_ap.id=sp.doc_id OR po_ap.order_no=sp.doc_no
            LEFT JOIN subcontract_orders sc_ap ON sp.doc_type='subcontract_order' AND (sc_ap.id=sp.doc_id OR sc_ap.order_no=sp.doc_no)
            WHERE (bo.cost_object_id IS NOT NULL AND (po_ap.cost_object_id=bo.cost_object_id OR sc_ap.cost_object_id=bo.cost_object_id))
               OR (NULLIF(bo.project_code, '') IS NOT NULL AND (po_ap.project_code=bo.project_code OR sc_ap.project_code=bo.project_code))
               OR (NULLIF(bo.serial_no, '') IS NOT NULL AND (po_ap.serial_no=bo.serial_no OR sc_ap.serial_no=bo.serial_no))
        ) ap ON TRUE
        LEFT JOIN LATERAL (
            SELECT
                COALESCE((
                    SELECT SUM(total_amount)
                    FROM purchase_orders po_cost
                    WHERE (bo.cost_object_id IS NOT NULL AND po_cost.cost_object_id=bo.cost_object_id)
                       OR (NULLIF(bo.project_code, '') IS NOT NULL AND po_cost.project_code=bo.project_code)
                       OR (NULLIF(bo.serial_no, '') IS NOT NULL AND po_cost.serial_no=bo.serial_no)
                ), 0)
                + COALESCE((
                    SELECT SUM(total_amount)
                    FROM subcontract_orders sc_cost
                    WHERE (bo.cost_object_id IS NOT NULL AND sc_cost.cost_object_id=bo.cost_object_id)
                       OR (NULLIF(bo.project_code, '') IS NOT NULL AND sc_cost.project_code=bo.project_code)
                       OR (NULLIF(bo.serial_no, '') IS NOT NULL AND sc_cost.serial_no=bo.serial_no)
                ), 0)
                + COALESCE((
                    SELECT SUM(woc.total_cost)
                    FROM work_order_costs woc
                    LEFT JOIN work_orders wo_cost ON wo_cost.id=woc.work_order_id
                    WHERE (bo.cost_object_id IS NOT NULL AND woc.cost_object_id=bo.cost_object_id)
                       OR (NULLIF(bo.project_code, '') IS NOT NULL AND wo_cost.project_code=bo.project_code)
                       OR (NULLIF(bo.serial_no, '') IS NOT NULL AND wo_cost.serial_no=bo.serial_no)
                ), 0)
                + COALESCE((
                    SELECT SUM(total_cost)
                    FROM machine_service_orders mso_cost
                    WHERE mso_cost.sales_order_id=bo.id
                       OR (bo.cost_object_id IS NOT NULL AND mso_cost.cost_object_id=bo.cost_object_id)
                       OR (NULLIF(bo.project_code, '') IS NOT NULL AND mso_cost.project_code=bo.project_code)
                       OR (NULLIF(bo.serial_no, '') IS NOT NULL AND mso_cost.serial_no=bo.serial_no)
                ), 0) AS project_cost
        ) cost ON TRUE
        ORDER BY shortage_lines DESC, bo.delivery_date NULLS LAST, bo.id DESC
        """,
        tuple(params + [sql_limit, sql_offset]),
    )

    today = today or datetime.now().date()
    rows = filter_clean_rows(rows, "order_no", "customer_name", "project_code", "serial_no", "status")
    for row in rows:
        row["status"] = clean_display_text(row.get("status"), "未知状态")
        row["is_overdue"] = bool(row.get("delivery_date") and row.get("delivery_date") < today)
        row["delivery_state"], row["delivery_class"] = _project_delivery_state(row.get("delivery_date"), today)
        row["gross_profit"] = as_decimal(row.get("total_amount")) - as_decimal(row.get("project_cost"))
        row["gross_margin"] = (row["gross_profit"] / as_decimal(row.get("total_amount")) * 100) if as_decimal(row.get("total_amount")) else 0
        acceptance_gaps = []
        if not row.get("project_code") or not row.get("serial_no"):
            acceptance_gaps.append("项目/机号")
        if row.get("shortage_lines"):
            acceptance_gaps.append("缺料")
        if as_decimal(row.get("pending_purchase_qty")) > 0:
            acceptance_gaps.append("采购未到")
        if row.get("open_work_order_count"):
            acceptance_gaps.append("未完工单")
        if not row.get("shipment_count"):
            acceptance_gaps.append("未发货")
        if row.get("shipment_count") and not row.get("service_card_count"):
            acceptance_gaps.append("服务档案")
        if as_decimal(row.get("receivable_balance")) > 0:
            acceptance_gaps.append("应收")
        if as_decimal(row.get("payable_balance")) > 0:
            acceptance_gaps.append("应付")
        if as_decimal(row.get("project_cost")) <= 0:
            acceptance_gaps.append("成本")
        row["acceptance_status"] = "可验收" if not acceptance_gaps else "需关注"
        row["acceptance_class"] = "success" if not acceptance_gaps else "warning"
        row["acceptance_gaps"] = "、".join(acceptance_gaps) if acceptance_gaps else "无"
        row["acceptance_owner_roles"] = _acceptance_owner_roles(acceptance_gaps)
        row["acceptance_primary_gap"], row["acceptance_primary_owner"] = _acceptance_primary_gap(acceptance_gaps)
        if row.get("service_order_count"):
            row["project_stage"] = "售后"
        elif as_decimal(row.get("receivable_balance")) > 0 and as_decimal(row.get("shipped_amount")) > 0:
            row["project_stage"] = "回款"
        elif row.get("shipment_count"):
            row["project_stage"] = "发货"
        elif row.get("open_work_order_count"):
            row["project_stage"] = "生产"
        elif row.get("shortage_lines") or row.get("pending_purchase_qty"):
            row["project_stage"] = "齐套/采购"
        else:
            row["project_stage"] = "销售"
        if row["is_overdue"] and row.get("shortage_lines"):
            row["risk_level"] = "高风险"
            row["risk_class"] = "danger"
        elif row["is_overdue"] or row.get("shortage_lines") or as_decimal(row.get("receivable_balance")) > 0:
            row["risk_level"] = "需关注"
            row["risk_class"] = "warning"
        else:
            row["risk_level"] = "正常"
            row["risk_class"] = "success"
        row["next_action"], row["owner_role"], row["blocked_reason"] = _project_next_action(row, as_decimal)

    all_rows_for_metrics = list(rows)
    if risk == "shortage":
        rows = [row for row in rows if row.get("shortage_lines")]
    elif risk == "overdue":
        rows = [row for row in rows if row.get("is_overdue")]
    elif risk == "receivable":
        rows = [row for row in rows if as_decimal(row.get("receivable_balance")) > 0]
    elif risk == "open_work":
        rows = [row for row in rows if row.get("open_work_order_count")]
    elif risk == "blocked":
        rows = [row for row in rows if row.get("blocked_reason") != "暂无阻塞"]
    elif risk == "acceptance_blocked":
        rows = [row for row in rows if row.get("acceptance_status") != "可验收"]
    elif risk == "acceptance_ready":
        rows = [row for row in rows if row.get("acceptance_status") == "可验收"]
    if owner:
        rows = [row for row in rows if owner in (row.get("acceptance_owner_roles") or "")]
    if primary_owner:
        rows = [row for row in rows if primary_owner == (row.get("acceptance_primary_owner") or "")]

    if export_requested:
        return _project_csv_response(rows)

    filtered_count = len(rows)
    if needs_python_filter:
        result_count = filtered_count
        total_pages = max(1, ((result_count - 1) // per_page) + 1) if result_count else 1
        page = min(page, total_pages)
        start_index = (page - 1) * per_page
        visible_rows = rows[start_index : start_index + per_page]
    else:
        count_row = query_one(
            f"""
            SELECT COUNT(*) AS total
            FROM sales_orders so
            LEFT JOIN customers c ON c.id=so.customer_id
            {where_sql}
            """,
            tuple(params),
        ) or {}
        result_count = count_row.get("total", 0) or 0
        total_pages = max(1, ((result_count - 1) // per_page) + 1) if result_count else 1
        visible_rows = rows
        start_index = (page - 1) * per_page
    showing_start = start_index + 1 if visible_rows else 0
    showing_end = start_index + len(visible_rows)

    summary = query_one(
        """
        SELECT COUNT(*) AS total_projects,
               COUNT(*) FILTER (WHERE COALESCE(status, '') NOT IN ('已关闭','已作废','已完成')) AS active_projects,
               COUNT(*) FILTER (WHERE delivery_date < CURRENT_DATE AND COALESCE(status, '') NOT IN ('已关闭','已作废','已完成')) AS overdue_projects,
               COALESCE(SUM(total_amount), 0) AS sales_amount
        FROM sales_orders
        """
    ) or {}
    status_rows = query_rows(
        """
        SELECT COALESCE(status, '未定') AS status, COUNT(*) AS count
        FROM sales_orders
        GROUP BY COALESCE(status, '未定')
        ORDER BY count DESC, status
        LIMIT 10
        """
    )
    status_rows = filter_clean_rows(status_rows, "status")
    global_shortage = query_one(
        """
        SELECT COUNT(*) AS shortage_lines,
               COUNT(DISTINCT COALESCE(project_code, '') || '|' || COALESCE(serial_no, '')) AS shortage_projects
        FROM mrp_requirements
        WHERE COALESCE(shortage_quantity, 0) > 0
        """
    ) or {}
    metrics = [
        {"label": "项目总数", "value": summary.get("total_projects", 0), "hint": "销售项目口径"},
        {"label": "进行中", "value": summary.get("active_projects", 0), "hint": "未关闭项目"},
        {"label": "可验收", "value": len([row for row in all_rows_for_metrics if row.get("acceptance_status") == "可验收"]), "hint": "当前候选项目"},
        {"label": "需关注", "value": len([row for row in all_rows_for_metrics if row.get("acceptance_status") != "可验收"]), "hint": "存在验收缺口"},
        {"label": "缺料项目", "value": global_shortage.get("shortage_projects", 0), "hint": f"{global_shortage.get('shortage_lines', 0)} 行缺料"},
        {"label": "逾期交付", "value": summary.get("overdue_projects", 0), "hint": "交期早于今天"},
    ]
    owner_options = [
        "销售/项目",
        "计划/采购",
        "采购",
        "生产",
        "仓库/销售",
        "售后",
        "财务/销售",
        "采购/财务",
        "财务/成本",
    ]
    return render_template(
        "project_ledger.html",
        title="项目/机号台账",
        subtitle="按销售订单、项目号、机号追踪采购、生产、发货、回款和售后",
        rows=visible_rows,
        metrics=metrics,
        status_rows=status_rows,
        owner_options=owner_options,
        filters={"keyword": keyword, "status": status, "risk": risk, "owner": owner, "primary_owner": primary_owner},
        pagination={
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "result_count": result_count,
            "showing_start": showing_start,
            "showing_end": showing_end,
            "has_prev": page > 1,
            "has_next": page < total_pages,
        },
    )


def render_project_ledger_detail(
    order_id,
    query_one,
    query_rows,
    project_kit_rows,
    project_items_without_bom,
    project_finance_summary,
    build_kit_summary,
):
    order = query_one(
        """
        SELECT so.*, c.name AS customer_name
        FROM sales_orders so
        LEFT JOIN customers c ON c.id=so.customer_id
        WHERE so.id=%s
        """,
        (order_id,),
    )
    project_code = order.get("project_code") if order else None
    serial_no = order.get("serial_no") if order else None
    cost_object_id = order.get("cost_object_id") if order else None
    order_items = query_rows(
        """
        SELECT soi.*, p.code AS product_code, p.name AS product_name,
               p.specification, COALESCE(p.unit, '') AS product_unit
        FROM sales_order_items soi
        LEFT JOIN products p ON p.id=soi.product_id
        WHERE soi.order_id=%s
        ORDER BY soi.id
        """,
        (order_id,),
    )
    kit_rows = project_kit_rows(order_id, project_code, serial_no, cost_object_id) if order else []
    no_bom_items = project_items_without_bom(order_id) if order else []
    kit_summary = build_kit_summary(kit_rows, no_bom_items)
    finance_summary = project_finance_summary(order, project_code, serial_no, cost_object_id) if order else {}
    engineering_readiness = _project_engineering_readiness(query_one, order, kit_summary) if order else {}
    context = {
        "order": order,
        "order_items": order_items,
        "kit_requirements": kit_rows,
        "no_bom_items": no_bom_items,
        "kit_summary": kit_summary,
        "engineering_readiness": engineering_readiness,
        "finance_summary": finance_summary,
        "cost_rows": _project_cost_rows(query_rows, order_id, project_code, serial_no, cost_object_id) if order else [],
        "project_events": _project_axis_events(query_rows, order, 80) if order else [],
        "cost_object": query_one("SELECT * FROM cost_objects WHERE id=%s", (cost_object_id,)),
        "shortages": query_rows(
            """
            SELECT mr.*, p.name AS product_name
            FROM mrp_requirements mr
            LEFT JOIN products p ON p.id=mr.product_id
            WHERE (mr.source_document_type='sales_order' AND mr.source_document_id=%s)
               OR (%s IS NOT NULL AND mr.project_code=%s)
               OR (%s IS NOT NULL AND mr.serial_no=%s)
            ORDER BY mr.id DESC LIMIT 50
            """,
            (order_id, project_code, project_code, serial_no, serial_no),
        ),
        "purchase_orders": query_rows("SELECT * FROM purchase_orders WHERE cost_object_id=%s OR project_code=%s OR serial_no=%s LIMIT 50", (cost_object_id, project_code, serial_no)),
        "subcontract_orders": query_rows(
            """
            SELECT sc.*, 0 AS quantity, 0 AS unit_price,
                   COALESCE(s.name, sc.supplier_id::text, '-') AS supplier_name,
                   COALESCE(issue_sum.issued_qty, 0) AS issued_qty,
                   COALESCE(receive_sum.received_qty, 0) AS received_qty,
                   COALESCE(receive_sum.scrap_qty, 0) AS scrap_qty,
                   0 AS pending_receive_qty,
                   COALESCE(payable_sum.payable_amount, 0) AS payable_amount,
                   COALESCE(payable_sum.payable_balance, 0) AS payable_balance
            FROM subcontract_orders sc
            LEFT JOIN suppliers s ON s.id=sc.supplier_id
            LEFT JOIN LATERAL (
                SELECT COALESCE(SUM(total_quantity), 0) AS issued_qty
                FROM subcontract_issue_orders sio
                WHERE sio.subcontract_order_id=sc.id
                  AND COALESCE(sio.status, '') NOT IN ('已作废','void','cancelled')
            ) issue_sum ON TRUE
            LEFT JOIN LATERAL (
                SELECT COALESCE(SUM(total_quantity), 0) AS received_qty,
                       COALESCE(SUM(total_scrap), 0) AS scrap_qty
                FROM subcontract_receive_orders sro
                WHERE sro.subcontract_order_id=sc.id
                  AND COALESCE(sro.status, '') NOT IN ('已作废','void','cancelled')
            ) receive_sum ON TRUE
            LEFT JOIN LATERAL (
                SELECT COALESCE(SUM(amount), 0) AS payable_amount,
                       COALESCE(SUM(balance), 0) AS payable_balance
                FROM supplier_payables sp
                WHERE sp.doc_type='subcontract_order'
                  AND (sp.doc_id=sc.id OR sp.doc_no=sc.order_no)
            ) payable_sum ON TRUE
            WHERE (%s IS NOT NULL AND sc.project_code=%s)
               OR (%s IS NOT NULL AND sc.serial_no=%s)
            ORDER BY sc.id DESC
            LIMIT 50
            """,
            (project_code, project_code, serial_no, serial_no),
        ),
        "work_orders": query_rows(
            """
            SELECT wo.*, COALESCE(material.required_qty, 0) AS required_issue_qty,
                   COALESCE(material.issued_qty, 0) AS issued_qty,
                   COALESCE(material.returned_qty, 0) AS returned_qty,
                   GREATEST(COALESCE(material.required_qty, 0)-COALESCE(material.issued_qty, 0)+COALESCE(material.returned_qty, 0), 0) AS pending_issue_qty,
                   COALESCE(completed.completed_qty, 0) AS completed_qty
            FROM work_orders wo
            LEFT JOIN LATERAL (
                SELECT COALESCE(SUM(required_qty), 0) AS required_qty,
                       COALESCE(SUM(issued_qty), 0) AS issued_qty,
                       COALESCE(SUM(returned_qty), 0) AS returned_qty
                FROM wo_material_items mi
                WHERE mi.wo_id=wo.id
            ) material ON TRUE
            LEFT JOIN LATERAL (
                SELECT COALESCE(SUM(qty), 0) AS completed_qty
                FROM wo_complete_items wc
                WHERE wc.wo_id=wo.id
            ) completed ON TRUE
            WHERE (%s IS NOT NULL AND wo.cost_object_id=%s)
               OR (%s IS NOT NULL AND wo.project_code=%s)
               OR (%s IS NOT NULL AND wo.serial_no=%s)
            ORDER BY wo.id DESC
            LIMIT 50
            """,
            (cost_object_id, cost_object_id, project_code, project_code, serial_no, serial_no),
        ),
        "quality_inspections": query_rows(
            """
            SELECT qi.*, wo.wo_no, p.code AS product_code, p.name AS product_name
            FROM quality_inspection_records qi
            LEFT JOIN work_orders wo
              ON qi.source_document_type='work_order' AND wo.id=qi.source_document_id
            LEFT JOIN products p ON p.id=qi.product_id
            WHERE (%s IS NOT NULL AND qi.cost_object_id=%s)
               OR (%s IS NOT NULL AND qi.project_code=%s)
               OR (%s IS NOT NULL AND qi.serial_no=%s)
            ORDER BY qi.id DESC
            LIMIT 50
            """,
            (cost_object_id, cost_object_id, project_code, project_code, serial_no, serial_no),
        ),
        "shipments": query_rows(
            """
            SELECT ss.*, sc.id AS service_card_id,
                   COALESCE(sc.status, '未建档') AS service_card_status,
                   sc.machine_model
            FROM sales_shipments ss
            LEFT JOIN machine_service_cards sc
              ON sc.sales_order_id=ss.order_id AND sc.serial_no=ss.serial_no
            WHERE ss.order_id=%s OR ss.project_code=%s OR ss.serial_no=%s
            ORDER BY ss.id DESC
            LIMIT 50
            """,
            (order_id, project_code, serial_no),
        ),
        "receivables": query_rows("SELECT * FROM customer_receivables WHERE source_id=%s OR project_code=%s OR serial_no=%s LIMIT 50", (order_id, project_code, serial_no)),
        "service_orders": query_rows("SELECT * FROM machine_service_orders WHERE sales_order_id=%s OR project_code=%s OR serial_no=%s LIMIT 50", (order_id, project_code, serial_no)),
        "service_cards": query_rows("SELECT * FROM machine_service_cards WHERE sales_order_id=%s OR project_code=%s OR serial_no=%s LIMIT 50", (order_id, project_code, serial_no)),
        "service_acceptances": query_rows("SELECT * FROM machine_service_acceptance_checks WHERE sales_order_id=%s OR project_code=%s OR serial_no=%s LIMIT 50", (order_id, project_code, serial_no)),
        "service_visits": query_rows("SELECT * FROM machine_service_return_visits WHERE sales_order_id=%s OR project_code=%s OR serial_no=%s LIMIT 50", (order_id, project_code, serial_no)),
        "service_rmas": query_rows("SELECT * FROM machine_service_rmas WHERE sales_order_id=%s OR project_code=%s OR serial_no=%s LIMIT 50", (order_id, project_code, serial_no)),
    }
    next_action, owner_role, blocked_reason = _project_next_action(
        {
            "project_code": project_code,
            "serial_no": serial_no,
            "shortage_lines": (context["kit_summary"] or {}).get("shortage_count"),
            "pending_purchase_qty": sum([as_decimal_safe(row.get("pending_purchase_qty")) for row in context["purchase_orders"]]),
            "open_work_order_count": len([row for row in context["work_orders"] if (row.get("status") or "") not in {"已完工", "已关闭", "已作废"}]),
            "shipment_count": len(context["shipments"]),
            "receivable_balance": (finance_summary or {}).get("receivable_balance"),
            "service_order_count": len(context["service_orders"]),
        },
        lambda value: as_decimal_safe(value),
    )
    if engineering_readiness and not engineering_readiness.get("ready"):
        next_action = engineering_readiness.get("next_action")
        owner_role = engineering_readiness.get("owner_role")
        blocked_reason = engineering_readiness.get("blocked_reason")
    context["project_next_action"] = next_action
    context["project_owner_role"] = owner_role
    context["project_blocked_reason"] = blocked_reason
    context["delivery_state"], context["delivery_class"] = _project_delivery_state(order.get("delivery_date"), datetime.now().date()) if order else ("未定", "secondary")
    for row in context["subcontract_orders"]:
        row["execution_status"], row["next_step"] = _subcontract_project_execution(row)
    for row in context["work_orders"]:
        row["issue_state"], row["next_step"], row["owner_role"] = _work_order_project_execution(row)
    context["project_diagnostics"] = _build_project_diagnostics(order, context, finance_summary)
    if engineering_readiness and not engineering_readiness.get("ready"):
        context["project_diagnostics"].insert(
            0,
            {
                "level": "danger",
                "label": "工程准备未就绪",
                "text": engineering_readiness.get("blocked_reason") or "技术确认、BOM或图纸未就绪。",
                "owner": engineering_readiness.get("owner_role") or "技术/工艺",
            },
        )
    context["pilot_answers"] = _pilot_acceptance_answers(order, context, finance_summary)
    context["pilot_acceptance_summary"] = _pilot_acceptance_summary(context["pilot_answers"])
    return render_template("project_trace_detail.html", **context)


def register_routes(app, login_required, ledger_view, detail_view):
    app.add_url_rule(
        "/projects",
        endpoint="project_ledger_readonly",
        view_func=login_required(ledger_view),
        methods=["GET"],
    )
    app.add_url_rule(
        "/projects/<int:order_id>",
        endpoint="project_ledger_detail_readonly",
        view_func=login_required(detail_view),
        methods=["GET"],
    )


def register_project_ledger_routes(
    app,
    login_required,
    query_one,
    query_rows,
    as_decimal,
    money_metric,
    filter_clean_rows,
    clean_display_text,
    project_kit_rows,
    project_items_without_bom,
    project_finance_summary,
    build_kit_summary,
):
    @app.get("/projects")
    @login_required
    def project_ledger():
        return render_project_ledger(
            query_one,
            query_rows,
            as_decimal,
            money_metric,
            filter_clean_rows,
            clean_display_text,
        )

    @app.get("/projects/<int:order_id>")
    @login_required
    def project_ledger_detail(order_id):
        return render_project_ledger_detail(
            order_id,
            query_one,
            query_rows,
            project_kit_rows,
            project_items_without_bom,
            project_finance_summary,
            build_kit_summary,
        )

    @app.get("/projects/machine/<path:serial_no>")
    @login_required
    def project_machine_ledger(serial_no):
        order = _project_axis_order(query_one, serial_no=serial_no)
        if order:
            return redirect(f"/projects/{order.get('id')}")
        return redirect(f"/projects?{urlencode({'keyword': serial_no})}")

    @app.get("/projects/project/<path:project_code>")
    @login_required
    def project_code_ledger(project_code):
        order = _project_axis_order(query_one, project_code=project_code)
        if order:
            return redirect(f"/projects/{order.get('id')}")
        return redirect(f"/projects?{urlencode({'keyword': project_code})}")

    @app.get("/api/project-machine-ledger/search")
    @login_required
    def project_machine_ledger_search_api():
        keyword = (request.args.get("keyword") or request.args.get("q") or "").strip()
        try:
            limit = int(request.args.get("limit") or "20")
        except ValueError:
            limit = 20
        limit = min(max(limit, 1), 50)
        rows = _project_axis_search_rows(query_rows, keyword, limit)
        return jsonify(
            _json_safe(
                {
                    "keyword": keyword,
                    "count": len(rows),
                    "rows": rows,
                }
            )
        )

    @app.get("/api/project-machine-ledger/resolve")
    @login_required
    def project_machine_ledger_resolve_api():
        keyword = (request.args.get("keyword") or request.args.get("q") or "").strip()
        order = _project_axis_order(query_one, keyword=keyword)
        if not order:
            return jsonify({"found": False, "keyword": keyword}), 404
        return jsonify(
            _json_safe(
                {
                    "found": True,
                    "keyword": keyword,
                    "order": order,
                    "ledger_url": f"/projects/{order.get('id')}",
                    "machine_url": f"/projects/machine/{order.get('serial_no')}" if order.get("serial_no") else None,
                    "project_url": f"/projects/project/{order.get('project_code')}" if order.get("project_code") else None,
                    "overview_api": f"/api/project-machine-ledger/order/{order.get('id')}/overview",
                    "events_api": f"/api/project-machine-ledger/order/{order.get('id')}/events",
                }
            )
        )

    @app.get("/api/project-machine-ledger/machine/<path:serial_no>/overview")
    @login_required
    def project_machine_ledger_overview_api(serial_no):
        order = _project_axis_order(query_one, serial_no=serial_no)
        if not order:
            return jsonify({"found": False, "serial_no": serial_no}), 404

        return jsonify(
            _json_safe(
                _project_axis_overview_payload(
                    query_one,
                    order,
                    project_kit_rows,
                    project_items_without_bom,
                    project_finance_summary,
                    build_kit_summary,
                )
            )
        )

    @app.get("/api/project-machine-ledger/project/<path:project_code>/overview")
    @login_required
    def project_code_ledger_overview_api(project_code):
        order = _project_axis_order(query_one, project_code=project_code)
        if not order:
            return jsonify({"found": False, "project_code": project_code}), 404
        return jsonify(
            _json_safe(
                _project_axis_overview_payload(
                    query_one,
                    order,
                    project_kit_rows,
                    project_items_without_bom,
                    project_finance_summary,
                    build_kit_summary,
                )
            )
        )

    @app.get("/api/project-machine-ledger/order/<int:order_id>/overview")
    @login_required
    def project_order_ledger_overview_api(order_id):
        order = _project_order_by_id(query_one, order_id)
        if not order:
            return jsonify({"found": False, "order_id": order_id}), 404
        return jsonify(
            _json_safe(
                _project_axis_overview_payload(
                    query_one,
                    order,
                    project_kit_rows,
                    project_items_without_bom,
                    project_finance_summary,
                    build_kit_summary,
                )
            )
        )

    @app.get("/api/project-machine-ledger/machine/<path:serial_no>/engineering-readiness")
    @login_required
    def project_machine_ledger_engineering_readiness_api(serial_no):
        order = _project_axis_order(query_one, serial_no=serial_no)
        if not order:
            return jsonify({"found": False, "serial_no": serial_no}), 404
        return jsonify(
            _json_safe(
                _project_axis_engineering_readiness_payload(
                    query_one,
                    order,
                    project_kit_rows,
                    project_items_without_bom,
                    build_kit_summary,
                )
            )
        )

    @app.get("/api/project-machine-ledger/project/<path:project_code>/engineering-readiness")
    @login_required
    def project_code_ledger_engineering_readiness_api(project_code):
        order = _project_axis_order(query_one, project_code=project_code)
        if not order:
            return jsonify({"found": False, "project_code": project_code}), 404
        return jsonify(
            _json_safe(
                _project_axis_engineering_readiness_payload(
                    query_one,
                    order,
                    project_kit_rows,
                    project_items_without_bom,
                    build_kit_summary,
                )
            )
        )

    @app.get("/api/project-machine-ledger/order/<int:order_id>/engineering-readiness")
    @login_required
    def project_order_ledger_engineering_readiness_api(order_id):
        order = _project_order_by_id(query_one, order_id)
        if not order:
            return jsonify({"found": False, "order_id": order_id}), 404
        return jsonify(
            _json_safe(
                _project_axis_engineering_readiness_payload(
                    query_one,
                    order,
                    project_kit_rows,
                    project_items_without_bom,
                    build_kit_summary,
                )
            )
        )

    @app.get("/api/project-machine-ledger/machine/<path:serial_no>/procurement-closure")
    @login_required
    def project_machine_ledger_procurement_closure_api(serial_no):
        order = _project_axis_order(query_one, serial_no=serial_no)
        if not order:
            return jsonify({"found": False, "serial_no": serial_no}), 404
        return jsonify(
            _json_safe(
                _project_axis_procurement_closure_payload(
                    query_one,
                    order,
                    project_kit_rows,
                    project_items_without_bom,
                    build_kit_summary,
                )
            )
        )

    @app.get("/api/project-machine-ledger/project/<path:project_code>/procurement-closure")
    @login_required
    def project_code_ledger_procurement_closure_api(project_code):
        order = _project_axis_order(query_one, project_code=project_code)
        if not order:
            return jsonify({"found": False, "project_code": project_code}), 404
        return jsonify(
            _json_safe(
                _project_axis_procurement_closure_payload(
                    query_one,
                    order,
                    project_kit_rows,
                    project_items_without_bom,
                    build_kit_summary,
                )
            )
        )

    @app.get("/api/project-machine-ledger/order/<int:order_id>/procurement-closure")
    @login_required
    def project_order_ledger_procurement_closure_api(order_id):
        order = _project_order_by_id(query_one, order_id)
        if not order:
            return jsonify({"found": False, "order_id": order_id}), 404
        return jsonify(
            _json_safe(
                _project_axis_procurement_closure_payload(
                    query_one,
                    order,
                    project_kit_rows,
                    project_items_without_bom,
                    build_kit_summary,
                )
            )
        )

    @app.get("/api/project-machine-ledger/machine/<path:serial_no>/production-closure")
    @login_required
    def project_machine_ledger_production_closure_api(serial_no):
        order = _project_axis_order(query_one, serial_no=serial_no)
        if not order:
            return jsonify({"found": False, "serial_no": serial_no}), 404
        return jsonify(_json_safe(_project_axis_production_closure_payload(query_one, order)))

    @app.get("/api/project-machine-ledger/project/<path:project_code>/production-closure")
    @login_required
    def project_code_ledger_production_closure_api(project_code):
        order = _project_axis_order(query_one, project_code=project_code)
        if not order:
            return jsonify({"found": False, "project_code": project_code}), 404
        return jsonify(_json_safe(_project_axis_production_closure_payload(query_one, order)))

    @app.get("/api/project-machine-ledger/order/<int:order_id>/production-closure")
    @login_required
    def project_order_ledger_production_closure_api(order_id):
        order = _project_order_by_id(query_one, order_id)
        if not order:
            return jsonify({"found": False, "order_id": order_id}), 404
        return jsonify(_json_safe(_project_axis_production_closure_payload(query_one, order)))

    @app.get("/api/project-machine-ledger/engineering-readiness/alerts")
    @login_required
    def project_engineering_readiness_alerts_api():
        try:
            limit = int(request.args.get("limit") or "20")
        except ValueError:
            limit = 20
        limit = min(max(limit, 1), 100)
        candidates = query_rows(
            """
            SELECT so.id, so.order_no, so.order_date, so.project_code, so.serial_no,
                   so.delivery_date, so.status, so.total_amount, so.cost_object_id,
                   c.name AS customer_name
            FROM sales_orders so
            LEFT JOIN customers c ON c.id=so.customer_id
            WHERE COALESCE(so.status, '') NOT IN ('已作废','作废','void','cancelled')
              AND (
                    so.project_code IS NOT NULL
                    OR so.serial_no IS NOT NULL
                    OR EXISTS (SELECT 1 FROM sales_order_items soi WHERE soi.order_id=so.id)
              )
            ORDER BY so.delivery_date ASC NULLS LAST, so.id DESC
            LIMIT 200
            """
        )
        rows = []
        for order in candidates:
            payload = _project_axis_engineering_readiness_payload(
                query_one,
                order,
                project_kit_rows,
                project_items_without_bom,
                build_kit_summary,
            )
            readiness = payload.get("engineering_readiness") or {}
            if readiness.get("ready"):
                continue
            rows.append(
                {
                    "order_id": order.get("id"),
                    "order_no": order.get("order_no"),
                    "project_code": order.get("project_code"),
                    "serial_no": order.get("serial_no"),
                    "customer_name": order.get("customer_name"),
                    "delivery_date": order.get("delivery_date"),
                    "ledger_url": payload.get("ledger_url"),
                    "technical_confirmation_url": (
                        f"/engineering/technical-confirmations/{readiness.get('confirmation', {}).get('id')}"
                        if readiness.get("confirmation")
                        else f"/engineering/technical-confirmations/new?{urlencode({'sales_order_id': order.get('id')})}"
                    ),
                    "status": readiness.get("status"),
                    "blocked_reason": readiness.get("blocked_reason"),
                    "next_action": readiness.get("next_action"),
                    "owner_role": readiness.get("owner_role"),
                }
            )
            if len(rows) >= limit:
                break
        return jsonify(_json_safe({"count": len(rows), "rows": rows}))

    @app.get("/api/project-machine-ledger/assistant-context")
    @login_required
    def project_machine_ledger_assistant_context_api():
        keyword = (request.args.get("keyword") or request.args.get("q") or "").strip()
        if not keyword:
            return jsonify({"found": False, "msg": "请提供项目号、机号或销售订单号。"}), 400
        order = _project_axis_order(query_one, keyword=keyword)
        if not order:
            return jsonify({"found": False, "keyword": keyword}), 404
        return jsonify(
            _json_safe(
                _project_axis_assistant_context(
                    query_one,
                    query_rows,
                    order,
                    project_kit_rows,
                    project_items_without_bom,
                    build_kit_summary,
                )
            )
        )

    @app.get("/api/project-machine-ledger/machine/<path:serial_no>/events")
    @login_required
    def project_machine_ledger_events_api(serial_no):
        order = _project_axis_order(query_one, serial_no=serial_no)
        if not order:
            return jsonify({"found": False, "serial_no": serial_no, "events": []}), 404
        try:
            limit = int(request.args.get("limit") or "80")
        except ValueError:
            limit = 80
        limit = min(max(limit, 1), 200)
        events = _project_axis_events(query_rows, order, limit)
        return jsonify(
            _json_safe(
                {
                    "found": True,
                    "order_id": order.get("id"),
                    "project_code": order.get("project_code"),
                    "serial_no": order.get("serial_no"),
                    "ledger_url": f"/projects/{order.get('id')}",
                    "count": len(events),
                    "events": events,
                }
            )
        )

    @app.get("/api/project-machine-ledger/project/<path:project_code>/events")
    @login_required
    def project_code_ledger_events_api(project_code):
        order = _project_axis_order(query_one, project_code=project_code)
        if not order:
            return jsonify({"found": False, "project_code": project_code, "events": []}), 404
        try:
            limit = int(request.args.get("limit") or "80")
        except ValueError:
            limit = 80
        limit = min(max(limit, 1), 200)
        events = _project_axis_events(query_rows, order, limit)
        return jsonify(
            _json_safe(
                {
                    "found": True,
                    "order_id": order.get("id"),
                    "project_code": order.get("project_code"),
                    "serial_no": order.get("serial_no"),
                    "ledger_url": f"/projects/{order.get('id')}",
                    "count": len(events),
                    "events": events,
                }
            )
        )

    @app.get("/api/project-machine-ledger/order/<int:order_id>/events")
    @login_required
    def project_order_ledger_events_api(order_id):
        order = _project_order_by_id(query_one, order_id)
        if not order:
            return jsonify({"found": False, "order_id": order_id, "events": []}), 404
        try:
            limit = int(request.args.get("limit") or "80")
        except ValueError:
            limit = 80
        limit = min(max(limit, 1), 200)
        events = _project_axis_events(query_rows, order, limit)
        return jsonify(
            _json_safe(
                {
                    "found": True,
                    "order_id": order.get("id"),
                    "project_code": order.get("project_code"),
                    "serial_no": order.get("serial_no"),
                    "ledger_url": f"/projects/{order.get('id')}",
                    "count": len(events),
                    "events": events,
                }
            )
        )
