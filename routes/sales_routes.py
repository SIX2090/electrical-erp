"""Sales module routes: dashboard, order list, order form, and shipment readiness helpers."""
from datetime import datetime

from flask import render_template

from .display_helpers import _clean_display_text

SHIP_READY_STATUSES = {"已审核", "已审批", "部分发货"}
CLOSED_ORDER_STATUSES = {"已发货", "已关闭", "已作废", "closed", "completed"}


def render_sales_dashboard(
    query_one,
    query_rows,
    as_decimal,
    status_label,
    filter_clean_rows,
    money_metric,
    qty_metric,
    request_args,
    back_url="/sales-orders",
    document_list=False,
    scope_clause="",
    scope_params=None,
):
    keyword = (request_args.get("keyword") or request_args.get("q") or request_args.get("search") or "").strip()
    status = (request_args.get("status") or "").strip()
    customer_id = (request_args.get("customer_id") or "").strip()
    risk = (request_args.get("risk") or "").strip()
    product_family = (request_args.get("product_family") or "").strip()
    date_from = (request_args.get("date_from") or request_args.get("date_start") or "").strip()
    date_to = (request_args.get("date_to") or request_args.get("date_end") or "").strip()
    scope_params = list(scope_params or [])

    where_parts = []
    params = []
    if keyword:
        where_parts.append(
            "(so.order_no ILIKE %s OR so.project_code ILIKE %s OR so.cabinet_no ILIKE %s OR c.name ILIKE %s)"
        )
        params.extend([f"%{keyword}%"] * 4)
    if status:
        where_parts.append("COALESCE(so.status, '')=%s")
        params.append(status)
    if customer_id.isdigit():
        where_parts.append("so.customer_id=%s")
        params.append(int(customer_id))
    if date_from:
        where_parts.append("so.order_date >= %s")
        params.append(date_from)
    if date_to:
        where_parts.append("so.order_date <= %s")
        params.append(date_to)
    if product_family:
        where_parts.append(
            """
            EXISTS (
                SELECT 1
                FROM sales_order_items soi_filter
                LEFT JOIN products p_filter ON p_filter.id=soi_filter.product_id
                LEFT JOIN product_categories pc_filter ON pc_filter.id=p_filter.category_id
                WHERE soi_filter.order_id=so.id
                  AND COALESCE(pc_filter.name, p_filter.category, '')=%s
            )
            """
        )
        params.append(product_family)
    if scope_clause:
        where_parts.append(scope_clause.lstrip().removeprefix("AND").strip() or "1=1")
        params.extend(scope_params)
    credit_alerts = []
    credit_customer_ids = set()
    if risk == "credit" or not document_list:
        credit_alerts = query_rows(
            """
            SELECT c.id AS customer_id, c.name AS customer_name,
                   COALESCE(c.credit_limit, 0) AS credit_limit,
                   COALESCE(c.credit_used, 0) AS credit_used,
                   COALESCE(ar.open_balance, 0) AS open_balance,
                   COALESCE(open_orders.open_amount, 0) AS open_order_amount,
                   COALESCE(c.credit_used, 0) + COALESCE(ar.open_balance, 0) + COALESCE(open_orders.open_amount, 0) AS exposure
            FROM customers c
            LEFT JOIN LATERAL (
                SELECT COALESCE(SUM(balance), 0) AS open_balance
                FROM customer_receivables cr
                WHERE cr.customer_id=c.id AND COALESCE(cr.balance, 0) > 0
            ) ar ON TRUE
            LEFT JOIN LATERAL (
                SELECT COALESCE(SUM(COALESCE(amount_with_tax,total_amount,0)), 0) AS open_amount
                FROM sales_orders so
                WHERE so.customer_id=c.id
                  AND COALESCE(so.status, '') NOT IN ('已发货','已关闭','已作废','closed','completed')
            ) open_orders ON TRUE
            WHERE COALESCE(c.credit_limit, 0) > 0
              AND COALESCE(c.credit_used, 0) + COALESCE(ar.open_balance, 0) + COALESCE(open_orders.open_amount, 0) > COALESCE(c.credit_limit, 0)
            ORDER BY (COALESCE(c.credit_used, 0) + COALESCE(ar.open_balance, 0) + COALESCE(open_orders.open_amount, 0) - COALESCE(c.credit_limit, 0)) DESC, c.id DESC
            """
        )
        credit_alerts = filter_clean_rows(credit_alerts, "customer_name")
        credit_customer_ids = {
            row.get("customer_id")
            for row in credit_alerts
            if row.get("customer_id") is not None
        }
    if not document_list:
        where_parts.append(
            f"""
            (
                COALESCE(items.pending_ship_qty, 0) > 0
                OR COALESCE(ar.receivable_balance, 0) > 0
                OR (
                    so.delivery_date < CURRENT_DATE
                    AND COALESCE(so.status, '') NOT IN ({','.join(['%s'] * len(CLOSED_ORDER_STATUSES))})
                )
            )
            """
        )
        params.extend(sorted(CLOSED_ORDER_STATUSES))
    if risk == "pending_ship":
        where_parts.append("COALESCE(items.pending_ship_qty, 0) > 0")
    elif risk == "receivable":
        where_parts.append("COALESCE(ar.receivable_balance, 0) > 0")
    elif risk == "overdue":
        where_parts.append(
            f"""
            so.delivery_date < CURRENT_DATE
            AND COALESCE(so.status, '') NOT IN ({','.join(['%s'] * len(CLOSED_ORDER_STATUSES))})
            AND COALESCE(items.pending_ship_qty, 0) > 0
            """
        )
        params.extend(sorted(CLOSED_ORDER_STATUSES))
    elif risk == "credit":
        if credit_customer_ids:
            where_parts.append("so.customer_id = ANY(%s)")
            params.append(list(credit_customer_ids))
        else:
            where_parts.append("1=0")
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

    summary = query_one(
        f"""
        SELECT COUNT(*) AS order_count,
               COUNT(*) FILTER (
                   WHERE COALESCE(so.status, '') NOT IN ('已发货','已关闭','已作废','closed','completed')
               ) AS open_count,
               COALESCE(SUM(COALESCE(so.amount_with_tax, so.total_amount, 0)), 0) AS sales_amount,
               COUNT(*) FILTER (
                   WHERE so.delivery_date < CURRENT_DATE
                     AND COALESCE(so.status, '') NOT IN ('已发货','已关闭','已作废','closed','completed')
                     AND COALESCE(items.pending_ship_qty, 0) > 0
               ) AS overdue_delivery,
               COUNT(*) FILTER (WHERE COALESCE(items.pending_ship_qty, 0) > 0) AS pending_ship_order_count,
               COALESCE(SUM(COALESCE(items.pending_ship_qty, 0)), 0) AS pending_qty
        FROM sales_orders so
        LEFT JOIN customers c ON c.id=so.customer_id
        LEFT JOIN LATERAL (
            SELECT COALESCE(SUM(GREATEST(COALESCE(quantity,0)-COALESCE(shipped_qty,0),0)), 0) AS pending_ship_qty
            FROM sales_order_items soi
            WHERE soi.order_id=so.id
        ) items ON TRUE
        LEFT JOIN LATERAL (
            SELECT COALESCE(SUM(balance), 0) AS receivable_balance
            FROM customer_receivables cr
            WHERE cr.source_id=so.id OR cr.source_no=so.order_no
        ) ar ON TRUE
        {where_sql}
        """,
        tuple(params),
    ) or {}
    receivable_summary = query_one(
        """
        SELECT COALESCE(SUM(balance), 0) AS balance,
               COALESCE(SUM(CASE WHEN due_date < CURRENT_DATE THEN balance ELSE 0 END), 0) AS overdue_balance,
               COUNT(*) FILTER (WHERE COALESCE(balance, 0) > 0) AS open_count
        FROM customer_receivables
        """
    ) or {}
    metrics = [
        {"label": "销售订单数", "value": summary.get("order_count", 0), "hint": "按当前筛选条件"},
        {"label": "待发货", "value": summary.get("pending_ship_order_count", 0), "hint": f"{qty_metric(summary.get('pending_qty', 0))} 件/套未发"},
        {"label": "应收余额", "value": money_metric(receivable_summary.get("balance", 0)), "hint": f"{receivable_summary.get('open_count', 0)} 笔未清，全局指标"},
        {"label": "逾期交付", "value": summary.get("overdue_delivery", 0), "hint": "交期早于今天且未关闭"},
    ]
    status_rows = query_rows(
        """
        SELECT status, COUNT(*) AS count
        FROM sales_orders
        WHERE COALESCE(status, '') <> ''
        GROUP BY status
        ORDER BY count DESC, status
        """
    )
    status_rows = filter_clean_rows(status_rows, "status")
    for row in status_rows:
        row["display_status"] = status_label(row.get("status"))
    customers = query_rows(
        """
        SELECT c.id, c.name
        FROM customers c
        WHERE c.id IN (SELECT DISTINCT customer_id FROM sales_orders WHERE customer_id IS NOT NULL)
        ORDER BY c.name
        LIMIT 200
        """
    )
    customers = filter_clean_rows(customers, "name")
    product_families = query_rows(
        """
        SELECT DISTINCT COALESCE(pc.name, p.category, '') AS name
        FROM sales_order_items soi
        LEFT JOIN products p ON p.id=soi.product_id
        LEFT JOIN product_categories pc ON pc.id=p.category_id
        WHERE COALESCE(pc.name, p.category, '') <> ''
        ORDER BY name
        LIMIT 200
        """
    )
    product_families = filter_clean_rows(product_families, "name")
    orders = query_rows(
        f"""
        SELECT so.id, so.order_no, so.order_date, so.delivery_date, so.project_code, so.cabinet_no,
               so.status, so.total_amount, so.shipped_amount, c.name AS customer_name,
               COALESCE(items.item_count, 0) AS item_count,
               COALESCE(items.ordered_qty, 0) AS ordered_qty,
               COALESCE(items.shipped_qty, 0) AS shipped_qty,
               COALESCE(items.pending_ship_qty, 0) AS pending_ship_qty,
               COALESCE(items.product_families, '') AS product_families,
               COALESCE(items.bom_versions, '') AS bom_versions,
               COALESCE(ar.receivable_balance, 0) AS receivable_balance,
               COALESCE(ship.shipment_count, 0) AS shipment_count
        FROM sales_orders so
        LEFT JOIN customers c ON c.id=so.customer_id
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS item_count,
                   COALESCE(SUM(quantity), 0) AS ordered_qty,
                   COALESCE(SUM(shipped_qty), 0) AS shipped_qty,
                   COALESCE(SUM(GREATEST(COALESCE(quantity,0)-COALESCE(shipped_qty,0),0)), 0) AS pending_ship_qty,
                   STRING_AGG(DISTINCT NULLIF(COALESCE(pc.name, p.category, ''), ''), ' / ') AS product_families,
                   STRING_AGG(DISTINCT NULLIF(CONCAT_WS(' ', b.bom_no, b.version), ''), ' / ') AS bom_versions
            FROM sales_order_items soi
            LEFT JOIN products p ON p.id=soi.product_id
            LEFT JOIN product_categories pc ON pc.id=p.category_id
            LEFT JOIN LATERAL (
                SELECT bom_no, version
                FROM boms b
                WHERE b.product_id=soi.product_id AND COALESCE(b.status, '') NOT IN ('停用','inactive','disabled')
                ORDER BY CASE WHEN b.bom_type='production' THEN 0 ELSE 1 END, b.id DESC
                LIMIT 1
            ) b ON TRUE
            WHERE soi.order_id=so.id
        ) items ON TRUE
        LEFT JOIN LATERAL (
            SELECT COALESCE(SUM(balance), 0) AS receivable_balance
            FROM customer_receivables cr
            WHERE cr.source_id=so.id OR cr.source_no=so.order_no
        ) ar ON TRUE
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS shipment_count
            FROM sales_shipments ss
            WHERE ss.order_id=so.id
        ) ship ON TRUE
        {where_sql}
        ORDER BY COALESCE(items.pending_ship_qty, 0) DESC, so.delivery_date NULLS LAST, so.id DESC
        LIMIT 120
        """,
        tuple(params),
    )
    orders = filter_clean_rows(orders, "order_no", "customer_name", "project_code", "cabinet_no", "status")
    today = datetime.now().date()
    filtered_orders = []
    for row in orders:
        for key in ("order_no", "customer_name", "project_code", "cabinet_no"):
            row[key] = _clean_display_text(row.get(key))
        row["display_status"] = status_label(row.get("status"))
        pending_qty = as_decimal(row.get("pending_ship_qty"))
        receivable_balance = as_decimal(row.get("receivable_balance"))
        is_overdue = bool(row.get("delivery_date") and row.get("delivery_date") < today and pending_qty > 0)
        is_ship_status_ready = row.get("status") in SHIP_READY_STATUSES
        has_project_cabinet = bool(row.get("project_code") and row.get("cabinet_no"))
        row["can_ship"] = bool(pending_qty > 0 and is_ship_status_ready and has_project_cabinet)
        row["ship_action_label"] = "生成销售出库单"
        row["risk_label"] = "正常"
        row["next_action"] = "跟进订单"
        row["blocked_reason"] = ""
        row["owner_role"] = "销售跟单"
        row["condition_label"] = "按交期跟踪客户、项目号和柜号"
        row["downstream_impact"] = "影响项目交付、发货、服务建档和应收"
        if pending_qty > 0:
            row["risk_label"] = "逾期交付" if is_overdue else "待发货"
            row["next_action"] = "生成销售出库单" if row["can_ship"] else "补齐发货条件"
            row["owner_role"] = "销售跟单 / 仓库"
            row["downstream_impact"] = "影响成品出库、客户签收、服务档案和应收确认"
            if not is_ship_status_ready:
                row["blocked_reason"] = "销售订单未审核，不能发货"
                row["condition_label"] = "需销售主管审核"
            elif not row.get("project_code") or not row.get("cabinet_no"):
                row["blocked_reason"] = "缺少项目号或柜号，不能发货"
                row["condition_label"] = "需补齐项目号和柜号"
            elif not row.get("shipment_count"):
                row["blocked_reason"] = "可直接生成销售出库单"
                row["condition_label"] = "订单已审核，项目/柜号齐套"
        elif receivable_balance > 0:
            row["risk_label"] = "待回款"
            row["next_action"] = "催收回款"
            row["blocked_reason"] = "存在未清应收余额"
            row["owner_role"] = "销售跟单 / 财务"
            row["condition_label"] = "需登记客户回款或确认账期"
            row["downstream_impact"] = "影响应收账龄、项目毛利和期间结账"
        filtered_orders.append(row)
    pending_ship_rows = [row for row in filtered_orders if as_decimal(row.get("pending_ship_qty")) > 0]
    receivable_rows = [row for row in filtered_orders if as_decimal(row.get("receivable_balance")) > 0]
    overdue_rows = [
        row
        for row in filtered_orders
        if row.get("delivery_date") and row.get("delivery_date") < today and as_decimal(row.get("pending_ship_qty")) > 0
    ]
    blocked_rows = [row for row in filtered_orders if row.get("blocked_reason") and not row.get("can_ship")]
    queue_cards = [
        {
            "label": "交付例外",
            "count": len(overdue_rows),
            "role": "销售跟单",
            "next_action": "确认改期、协调仓库或升级项目风险",
            "condition": "交期已过且仍有未发数量",
            "impact": "影响客户交付承诺、服务安装和收入确认",
            "url": f"{back_url}?risk=overdue",
            "variant": "danger",
        },
        {
            "label": "待发货队列",
            "count": len(pending_ship_rows),
            "role": "仓库 / 销售跟单",
            "next_action": "生成销售出库单并跟踪签收",
            "condition": f"{len(blocked_rows)} 张仍有发货条件堵点",
            "impact": "影响库存出库、服务建档和应收生成",
            "url": f"{back_url}?risk=pending_ship",
            "variant": "primary",
        },
        {
            "label": "待回款队列",
            "count": len(receivable_rows),
            "role": "销售跟单 / 财务",
            "next_action": "核对应收余额并登记客户回款",
            "condition": f"逾期应收 {money_metric(receivable_summary.get('overdue_balance', 0))}",
            "impact": "影响现金流、项目利润和月结",
            "url": f"{back_url}?risk=receivable",
            "variant": "warning",
        },
    ]
    if not document_list:
        queue_cards.append(
            {
                "label": "信用预警",
                "count": len(credit_alerts),
                "role": "销售主管 / 财务",
                "next_action": "确认额度、账期或暂停新增发货",
                "condition": "客户未清应收和未交订单超过信用额度",
                "impact": "影响订单审核、发货放行和回款风险",
                "url": f"{back_url}?risk=credit",
                "variant": "warning",
            }
        )
    project_focus = (overdue_rows + blocked_rows + pending_ship_rows + receivable_rows)[:12]
    pending_items = []
    receivables = []
    if not document_list:
        pending_items = query_rows(
            """
            SELECT soi.id, so.id AS order_id, so.order_no, so.delivery_date, c.name AS customer_name,
                   so.project_code, so.cabinet_no, p.code AS product_code, p.name AS product_name,
                   p.specification, p.unit,
                   soi.quantity, soi.shipped_qty,
                   GREATEST(COALESCE(soi.quantity,0)-COALESCE(soi.shipped_qty,0),0) AS pending_ship_qty
            FROM sales_order_items soi
            LEFT JOIN sales_orders so ON so.id=soi.order_id
            LEFT JOIN customers c ON c.id=so.customer_id
            LEFT JOIN products p ON p.id=soi.product_id
            WHERE GREATEST(COALESCE(soi.quantity,0)-COALESCE(soi.shipped_qty,0),0) > 0
              AND COALESCE(so.status, '') NOT IN ('已发货','已关闭','已作废','closed','completed')
            ORDER BY so.delivery_date NULLS LAST, soi.id DESC
            LIMIT 12
            """
        )
        pending_items = filter_clean_rows(pending_items, "order_no", "customer_name", "product_code", "product_name", "project_code", "cabinet_no")
        for row in pending_items:
            for key in ("order_no", "customer_name", "product_code", "product_name"):
                row[key] = _clean_display_text(row.get(key))
        receivables = query_rows(
            """
            SELECT cr.id, cr.source_no, cr.receivable_date, cr.due_date, c.name AS customer_name,
                   cr.total_amount, cr.received_amount, cr.balance, cr.status
            FROM customer_receivables cr
            LEFT JOIN customers c ON c.id=cr.customer_id
            WHERE COALESCE(cr.balance, 0) > 0
            ORDER BY cr.due_date NULLS FIRST, cr.id DESC
            LIMIT 10
            """
        )
        receivables = filter_clean_rows(receivables, "source_no", "customer_name", "status")
        for row in receivables:
            for key in ("source_no", "customer_name", "status"):
                row[key] = _clean_display_text(row.get(key))
    return render_template(
        "sales_order_list.html" if document_list else "sales_dashboard.html",
        title="销售订单列表" if document_list else "销售工作台",
        subtitle="销售订单单据列表：新建、查看、提交、审核、发货、关闭、作废。" if document_list else "按项目号和柜号推进订单、发货、签收、服务建档和应收闭环。",
        document_list=document_list,
        back_url=back_url,
        metrics=metrics,
        orders=filtered_orders,
        queue_cards=queue_cards,
        project_focus=project_focus,
        pending_items=pending_items,
        receivables=receivables,
        credit_alerts=credit_alerts,
        shipments=[],
        receipts=[],
        status_rows=status_rows,
        customers=customers,
        product_families=product_families,
        filters={
            "keyword": keyword,
            "status": status,
            "customer_id": customer_id,
            "risk": risk,
            "product_family": product_family,
            "date_from": date_from,
            "date_to": date_to,
        },
        overdue_receivable=money_metric(receivable_summary.get("overdue_balance", 0)),
    )
