"""Purchase module routes: dashboard, order list, order form, and receipt readiness helpers."""
from datetime import datetime

from flask import render_template

RECEIVE_READY_STATUSES = {"已审核", "已审批", "待收货", "部分收货"}


def render_purchase_dashboard(
    query_one,
    query_rows,
    count_rows,
    as_decimal,
    status_label,
    filter_clean_rows,
    money_metric,
    qty_metric,
    purchase_suggestion_rows,
    request_args,
    back_url="/purchase-orders",
    document_list=False,
    scope_clause="",
    scope_params=None,
):
    keyword = (request_args.get("keyword") or request_args.get("q") or request_args.get("search") or "").strip()
    status = (request_args.get("status") or "").strip()
    supplier_id = (request_args.get("supplier_id") or "").strip()
    risk = (request_args.get("risk") or "").strip()
    date_from = (request_args.get("date_from") or request_args.get("date_start") or "").strip()
    date_to = (request_args.get("date_to") or request_args.get("date_end") or "").strip()
    scope_params = list(scope_params or [])

    where_parts = []
    params = []
    if keyword:
        where_parts.append(
            "(po.order_no ILIKE %s OR po.project_code ILIKE %s OR po.cabinet_no ILIKE %s OR s.name ILIKE %s)"
        )
        params.extend([f"%{keyword}%"] * 4)
    if status:
        where_parts.append("COALESCE(po.status, '')=%s")
        params.append(status)
    if supplier_id.isdigit():
        where_parts.append("po.supplier_id=%s")
        params.append(int(supplier_id))
    if date_from:
        where_parts.append("po.order_date >= %s")
        params.append(date_from)
    if date_to:
        where_parts.append("po.order_date <= %s")
        params.append(date_to)
    if scope_clause:
        where_parts.append(scope_clause.lstrip().removeprefix("AND").strip() or "1=1")
        params.extend(scope_params)
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

    pending_summary = query_one(
        """
        SELECT COUNT(DISTINCT po.id) AS order_count,
               COALESCE(SUM(GREATEST(COALESCE(poi.quantity,0)-COALESCE(poi.received_qty,0),0)), 0) AS pending_qty,
               COALESCE(SUM(GREATEST(COALESCE(poi.quantity,0)-COALESCE(poi.received_qty,0),0) * COALESCE(poi.unit_price,0)), 0) AS pending_amount,
               COUNT(DISTINCT po.id) FILTER (WHERE po.expected_date < CURRENT_DATE) AS overdue_count
        FROM purchase_orders po
        JOIN purchase_order_items poi ON poi.order_id=po.id
        WHERE COALESCE(po.status, '') NOT IN ('已收货','已关闭','已作废','closed','completed')
          AND GREATEST(COALESCE(poi.quantity,0)-COALESCE(poi.received_qty,0),0) > 0
        """
    ) or {}
    payable_summary = query_one(
        """
        SELECT COALESCE(SUM(balance), 0) AS balance,
               COUNT(*) FILTER (WHERE COALESCE(balance, 0) > 0) AS open_count
        FROM supplier_payables
        """
    ) or {}
    suggestion_rows = purchase_suggestion_rows(40)
    actionable_suggestions = [row for row in suggestion_rows if as_decimal(row.get("suggestion_qty")) > 0]
    metrics = [
        {"label": "采购单数", "value": count_rows("purchase_orders"), "hint": "全部采购订单"},
        {
            "label": "待收货",
            "value": pending_summary.get("order_count", 0),
            "hint": f"{qty_metric(pending_summary.get('pending_qty', 0))} 未到",
        },
        {"label": "采购建议", "value": len(actionable_suggestions), "hint": "MRP 缺料扣减后仍需处理"},
        {
            "label": "应付余额",
            "value": money_metric(payable_summary.get("balance", 0)),
            "hint": f"{payable_summary.get('open_count', 0)} 笔未清",
        },
    ]
    status_rows = query_rows(
        """
        SELECT status, COUNT(*) AS count
        FROM purchase_orders
        WHERE COALESCE(status, '') <> ''
        GROUP BY status
        ORDER BY count DESC, status
        """
    )
    status_rows = filter_clean_rows(status_rows, "status")
    for row in status_rows:
        row["display_status"] = status_label(row.get("status"))
    suppliers = query_rows(
        """
        SELECT s.id, s.name
        FROM suppliers s
        WHERE s.id IN (SELECT DISTINCT supplier_id FROM purchase_orders WHERE supplier_id IS NOT NULL)
        ORDER BY s.name
        LIMIT 200
        """
    )
    suppliers = filter_clean_rows(suppliers, "name")
    orders = query_rows(
        f"""
        SELECT po.id, po.order_no, po.order_date, po.expected_date, po.project_code, po.cabinet_no,
               po.status, po.total_amount, po.received_amount, s.name AS supplier_name,
               COALESCE(items.item_count, 0) AS item_count,
               COALESCE(items.ordered_qty, 0) AS ordered_qty,
               COALESCE(items.received_qty, 0) AS received_qty,
               COALESCE(items.pending_receive_qty, 0) AS pending_receive_qty,
               COALESCE(items.product_families, '') AS product_families,
               COALESCE(items.bom_versions, '') AS bom_versions,
               COALESCE(ap.payable_balance, 0) AS payable_balance,
               receipts.last_receipt_date
        FROM purchase_orders po
        LEFT JOIN suppliers s ON s.id=po.supplier_id
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS item_count,
                   COALESCE(SUM(quantity), 0) AS ordered_qty,
                   COALESCE(SUM(received_qty), 0) AS received_qty,
                   COALESCE(SUM(GREATEST(COALESCE(quantity,0)-COALESCE(received_qty,0),0)), 0) AS pending_receive_qty,
                   STRING_AGG(DISTINCT NULLIF(COALESCE(pc.name, p.category, ''), ''), ' / ') AS product_families,
                   STRING_AGG(DISTINCT NULLIF(CONCAT_WS(' ', b.bom_no, b.version), ''), ' / ') AS bom_versions
            FROM purchase_order_items poi
            LEFT JOIN products p ON p.id=poi.product_id
            LEFT JOIN product_categories pc ON pc.id=p.category_id
            LEFT JOIN LATERAL (
                SELECT bom_no, version
                FROM boms b
                WHERE b.product_id=poi.product_id AND COALESCE(b.status, '') NOT IN ('停用','inactive','disabled')
                ORDER BY CASE WHEN b.bom_type='production' THEN 0 ELSE 1 END, b.id DESC
                LIMIT 1
            ) b ON TRUE
            WHERE poi.order_id=po.id
        ) items ON TRUE
        LEFT JOIN LATERAL (
            SELECT COALESCE(SUM(balance), 0) AS payable_balance
            FROM supplier_payables sp
            WHERE sp.doc_id=po.id OR sp.doc_no=po.order_no
        ) ap ON TRUE
        LEFT JOIN LATERAL (
            SELECT MAX(pr.receipt_date) AS last_receipt_date
            FROM purchase_receipts pr
            WHERE pr.order_id=po.id
        ) receipts ON TRUE
        {where_sql}
        ORDER BY COALESCE(items.pending_receive_qty, 0) DESC, po.expected_date NULLS LAST, po.id DESC
        LIMIT 120
        """,
        tuple(params),
    )
    orders = filter_clean_rows(orders, "order_no", "supplier_name", "project_code", "cabinet_no", "status")
    today = datetime.now().date()
    filtered_orders = []
    for row in orders:
        row["display_status"] = status_label(row.get("status"))
        for key in ("order_no", "supplier_name", "project_code", "cabinet_no"):
            row[key] = row.get(key)
        pending_qty = as_decimal(row.get("pending_receive_qty"))
        payable_balance = as_decimal(row.get("payable_balance"))
        is_overdue = bool(row.get("expected_date") and row.get("expected_date") < today and pending_qty > 0)
        is_receive_status_ready = row.get("status") in RECEIVE_READY_STATUSES
        has_project_cabinet = bool(row.get("project_code") and row.get("cabinet_no"))
        row["can_receive"] = bool(pending_qty > 0 and is_receive_status_ready and has_project_cabinet)
        row["risk_label"] = "正常"
        row["arrival_alert"] = "按期跟进"
        row["next_action"] = "跟进采购"
        row["blocked_reason"] = ""
        row["owner_role"] = "采购跟单"
        row["condition_label"] = "按项目料到货计划跟踪"
        row["downstream_impact"] = "影响项目齐套、入库、领料和应付"
        if pending_qty > 0:
            row["risk_label"] = "逾期未到" if is_overdue else "待收货"
            row["arrival_alert"] = "预计到货已过，仍有未到数量" if is_overdue else "预计到货未完全入库"
            row["next_action"] = "生成采购入库单" if row["can_receive"] else "补齐收货条件"
            row["owner_role"] = "采购跟单 / 仓库"
            row["downstream_impact"] = "影响项目齐套、生产领料、委外发料和应付确认"
            if not is_receive_status_ready:
                row["blocked_reason"] = "采购订单未审核，不能收货入库"
                row["condition_label"] = "需采购主管审核"
            elif not has_project_cabinet:
                row["blocked_reason"] = "缺少项目号或柜号，不能收货入库"
                row["condition_label"] = "需补齐项目号和柜号"
            else:
                row["blocked_reason"] = "可直接生成采购入库单"
                row["condition_label"] = "订单已审核，项目/柜号齐套"
        elif payable_balance > 0:
            row["risk_label"] = "待付款"
            row["arrival_alert"] = "已形成应付，跟进账期/付款"
            row["next_action"] = "处理应付"
            row["blocked_reason"] = "存在未清应付余额"
            row["owner_role"] = "采购跟单 / 财务"
            row["condition_label"] = "需核对应付余额和付款计划"
            row["downstream_impact"] = "影响供应商账期、项目成本和期间结账"
        if risk == "pending_receive" and pending_qty <= 0:
            continue
        if risk == "payable" and payable_balance <= 0:
            continue
        if risk == "overdue" and not is_overdue:
            continue
        filtered_orders.append(row)
    pending_receive_rows = [row for row in filtered_orders if as_decimal(row.get("pending_receive_qty")) > 0]
    payable_rows = [row for row in filtered_orders if as_decimal(row.get("payable_balance")) > 0]
    overdue_rows = [
        row
        for row in filtered_orders
        if row.get("expected_date") and row.get("expected_date") < today and as_decimal(row.get("pending_receive_qty")) > 0
    ]
    blocked_rows = [row for row in filtered_orders if row.get("blocked_reason") and not row.get("can_receive")]
    queue_cards = [
        {
            "label": "到货例外",
            "count": len(overdue_rows),
            "role": "采购跟单",
            "next_action": "催交、改期或升级项目缺料风险",
            "condition": "预计到货已过且仍有未收数量",
            "impact": "影响项目齐套、工单领料和装配计划",
            "url": f"{back_url}?risk=overdue",
            "variant": "danger",
        },
        {
            "label": "待收货队列",
            "count": len(pending_receive_rows),
            "role": "仓库 / 采购跟单",
            "next_action": "生成采购入库单并核对库存流水",
            "condition": f"{len(blocked_rows)} 张仍有收货条件堵点",
            "impact": "影响可用库存、项目领料和应付确认",
            "url": f"{back_url}?risk=pending_receive",
            "variant": "primary",
        },
        {
            "label": "采购建议",
            "count": len(actionable_suggestions),
            "role": "采购计划",
            "next_action": "将缺料建议转采购申请或采购订单",
            "condition": "MRP 缺口扣减库存和在途后仍需处理",
            "impact": "影响项目齐套、长周期件交期和工单开工",
            "url": "/procurement/suggestions",
            "variant": "warning",
        },
        {
            "label": "待付款队列",
            "count": len(payable_rows),
            "role": "采购跟单 / 财务",
            "next_action": "核对应付余额和付款计划",
            "condition": f"{payable_summary.get('open_count', 0)} 笔应付未清",
            "impact": "影响供应商账期、项目成本和月结",
            "url": f"{back_url}?risk=payable",
            "variant": "secondary",
        },
    ]
    project_focus = (overdue_rows + blocked_rows + pending_receive_rows + payable_rows)[:12]
    pending_items = query_rows(
        """
        SELECT poi.id, po.id AS order_id, po.order_no, po.expected_date, s.name AS supplier_name,
               po.project_code, po.cabinet_no, p.code AS product_code, p.name AS product_name,
               p.specification, p.unit,
               poi.quantity, poi.received_qty,
               GREATEST(COALESCE(poi.quantity,0)-COALESCE(poi.received_qty,0),0) AS pending_receive_qty
        FROM purchase_order_items poi
        LEFT JOIN purchase_orders po ON po.id=poi.order_id
        LEFT JOIN suppliers s ON s.id=po.supplier_id
        LEFT JOIN products p ON p.id=poi.product_id
        WHERE GREATEST(COALESCE(poi.quantity,0)-COALESCE(poi.received_qty,0),0) > 0
          AND COALESCE(po.status, '') NOT IN ('已收货','已关闭','已作废','closed','completed')
        ORDER BY po.expected_date NULLS LAST, poi.id DESC
        LIMIT 60
        """
    )
    pending_items = filter_clean_rows(pending_items, "order_no", "supplier_name", "product_code", "product_name", "project_code", "cabinet_no")
    requisitions = query_rows(
        """
        SELECT pr.id, pr.req_no, pr.req_date, pr.project_code, pr.cabinet_no, pr.status,
               COUNT(pri.id) AS item_count,
               COALESCE(SUM(GREATEST(COALESCE(pri.quantity,0)-COALESCE(ordered.ordered_qty,0),0)), 0) AS remaining_qty
        FROM purchase_requisitions pr
        LEFT JOIN purchase_requisition_items pri ON pri.req_id=pr.id
        LEFT JOIN LATERAL (
            SELECT COALESCE(SUM(poi.quantity), 0) AS ordered_qty
            FROM purchase_order_items poi
            WHERE poi.source_line_no=CONCAT('PRITEM-', pri.id::text)
        ) ordered ON TRUE
        WHERE COALESCE(pr.status, '') NOT IN ('已下推','已关闭','已作废','closed','cancelled')
        GROUP BY pr.id
        ORDER BY pr.id DESC
        LIMIT 30
        """
    )
    payables = query_rows(
        """
        SELECT sp.id, sp.doc_no, sp.doc_date, s.name AS supplier_name,
               sp.amount, sp.paid_amount, sp.balance, sp.status
        FROM supplier_payables sp
        LEFT JOIN suppliers s ON s.id=sp.supplier_id
        WHERE COALESCE(sp.balance, 0) > 0
        ORDER BY sp.next_follow_up_date NULLS FIRST, sp.id DESC
        LIMIT 50
        """
    )
    payables = filter_clean_rows(payables, "doc_no", "supplier_name", "status")
    return render_template(
        "purchase_order_list.html" if document_list else "purchase_dashboard.html",
        title="采购订单列表" if document_list else "采购工作台",
        subtitle="采购订单单据列表：新建、查看、提交、审核、收货、关闭、作废。" if document_list else "按项目号和柜号推进缺料、采购、到货、入库和应付闭环。",
        document_list=document_list,
        back_url=back_url,
        metrics=metrics,
        orders=filtered_orders,
        queue_cards=queue_cards,
        project_focus=project_focus,
        pending_items=pending_items,
        suggestions=actionable_suggestions[:30],
        requisitions=requisitions,
        payables=payables,
        status_rows=status_rows,
        suppliers=suppliers,
        filters={"keyword": keyword, "status": status, "supplier_id": supplier_id, "risk": risk, "date_from": date_from, "date_to": date_to},
        overdue_count=pending_summary.get("overdue_count", 0),
        pending_amount=money_metric(pending_summary.get("pending_amount", 0)),
    )
