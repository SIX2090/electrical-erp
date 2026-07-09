"""Module report data: fetch and aggregate report data for module report pages."""
import hashlib
import logging
from decimal import Decimal

from routes.module_report_helpers import report_filters, report_where_from_args
from services.report_cache import report_cache

logger = logging.getLogger(__name__)

# Cache TTL for module center page metrics queries (seconds).
# These are lightweight summary queries that tolerate slight staleness.
_METRICS_CACHE_TTL = 30


def _inventory_cost_source_display(row):
    source_no = (row.get("source_doc_no") or row.get("reference_no") or "").strip()
    source_type = (row.get("source_doc_type") or row.get("source_type") or "").strip()
    return source_no or source_type or "-"


def _inventory_cost_source_url(row):
    source_no = (row.get("source_doc_no") or row.get("reference_no") or "").strip()
    source_no_lower = source_no.lower()
    source_type = (row.get("source_doc_type") or row.get("source_type") or row.get("transaction_type") or "").strip().lower()
    if not source_no:
        return ""

    doc_routes = (
        ("purchase_receipt_id", "/purchase_receipts"),
        ("sales_shipment_id", "/shipments"),
        ("work_order_id", "/work-orders"),
        ("subcontract_issue_id", "/subcontract_issue"),
        ("subcontract_receive_id", "/subcontract_receive"),
        ("inventory_adjustment_id", "/adjustments"),
        ("inventory_transfer_id", "/transfers"),
        ("inventory_check_id", "/inventory_checks"),
        ("inventory_assembly_id", "/assembly-orders"),
        ("inventory_disassembly_id", "/disassembly-orders"),
    )
    for id_key, prefix in doc_routes:
        value = row.get(id_key)
        if value:
            return f"{prefix}/{value}"

    # Fallback only when the document prefix/type is already explicit in stock transaction data.
    prefix_routes = (
        (("purchase_receipt", "receipt"), ("pr",), "/purchase_receipts"),
        (("sales_shipment", "shipment"), ("ss",), "/shipments"),
        (("work_order", "work order"), ("wo",), "/work-orders"),
        (("subcontract_issue", "outsourcing_issue"), ("osi",), "/subcontract_issue"),
        (("subcontract_receive", "outsourcing_receive"), ("osr",), "/subcontract_receive"),
        (("inventory_adjustment", "adjustment"), ("ia",), "/adjustments"),
        (("inventory_transfer", "transfer"), ("tr",), "/transfers"),
        (("inventory_check", "check"), ("ic",), "/inventory_checks"),
    )
    for type_needles, doc_prefixes, route in prefix_routes:
        if any(needle in source_type for needle in type_needles) or any(source_no_lower.startswith(prefix) for prefix in doc_prefixes):
            return f"{route}?keyword={source_no}"
    return ""


def _apply_inventory_cost_drilldown(rows):
    for row in rows:
        row["source_doc_label"] = _inventory_cost_source_display(row)
        row["source_doc_url"] = _inventory_cost_source_url(row)
        if as_decimal_safe(row.get("inbound_qty")) > 0:
            row["cost_basis_note"] = "Inbound cost = inbound qty * stock transaction unit cost."
        elif as_decimal_safe(row.get("outbound_qty")) > 0:
            row["cost_basis_note"] = "Outbound cost = outbound qty * stock transaction unit cost."
        else:
            row["cost_basis_note"] = "Calculated from stock transaction unit cost."
    return rows


def as_decimal_safe(value):
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _with_url_key(column_list, key, url_key):
    for column in column_list:
        if column.get("key") == key:
            column["url_key"] = url_key
    return column_list


def _with_section_urls(section_list, urls):
    for section, url in zip(section_list, urls):
        section["url"] = url
    return section_list


def _build_inventory_report_config(query_rows, as_decimal, money_metric, qty_metric, columns, request_args):
    balance_where, balance_params, filters = report_where_from_args(
        request_args,
        "COALESCE(ib.updated_at::date, CURRENT_DATE)",
        ("p.code", "p.name", "p.specification", "w.name", "l.code", "l.name", "ib.lot_no", "ib.serial_no", "ib.project_code"),
        None,
        ("ib.project_code", "ib.serial_no"),
    )
    tx_where, tx_params, _ = report_where_from_args(
        request_args,
        "COALESCE(st.transaction_date::date, st.created_at::date, CURRENT_DATE)",
        ("p.code", "p.name", "p.specification", "w.name", "l.code", "l.name", "st.reference_no", "st.lot_no", "st.serial_no", "st.project_code"),
        None,
        ("st.project_code", "st.serial_no"),
    )
    batch_where, batch_params, _ = report_where_from_args(
        request_args,
        "COALESCE(bt.updated_at::date, CURRENT_DATE)",
        ("p.code", "p.name", "p.specification", "w.name", "bt.location", "bt.lot_no", "bt.serial_no", "bt.project_code", "bt.source_order_no"),
        None,
        ("bt.project_code", "bt.serial_no"),
    )
    date_start = filters.get("date_start") or "1900-01-01"
    date_end = filters.get("date_end") or "2999-12-31"

    section_path = request_args.get("_section_path") if hasattr(request_args, "get") else ""
    section_key_by_path = {
        "/finance/inventory-cost/summary": "inventory-cost-summary",
        "/finance/inventory-cost/detail": "inventory-cost-detail",
        "/inventory/reports/ledger": "ledger",
        "/inventory/reports/account-book": "account-book",
        "/inventory/reports/monthly": "monthly",
        "/inventory/reports/inout-summary": "inout-summary",
        "/inventory/reports/balance": "balance",
        "/inventory/reports/inout-detail": "inout-detail",
        "/inventory/reports/location-stock": "location-stock",
        "/inventory/reports/available-stock": "available-stock",
        "/inventory/reports/shortage": "shortage",
        "/inventory/reports/turnover": "turnover",
        "/inventory/reports/project-occupation": "project-occupation",
        "/inventory/reports/subcontract-wip": "subcontract-wip",
        "/inventory/reports/subcontract-execution": "subcontract-execution",
        "/inventory/reports/subcontract-inout-detail": "subcontract-inout-detail",
        "/inventory/reports/subcontract-variance": "subcontract-variance",
        "/inventory/reports/subcontract-payable-reconcile": "subcontract-payable-reconcile",
        "/inventory/reports/check-difference": "check-difference",
        "/inventory/reports/fund-occupation": "fund-occupation",
        "/inventory/reports/batch-trace": "batch-trace",
    }
    requested_key = section_key_by_path.get(section_path or "")

    # Metrics-only keys: lightweight queries needed for the module center page
    _METRICS_KEYS = frozenset(("ledger", "inout-detail", "account-book", "fund-occupation", "batch-trace"))

    def should_load(*keys):
        if not requested_key:
            # Module center page: only load data needed for metrics summary
            return any(k in _METRICS_KEYS for k in keys)
        return requested_key in keys

    def query_for(keys, sql, params=()):
        if not should_load(*keys):
            return []
        # On the module center page (no specific section requested), cache
        # the lightweight metrics queries to avoid re-querying on every refresh.
        # Specific report pages always hit the DB for real-time data.
        if not requested_key:
            cache_key = "inv_metrics:" + hashlib.sha256(
                (sql + str(params)).encode("utf-8")
            ).hexdigest()[:32]
            return report_cache.get_or_fetch(
                cache_key,
                lambda: query_rows(sql, params),
                ttl_seconds=_METRICS_CACHE_TTL,
            )
        return query_rows(sql, params)

    ledger_rows = query_for(
        ("ledger", "inout-detail"),
        f"""
        SELECT COALESCE(st.transaction_date::date, st.created_at::date) AS transaction_date,
               st.reference_no, st.source_type, st.transaction_type,
               p.code AS product_code, p.name AS product_name, p.specification,
               w.name AS warehouse_name, l.code AS location_code, l.name AS location_name,
               st.project_code, st.lot_no, st.serial_no,
               CASE WHEN COALESCE(st.quantity,0) >= 0 THEN COALESCE(st.quantity,0) ELSE 0 END AS inbound_qty,
               CASE WHEN COALESCE(st.quantity,0) < 0 THEN ABS(COALESCE(st.quantity,0)) ELSE 0 END AS outbound_qty,
               COALESCE(st.quantity,0) AS net_qty,
               st.unit_cost,
               COALESCE(st.quantity,0) * COALESCE(st.unit_cost,0) AS amount
        FROM stock_transactions st
        LEFT JOIN products p ON p.id=st.product_id
        LEFT JOIN warehouses w ON w.id=st.warehouse_id
        LEFT JOIN locations l ON l.id=st.location_id
        {tx_where}
        ORDER BY COALESCE(st.transaction_date, st.created_at) DESC NULLS LAST, st.id DESC
        LIMIT 300
        """,
        tx_params,
    )
    cost_detail_rows = query_for(
        ("inventory-cost-detail",),
        f"""
        SELECT COALESCE(st.transaction_date::date, st.created_at::date) AS transaction_date,
               st.reference_no, st.source_type, st.transaction_type,
               p.code AS product_code, p.name AS product_name, p.specification,
               w.name AS warehouse_name, l.code AS location_code, l.name AS location_name,
               st.project_code, st.lot_no, st.serial_no,
               CASE WHEN COALESCE(st.quantity,0) >= 0 THEN COALESCE(st.quantity,0) ELSE 0 END AS inbound_qty,
               CASE WHEN COALESCE(st.quantity,0) < 0 THEN ABS(COALESCE(st.quantity,0)) ELSE 0 END AS outbound_qty,
               COALESCE(st.quantity,0) AS net_qty,
               COALESCE(st.unit_cost,0) AS unit_cost,
               CASE WHEN COALESCE(st.quantity,0) >= 0 THEN COALESCE(st.quantity,0) * COALESCE(st.unit_cost,0) ELSE 0 END AS inbound_amount,
               CASE WHEN COALESCE(st.quantity,0) < 0 THEN ABS(COALESCE(st.quantity,0)) * COALESCE(st.unit_cost,0) ELSE 0 END AS outbound_amount,
               COALESCE(st.quantity,0) * COALESCE(st.unit_cost,0) AS balance_impact_amount,
               COALESCE(st.source_doc_no, st.reference_no) AS source_doc_no,
               COALESCE(st.source_doc_type, st.source_type) AS source_doc_type,
               pr.id AS purchase_receipt_id,
               ss.id AS sales_shipment_id,
               wo.id AS work_order_id,
               sio.id AS subcontract_issue_id,
               sro.id AS subcontract_receive_id,
               ia.id AS inventory_adjustment_id,
               tr.id AS inventory_transfer_id,
               ic.id AS inventory_check_id,
               asm.id AS inventory_assembly_id,
               dis.id AS inventory_disassembly_id,
               st.remark
        FROM stock_transactions st
        LEFT JOIN products p ON p.id=st.product_id
        LEFT JOIN warehouses w ON w.id=st.warehouse_id
        LEFT JOIN locations l ON l.id=st.location_id
        LEFT JOIN (SELECT MIN(id) AS id, receipt_no FROM purchase_receipts GROUP BY receipt_no) pr ON pr.receipt_no=COALESCE(st.source_doc_no, st.reference_no)
        LEFT JOIN (SELECT MIN(id) AS id, shipment_no FROM sales_shipments GROUP BY shipment_no) ss ON ss.shipment_no=COALESCE(st.source_doc_no, st.reference_no)
        LEFT JOIN (SELECT MIN(id) AS id, wo_no FROM work_orders GROUP BY wo_no) wo ON wo.wo_no=COALESCE(st.source_doc_no, st.reference_no)
        LEFT JOIN (SELECT MIN(id) AS id, issue_no FROM subcontract_issue_orders GROUP BY issue_no) sio ON sio.issue_no=COALESCE(st.source_doc_no, st.reference_no)
        LEFT JOIN (SELECT MIN(id) AS id, receive_no FROM subcontract_receive_orders GROUP BY receive_no) sro ON sro.receive_no=COALESCE(st.source_doc_no, st.reference_no)
        LEFT JOIN (SELECT MIN(id) AS id, adj_no FROM inventory_adjustments GROUP BY adj_no) ia ON ia.adj_no=COALESCE(st.source_doc_no, st.reference_no)
        LEFT JOIN (SELECT MIN(id) AS id, transfer_no FROM transfer_orders GROUP BY transfer_no) tr ON tr.transfer_no=COALESCE(st.source_doc_no, st.reference_no)
        LEFT JOIN (SELECT MIN(id) AS id, check_no FROM inventory_check_orders GROUP BY check_no) ic ON ic.check_no=COALESCE(st.source_doc_no, st.reference_no)
        LEFT JOIN (SELECT MIN(id) AS id, assembly_no FROM inventory_assembly_orders WHERE doc_type='assembly' GROUP BY assembly_no) asm ON asm.assembly_no=COALESCE(st.source_doc_no, st.reference_no)
        LEFT JOIN (SELECT MIN(id) AS id, assembly_no FROM inventory_assembly_orders WHERE doc_type='disassembly' GROUP BY assembly_no) dis ON dis.assembly_no=COALESCE(st.source_doc_no, st.reference_no)
        {tx_where}
        ORDER BY COALESCE(st.transaction_date, st.created_at) DESC NULLS LAST, st.id DESC
        LIMIT 500
        """,
        tx_params,
    )
    summary_rows = query_for(
        ("inout-summary",),
        f"""
        WITH tx AS (
            SELECT st.product_id, st.warehouse_id, st.location_id,
                   COALESCE(st.lot_no, '') AS lot_no,
                   COALESCE(st.serial_no, '') AS serial_no,
                   COALESCE(st.project_code, '') AS project_code,
                   SUM(CASE WHEN COALESCE(st.transaction_date::date, st.created_at::date, CURRENT_DATE) < %s THEN COALESCE(st.quantity,0) ELSE 0 END) AS opening_qty,
                   SUM(CASE WHEN COALESCE(st.transaction_date::date, st.created_at::date, CURRENT_DATE) BETWEEN %s AND %s AND COALESCE(st.quantity,0) >= 0 THEN COALESCE(st.quantity,0) ELSE 0 END) AS inbound_qty,
                   SUM(CASE WHEN COALESCE(st.transaction_date::date, st.created_at::date, CURRENT_DATE) BETWEEN %s AND %s AND COALESCE(st.quantity,0) < 0 THEN ABS(COALESCE(st.quantity,0)) ELSE 0 END) AS outbound_qty,
                   AVG(NULLIF(COALESCE(st.unit_cost,0),0)) AS avg_unit_cost
            FROM stock_transactions st
            LEFT JOIN products p ON p.id=st.product_id
            LEFT JOIN warehouses w ON w.id=st.warehouse_id
            LEFT JOIN locations l ON l.id=st.location_id
            {tx_where}
            GROUP BY st.product_id, st.warehouse_id, st.location_id,
                     COALESCE(st.lot_no, ''), COALESCE(st.serial_no, ''), COALESCE(st.project_code, '')
        ),
        purchase_pending AS (
            SELECT poi.product_id,
                   COALESCE(po.project_code, '') AS project_code,
                   COALESCE(po.serial_no, '') AS serial_no,
                   SUM(GREATEST(COALESCE(poi.quantity,0)-COALESCE(poi.received_qty,0),0)) AS purchase_pending_qty
            FROM purchase_order_items poi
            JOIN purchase_orders po ON po.id=poi.order_id
            WHERE COALESCE(po.status,'') NOT IN ('已关闭','已作废','已取消','closed','void','cancelled','canceled')
            GROUP BY poi.product_id, COALESCE(po.project_code, ''), COALESCE(po.serial_no, '')
        ),
        sales_pending AS (
            SELECT soi.product_id,
                   COALESCE(so.project_code, '') AS project_code,
                   COALESCE(so.serial_no, '') AS serial_no,
                   SUM(GREATEST(COALESCE(soi.quantity,0)-COALESCE(soi.shipped_qty,0),0)) AS sales_pending_qty
            FROM sales_order_items soi
            JOIN sales_orders so ON so.id=soi.order_id
            WHERE COALESCE(so.status,'') NOT IN ('已关闭','已作废','已取消','closed','void','cancelled','canceled')
            GROUP BY soi.product_id, COALESCE(so.project_code, ''), COALESCE(so.serial_no, '')
        )
        SELECT p.code AS product_code, p.name AS product_name, p.specification,
               w.name AS warehouse_name, l.code AS location_code, l.name AS location_name,
               tx.project_code, tx.lot_no, tx.serial_no,
               tx.opening_qty, tx.inbound_qty, tx.outbound_qty,
               (COALESCE(tx.opening_qty,0) + COALESCE(tx.inbound_qty,0) - COALESCE(tx.outbound_qty,0)) AS closing_qty,
               COALESCE(purchase_pending.purchase_pending_qty, 0) AS purchase_pending_qty,
               COALESCE(sales_pending.sales_pending_qty, 0) AS sales_pending_qty,
               tx.avg_unit_cost,
               (COALESCE(tx.opening_qty,0) + COALESCE(tx.inbound_qty,0) - COALESCE(tx.outbound_qty,0)) * COALESCE(tx.avg_unit_cost,0) AS closing_amount
        FROM tx
        LEFT JOIN products p ON p.id=tx.product_id
        LEFT JOIN warehouses w ON w.id=tx.warehouse_id
        LEFT JOIN locations l ON l.id=tx.location_id
        LEFT JOIN purchase_pending ON purchase_pending.product_id=tx.product_id
            AND purchase_pending.project_code=tx.project_code
            AND purchase_pending.serial_no=tx.serial_no
        LEFT JOIN sales_pending ON sales_pending.product_id=tx.product_id
            AND sales_pending.project_code=tx.project_code
            AND sales_pending.serial_no=tx.serial_no
        ORDER BY p.code, w.name, l.code, tx.lot_no, tx.serial_no
        LIMIT 300
        """,
        (date_start, date_start, date_end, date_start, date_end) + tx_params,
    )
    account_book_rows = query_for(
        ("account-book",),
        f"""
        WITH tx AS (
            SELECT st.product_id, st.warehouse_id, st.location_id,
                   COALESCE(st.lot_no, '') AS lot_no,
                   COALESCE(st.serial_no, '') AS serial_no,
                   COALESCE(st.project_code, '') AS project_code,
                   SUM(CASE WHEN COALESCE(st.transaction_date::date, st.created_at::date, CURRENT_DATE) < %s THEN COALESCE(st.quantity,0) ELSE 0 END) AS opening_qty,
                   SUM(CASE WHEN COALESCE(st.transaction_date::date, st.created_at::date, CURRENT_DATE) < %s THEN COALESCE(st.quantity,0) * COALESCE(st.unit_cost,0) ELSE 0 END) AS opening_amount,
                   SUM(CASE WHEN COALESCE(st.transaction_date::date, st.created_at::date, CURRENT_DATE) BETWEEN %s AND %s AND COALESCE(st.quantity,0) >= 0 THEN COALESCE(st.quantity,0) ELSE 0 END) AS inbound_qty,
                   SUM(CASE WHEN COALESCE(st.transaction_date::date, st.created_at::date, CURRENT_DATE) BETWEEN %s AND %s AND COALESCE(st.quantity,0) >= 0 THEN COALESCE(st.quantity,0) * COALESCE(st.unit_cost,0) ELSE 0 END) AS inbound_amount,
                   SUM(CASE WHEN COALESCE(st.transaction_date::date, st.created_at::date, CURRENT_DATE) BETWEEN %s AND %s AND COALESCE(st.quantity,0) < 0 THEN ABS(COALESCE(st.quantity,0)) ELSE 0 END) AS outbound_qty,
                   SUM(CASE WHEN COALESCE(st.transaction_date::date, st.created_at::date, CURRENT_DATE) BETWEEN %s AND %s AND COALESCE(st.quantity,0) < 0 THEN ABS(COALESCE(st.quantity,0)) * COALESCE(st.unit_cost,0) ELSE 0 END) AS outbound_amount,
                   AVG(NULLIF(COALESCE(st.unit_cost,0),0)) AS avg_unit_cost
            FROM stock_transactions st
            LEFT JOIN products p ON p.id=st.product_id
            LEFT JOIN warehouses w ON w.id=st.warehouse_id
            LEFT JOIN locations l ON l.id=st.location_id
            {tx_where}
            GROUP BY st.product_id, st.warehouse_id, st.location_id,
                     COALESCE(st.lot_no, ''), COALESCE(st.serial_no, ''), COALESCE(st.project_code, '')
        )
        SELECT p.code AS product_code, p.name AS product_name, p.specification,
               w.name AS warehouse_name, l.code AS location_code, l.name AS location_name,
               tx.project_code, tx.lot_no, tx.serial_no,
               tx.opening_qty, tx.opening_amount,
               tx.inbound_qty, tx.inbound_amount,
               tx.outbound_qty, tx.outbound_amount,
               (COALESCE(tx.opening_qty,0) + COALESCE(tx.inbound_qty,0) - COALESCE(tx.outbound_qty,0)) AS closing_qty,
               (COALESCE(tx.opening_qty,0) + COALESCE(tx.inbound_qty,0) - COALESCE(tx.outbound_qty,0)) * COALESCE(tx.avg_unit_cost,0) AS closing_amount,
               tx.avg_unit_cost
        FROM tx
        LEFT JOIN products p ON p.id=tx.product_id
        LEFT JOIN warehouses w ON w.id=tx.warehouse_id
        LEFT JOIN locations l ON l.id=tx.location_id
        ORDER BY p.code, w.name, l.code, tx.project_code, tx.lot_no, tx.serial_no
        LIMIT 300
        """,
        (
            date_start,
            date_start,
            date_start,
            date_end,
            date_start,
            date_end,
            date_start,
            date_end,
            date_start,
            date_end,
        )
        + tx_params,
    )
    monthly_rows = query_for(
        ("monthly",),
        f"""
        WITH tx AS (
            SELECT DATE_TRUNC('month', COALESCE(st.transaction_date::date, st.created_at::date, CURRENT_DATE))::date AS report_month,
                   SUM(CASE WHEN COALESCE(st.quantity,0) >= 0 THEN COALESCE(st.quantity,0) ELSE 0 END) AS inbound_qty,
                   SUM(CASE WHEN COALESCE(st.quantity,0) >= 0 THEN COALESCE(st.quantity,0) * COALESCE(st.unit_cost,0) ELSE 0 END) AS inbound_amount,
                   SUM(CASE WHEN COALESCE(st.quantity,0) < 0 THEN ABS(COALESCE(st.quantity,0)) ELSE 0 END) AS outbound_qty,
                   SUM(CASE WHEN COALESCE(st.quantity,0) < 0 THEN ABS(COALESCE(st.quantity,0)) * COALESCE(st.unit_cost,0) ELSE 0 END) AS outbound_amount,
                   SUM(COALESCE(st.quantity,0)) AS net_qty,
                   SUM(COALESCE(st.quantity,0) * COALESCE(st.unit_cost,0)) AS net_amount
            FROM stock_transactions st
            LEFT JOIN products p ON p.id=st.product_id
            LEFT JOIN warehouses w ON w.id=st.warehouse_id
            LEFT JOIN locations l ON l.id=st.location_id
            {tx_where}
            GROUP BY DATE_TRUNC('month', COALESCE(st.transaction_date::date, st.created_at::date, CURRENT_DATE))::date
        ),
        opening AS (
            SELECT month_row.report_month,
                   COALESCE(SUM(CASE WHEN COALESCE(st.transaction_date::date, st.created_at::date, CURRENT_DATE) < month_row.report_month THEN COALESCE(st.quantity,0) ELSE 0 END),0) AS opening_qty,
                   COALESCE(SUM(CASE WHEN COALESCE(st.transaction_date::date, st.created_at::date, CURRENT_DATE) < month_row.report_month THEN COALESCE(st.quantity,0) * COALESCE(st.unit_cost,0) ELSE 0 END),0) AS opening_amount
            FROM tx month_row
            LEFT JOIN stock_transactions st
                ON st.transaction_date::date < month_row.report_month
            LEFT JOIN products p ON p.id=st.product_id
            LEFT JOIN warehouses w ON w.id=st.warehouse_id
            LEFT JOIN locations l ON l.id=st.location_id
            {tx_where}
            GROUP BY month_row.report_month
        )
        SELECT tx.report_month,
               opening.opening_qty, opening.opening_amount,
               tx.inbound_qty, tx.inbound_amount,
               tx.outbound_qty, tx.outbound_amount,
               opening.opening_qty + tx.net_qty AS closing_qty,
               opening.opening_amount + tx.net_amount AS closing_amount
        FROM tx
        LEFT JOIN opening ON opening.report_month=tx.report_month
        ORDER BY tx.report_month DESC
        LIMIT 36
        """,
        tx_params + tx_params,
    )
    fund_rows = query_for(
        ("fund-occupation",),
        f"""
        WITH last_tx AS (
            SELECT product_id, warehouse_id, location_id,
                   COALESCE(lot_no, '') AS lot_no,
                   COALESCE(serial_no, '') AS serial_no,
                   COALESCE(project_code, '') AS project_code,
                   MAX(COALESCE(transaction_date::date, created_at::date)) AS last_transaction_date
            FROM stock_transactions
            GROUP BY product_id, warehouse_id, location_id,
                     COALESCE(lot_no, ''), COALESCE(serial_no, ''), COALESCE(project_code, '')
        )
        SELECT p.code AS product_code, p.name AS product_name, p.specification,
               w.name AS warehouse_name, l.code AS location_code, l.name AS location_name,
               ib.project_code, ib.lot_no, ib.serial_no,
               ib.quantity AS closing_qty, ib.locked_qty, ib.unit_cost,
               COALESCE(ib.quantity,0) * COALESCE(ib.unit_cost,0) AS stock_amount,
               last_tx.last_transaction_date,
               GREATEST(CURRENT_DATE - COALESCE(last_tx.last_transaction_date, ib.updated_at::date, CURRENT_DATE), 0) AS stagnant_days,
               CASE
                   WHEN COALESCE(ib.quantity,0) * COALESCE(ib.unit_cost,0) >= 100000 THEN '高'
                   WHEN COALESCE(ib.quantity,0) * COALESCE(ib.unit_cost,0) >= 10000 THEN '中'
                   ELSE '低'
               END AS occupation_level
        FROM inventory_balances ib
        LEFT JOIN products p ON p.id=ib.product_id
        LEFT JOIN warehouses w ON w.id=ib.warehouse_id
        LEFT JOIN locations l ON l.id=ib.location_id
        LEFT JOIN last_tx ON last_tx.product_id=ib.product_id
            AND COALESCE(last_tx.warehouse_id,0)=COALESCE(ib.warehouse_id,0)
            AND COALESCE(last_tx.location_id,0)=COALESCE(ib.location_id,0)
            AND last_tx.lot_no=COALESCE(ib.lot_no,'')
            AND last_tx.serial_no=COALESCE(ib.serial_no,'')
            AND last_tx.project_code=COALESCE(ib.project_code,'')
        {balance_where}
        ORDER BY stock_amount DESC NULLS LAST, p.code
        LIMIT 300
        """,
        balance_params,
    )
    stagnant_rows = [row for row in fund_rows if as_decimal(row.get("closing_qty")) > 0 and as_decimal(row.get("stagnant_days")) >= 90][:120]
    batch_rows = query_for(
        ("batch-trace",),
        f"""
        WITH tx AS (
            SELECT product_id, warehouse_id, location_id,
                   COALESCE(lot_no, '') AS lot_no,
                   COALESCE(serial_no, '') AS serial_no,
                   COALESCE(project_code, '') AS project_code,
                   COUNT(*) AS transaction_count,
                   MIN(COALESCE(transaction_date::date, created_at::date)) AS first_transaction_date,
                   MAX(COALESCE(transaction_date::date, created_at::date)) AS last_transaction_date,
                   SUM(CASE WHEN COALESCE(quantity,0) >= 0 THEN COALESCE(quantity,0) ELSE 0 END) AS inbound_qty,
                   SUM(CASE WHEN COALESCE(quantity,0) < 0 THEN ABS(COALESCE(quantity,0)) ELSE 0 END) AS outbound_qty
            FROM stock_transactions
            GROUP BY product_id, warehouse_id, location_id,
                     COALESCE(lot_no, ''), COALESCE(serial_no, ''), COALESCE(project_code, '')
        )
        SELECT bt.lot_no, bt.serial_no, bt.project_code,
               p.code AS product_code, p.name AS product_name, p.specification,
               w.name AS warehouse_name, COALESCE(l.code, bt.location) AS location_code,
               bt.quantity_available AS closing_qty,
               COALESCE(tx.inbound_qty,0) AS inbound_qty,
               COALESCE(tx.outbound_qty,0) AS outbound_qty,
               COALESCE(tx.transaction_count,0) AS transaction_count,
               tx.first_transaction_date, tx.last_transaction_date,
               bt.source_order_no, bt.status
        FROM batch_tracking bt
        LEFT JOIN products p ON p.id=bt.product_id
        LEFT JOIN warehouses w ON w.id=bt.warehouse_id
        LEFT JOIN locations l ON l.id=bt.location_id
        LEFT JOIN tx ON tx.product_id=bt.product_id
            AND COALESCE(tx.warehouse_id,0)=COALESCE(bt.warehouse_id,0)
            AND COALESCE(tx.location_id,0)=COALESCE(bt.location_id,0)
            AND tx.lot_no=COALESCE(bt.lot_no,'')
            AND tx.serial_no=COALESCE(bt.serial_no,'')
            AND tx.project_code=COALESCE(bt.project_code,'')
        {batch_where}
        ORDER BY bt.updated_at DESC NULLS LAST, bt.id DESC
        LIMIT 300
        """,
        batch_params,
    )
    balance_rows = query_for(
        ("balance", "available-stock", "location-stock"),
        f"""
        SELECT p.code AS product_code, p.name AS product_name, p.specification,
               w.name AS warehouse_name, l.code AS location_code, l.name AS location_name,
               ib.project_code, ib.lot_no, ib.serial_no,
               ib.quantity AS stock_qty,
               COALESCE(ib.locked_qty,0) AS locked_qty,
               COALESCE(ib.quantity,0) - COALESCE(ib.locked_qty,0) AS available_qty,
               ib.unit_cost,
               COALESCE(ib.quantity,0) * COALESCE(ib.unit_cost,0) AS stock_amount,
               ib.updated_at
        FROM inventory_balances ib
        LEFT JOIN products p ON p.id=ib.product_id
        LEFT JOIN warehouses w ON w.id=ib.warehouse_id
        LEFT JOIN locations l ON l.id=ib.location_id
        {balance_where}
        ORDER BY p.code, w.name, l.code, ib.lot_no, ib.serial_no
        LIMIT 300
        """,
        balance_params,
    )
    inventory_cost_summary_rows = query_for(
        ("inventory-cost-summary",),
        f"""
        WITH tx AS (
            SELECT product_id, warehouse_id, location_id,
                   COALESCE(lot_no, '') AS lot_no,
                   COALESCE(serial_no, '') AS serial_no,
                   COALESCE(project_code, '') AS project_code,
                   SUM(CASE WHEN COALESCE(transaction_date::date, created_at::date, CURRENT_DATE) BETWEEN %s AND %s AND COALESCE(quantity,0) >= 0 THEN COALESCE(quantity,0) ELSE 0 END) AS inbound_qty,
                   SUM(CASE WHEN COALESCE(transaction_date::date, created_at::date, CURRENT_DATE) BETWEEN %s AND %s AND COALESCE(quantity,0) >= 0 THEN COALESCE(quantity,0) * COALESCE(unit_cost,0) ELSE 0 END) AS inbound_amount,
                   SUM(CASE WHEN COALESCE(transaction_date::date, created_at::date, CURRENT_DATE) BETWEEN %s AND %s AND COALESCE(quantity,0) < 0 THEN ABS(COALESCE(quantity,0)) ELSE 0 END) AS outbound_qty,
                   SUM(CASE WHEN COALESCE(transaction_date::date, created_at::date, CURRENT_DATE) BETWEEN %s AND %s AND COALESCE(quantity,0) < 0 THEN ABS(COALESCE(quantity,0)) * COALESCE(unit_cost,0) ELSE 0 END) AS outbound_amount,
                   MAX(COALESCE(transaction_date::date, created_at::date)) AS last_transaction_date
            FROM stock_transactions
            GROUP BY product_id, warehouse_id, location_id,
                     COALESCE(lot_no, ''), COALESCE(serial_no, ''), COALESCE(project_code, '')
        )
        SELECT p.code AS product_code, p.name AS product_name, p.specification,
               w.name AS warehouse_name, l.code AS location_code, l.name AS location_name,
               ib.project_code, ib.lot_no, ib.serial_no,
               COALESCE(tx.inbound_qty,0) AS inbound_qty,
               COALESCE(tx.inbound_amount,0) AS inbound_amount,
               COALESCE(tx.outbound_qty,0) AS outbound_qty,
               COALESCE(tx.outbound_amount,0) AS outbound_amount,
               COALESCE(ib.quantity,0) AS closing_qty,
               COALESCE(ib.locked_qty,0) AS locked_qty,
               COALESCE(ib.quantity,0) - COALESCE(ib.locked_qty,0) AS available_qty,
               COALESCE(ib.unit_cost,0) AS unit_cost,
               COALESCE(ib.quantity,0) * COALESCE(ib.unit_cost,0) AS closing_amount,
               tx.last_transaction_date,
               ib.updated_at
        FROM inventory_balances ib
        LEFT JOIN products p ON p.id=ib.product_id
        LEFT JOIN warehouses w ON w.id=ib.warehouse_id
        LEFT JOIN locations l ON l.id=ib.location_id
        LEFT JOIN tx ON tx.product_id=ib.product_id
            AND COALESCE(tx.warehouse_id,0)=COALESCE(ib.warehouse_id,0)
            AND COALESCE(tx.location_id,0)=COALESCE(ib.location_id,0)
            AND tx.lot_no=COALESCE(ib.lot_no,'')
            AND tx.serial_no=COALESCE(ib.serial_no,'')
            AND tx.project_code=COALESCE(ib.project_code,'')
        {balance_where}
        ORDER BY closing_amount DESC NULLS LAST, p.code, w.name, l.code
        LIMIT 500
        """,
        (date_start, date_end, date_start, date_end, date_start, date_end, date_start, date_end) + balance_params,
    )
    for row in inventory_cost_summary_rows:
        row["cost_basis_note"] = "Ending value = inventory balance qty * balance unit cost; in/out value uses stock transaction unit cost."
    cost_detail_rows = _apply_inventory_cost_drilldown(cost_detail_rows)
    available_rows = [row for row in balance_rows if as_decimal(row.get("stock_qty")) != 0 or as_decimal(row.get("locked_qty")) != 0][:300]
    location_stock_rows = [row for row in balance_rows if row.get("warehouse_name") or row.get("location_code") or row.get("location_name")][:300]
    shortage_rows = query_for(
        ("shortage",),
        f"""
        SELECT p.code AS product_code, p.name AS product_name, p.specification,
               p.safety_stock,
               COALESCE(SUM(COALESCE(ib.quantity,0)),0) AS stock_qty,
               COALESCE(SUM(COALESCE(ib.locked_qty,0)),0) AS locked_qty,
               COALESCE(SUM(COALESCE(ib.quantity,0)-COALESCE(ib.locked_qty,0)),0) AS available_qty,
               GREATEST(COALESCE(p.safety_stock,0) - COALESCE(SUM(COALESCE(ib.quantity,0)-COALESCE(ib.locked_qty,0)),0),0) AS shortage_qty,
               p.default_supplier_name
        FROM products p
        LEFT JOIN inventory_balances ib ON ib.product_id=p.id
        LEFT JOIN warehouses w ON w.id=ib.warehouse_id
        LEFT JOIN locations l ON l.id=ib.location_id
        {balance_where.replace(' WHERE ', ' WHERE ', 1) if balance_where else ''}
        GROUP BY p.id, p.code, p.name, p.specification, p.safety_stock, p.default_supplier_name
        HAVING COALESCE(p.safety_stock,0) > COALESCE(SUM(COALESCE(ib.quantity,0)-COALESCE(ib.locked_qty,0)),0)
        ORDER BY shortage_qty DESC, p.code
        LIMIT 300
        """,
        balance_params,
    )
    turnover_rows = query_for(
        ("turnover",),
        f"""
        WITH issue AS (
            SELECT st.product_id,
                   SUM(CASE WHEN COALESCE(st.quantity,0) < 0 THEN ABS(COALESCE(st.quantity,0)) ELSE 0 END) AS outbound_qty
            FROM stock_transactions st
            LEFT JOIN products p ON p.id=st.product_id
            LEFT JOIN warehouses w ON w.id=st.warehouse_id
            LEFT JOIN locations l ON l.id=st.location_id
            {tx_where}
            GROUP BY st.product_id
        ),
        bal AS (
            SELECT product_id,
                   SUM(COALESCE(quantity,0)) AS stock_qty,
                   SUM(COALESCE(quantity,0) * COALESCE(unit_cost,0)) AS stock_amount
            FROM inventory_balances
            GROUP BY product_id
        )
        SELECT p.code AS product_code, p.name AS product_name, p.specification,
               COALESCE(issue.outbound_qty,0) AS outbound_qty,
               COALESCE(bal.stock_qty,0) AS ending_qty,
               (COALESCE(issue.outbound_qty,0) + COALESCE(bal.stock_qty,0)) / 2 AS avg_stock_qty,
               CASE WHEN (COALESCE(issue.outbound_qty,0) + COALESCE(bal.stock_qty,0)) / 2 > 0
                    THEN COALESCE(issue.outbound_qty,0) / ((COALESCE(issue.outbound_qty,0) + COALESCE(bal.stock_qty,0)) / 2)
                    ELSE 0 END AS turnover_times,
               CASE WHEN COALESCE(issue.outbound_qty,0) > 0
                    THEN 365 * ((COALESCE(issue.outbound_qty,0) + COALESCE(bal.stock_qty,0)) / 2) / COALESCE(issue.outbound_qty,0)
                    ELSE NULL END AS turnover_days,
               COALESCE(bal.stock_amount,0) AS stock_amount
        FROM products p
        LEFT JOIN issue ON issue.product_id=p.id
        LEFT JOIN bal ON bal.product_id=p.id
        WHERE COALESCE(issue.outbound_qty,0) > 0 OR COALESCE(bal.stock_qty,0) <> 0
        ORDER BY turnover_times DESC NULLS LAST, p.code
        LIMIT 300
        """,
        tx_params,
    )
    project_occupation_rows = query_for(
        ("project-occupation",),
        f"""
        SELECT COALESCE(ib.project_code,'') AS project_code,
               COALESCE(ib.serial_no,'') AS serial_no,
               p.code AS product_code, p.name AS product_name, p.specification,
               w.name AS warehouse_name, l.code AS location_code,
               SUM(COALESCE(ib.quantity,0)) AS stock_qty,
               SUM(COALESCE(ib.locked_qty,0)) AS locked_qty,
               SUM(COALESCE(ib.quantity,0) * COALESCE(ib.unit_cost,0)) AS stock_amount
        FROM inventory_balances ib
        LEFT JOIN products p ON p.id=ib.product_id
        LEFT JOIN warehouses w ON w.id=ib.warehouse_id
        LEFT JOIN locations l ON l.id=ib.location_id
        {balance_where}
        GROUP BY COALESCE(ib.project_code,''), COALESCE(ib.serial_no,''), p.code, p.name, p.specification, w.name, l.code
        HAVING COALESCE(ib.project_code,'') <> '' OR COALESCE(ib.serial_no,'') <> ''
        ORDER BY stock_amount DESC NULLS LAST, project_code, serial_no
        LIMIT 300
        """,
        balance_params,
    )
    subcontract_wip_rows = query_for(
        ("subcontract-wip",),
        """
        WITH issue AS (
            SELECT
                sio.supplier_id,
                sil.product_id,
                MIN(sio.date) AS first_issue_date,
                STRING_AGG(DISTINCT sio.issue_no, ', ' ORDER BY sio.issue_no) AS issue_nos,
                STRING_AGG(DISTINCT so.order_no, ', ' ORDER BY so.order_no) AS order_nos,
                STRING_AGG(DISTINCT NULLIF(COALESCE(sil.project_code, so.project_code, ''), ''), ', ') AS project_code,
                STRING_AGG(DISTINCT NULLIF(COALESCE(sil.serial_no, so.serial_no, ''), ''), ', ') AS serial_no,
                SUM(COALESCE(sil.quantity, 0)) AS issued_qty
            FROM subcontract_issue_lines sil
            JOIN subcontract_issue_orders sio ON sio.id=sil.issue_id
            LEFT JOIN subcontract_orders so ON so.id=COALESCE(sil.subcontract_order_id, sio.subcontract_order_id)
            WHERE COALESCE(sio.status,'') NOT IN ('已作废','已取消','void','voided','cancelled','canceled')
            GROUP BY sio.supplier_id, sil.product_id
        ),
        receive AS (
            SELECT
                sro.supplier_id,
                srl.product_id,
                MAX(sro.date) AS last_receive_date,
                STRING_AGG(DISTINCT sro.receive_no, ', ' ORDER BY sro.receive_no) AS receive_nos,
                SUM(COALESCE(srl.quantity, 0)) AS received_qty,
                SUM(COALESCE(srl.scrap_quantity, 0)) AS scrap_qty,
                SUM(COALESCE(sro.short_qty, 0)) AS short_qty
            FROM subcontract_receive_lines srl
            JOIN subcontract_receive_orders sro ON sro.id=srl.receive_id
            WHERE COALESCE(sro.status,'') NOT IN ('已作废','已取消','void','voided','cancelled','canceled')
            GROUP BY sro.supplier_id, srl.product_id
        )
        SELECT
            COALESCE(issue.order_nos, '') AS order_no,
            issue.first_issue_date AS issue_date,
            receive.last_receive_date,
            GREATEST(CURRENT_DATE - COALESCE(issue.first_issue_date, CURRENT_DATE), 0) AS days_outstanding,
            COALESCE(issue.project_code, '') AS project_code,
            COALESCE(issue.serial_no, '') AS serial_no,
            p.code AS product_code,
            p.name AS product_name,
            p.specification,
            COALESCE(issue.issued_qty, 0) AS issued_qty,
            COALESCE(receive.received_qty, 0) AS received_qty,
            COALESCE(receive.scrap_qty, 0) AS scrap_qty,
            COALESCE(receive.short_qty, 0) AS short_qty,
            COALESCE(issue.issued_qty, 0) - COALESCE(receive.received_qty, 0) - COALESCE(receive.scrap_qty, 0) - COALESCE(receive.short_qty, 0) AS wip_qty,
            s.name AS processor_name,
            CASE
                WHEN COALESCE(issue.issued_qty, 0) - COALESCE(receive.received_qty, 0) < 0 THEN '异常'
                WHEN COALESCE(issue.issued_qty, 0) - COALESCE(receive.received_qty, 0) > 0
                     AND CURRENT_DATE - COALESCE(issue.first_issue_date, CURRENT_DATE) > 30 THEN '超期'
                ELSE '正常'
            END AS status
        FROM issue
        FULL OUTER JOIN receive
          ON COALESCE(issue.supplier_id, 0)=COALESCE(receive.supplier_id, 0)
         AND COALESCE(issue.product_id, 0)=COALESCE(receive.product_id, 0)
        LEFT JOIN suppliers s ON s.id=COALESCE(issue.supplier_id, receive.supplier_id)
        LEFT JOIN products p ON p.id=COALESCE(issue.product_id, receive.product_id)
        WHERE COALESCE(issue.issued_qty, 0) - COALESCE(receive.received_qty, 0) - COALESCE(receive.scrap_qty, 0) - COALESCE(receive.short_qty, 0) <> 0
        ORDER BY
            CASE
                WHEN COALESCE(issue.issued_qty, 0) - COALESCE(receive.received_qty, 0) < 0 THEN 0
                WHEN COALESCE(issue.issued_qty, 0) - COALESCE(receive.received_qty, 0) > 0
                     AND CURRENT_DATE - COALESCE(issue.first_issue_date, CURRENT_DATE) > 30 THEN 1
                ELSE 2
            END,
            issue.first_issue_date NULLS FIRST,
            p.code
        LIMIT 300
        """
    )
    subcontract_execution_rows = query_for(
        ("subcontract-execution",),
        """
        WITH issue AS (
            SELECT subcontract_order_id, SUM(COALESCE(total_quantity, 0)) AS issued_qty
            FROM subcontract_issue_orders
            WHERE COALESCE(status,'') NOT IN ('已作废','已取消','void','voided','cancelled','canceled')
            GROUP BY subcontract_order_id
        ),
        receive AS (
            SELECT subcontract_order_id,
                   SUM(COALESCE(total_quantity, 0)) AS received_qty,
                   SUM(COALESCE(short_qty, 0)) AS short_qty,
                   SUM(COALESCE(scrap_qty, 0)) AS scrap_qty
            FROM subcontract_receive_orders
            WHERE COALESCE(status,'') NOT IN ('已作废','已取消','void','voided','cancelled','canceled')
            GROUP BY subcontract_order_id
        ),
        payable AS (
            SELECT
                COALESCE(
                    CASE WHEN doc_type='subcontract_order' THEN doc_id END,
                    sc.id
                ) AS subcontract_order_id,
                SUM(COALESCE(sp.amount, 0)) AS payable_amount,
                SUM(COALESCE(sp.paid_amount, 0)) AS paid_amount,
                SUM(COALESCE(sp.balance, 0)) AS payable_balance
            FROM supplier_payables sp
            LEFT JOIN subcontract_orders sc
              ON (sp.doc_type='subcontract_receive' AND sc.order_no=sp.doc_no)
              OR (sp.doc_type='subcontract_order' AND sc.id=sp.doc_id)
            WHERE sp.doc_type IN ('subcontract_order', 'subcontract_receive')
            GROUP BY COALESCE(CASE WHEN doc_type='subcontract_order' THEN doc_id END, sc.id)
        )
        SELECT
            so.order_no,
            so.order_date,
            s.name AS processor_name,
            p.code AS product_code,
            COALESCE(so.material_name, p.name) AS product_name,
            COALESCE(so.material_spec, p.specification) AS specification,
            so.project_code,
            so.serial_no,
            COALESCE(so.quantity, 0) AS order_qty,
            COALESCE(issue.issued_qty, 0) AS issued_qty,
            COALESCE(receive.received_qty, 0) AS received_qty,
            COALESCE(receive.short_qty, 0) AS short_qty,
            COALESCE(receive.scrap_qty, 0) AS scrap_qty,
            GREATEST(COALESCE(so.quantity, 0) - COALESCE(receive.received_qty, 0) - COALESCE(receive.short_qty, 0) - COALESCE(receive.scrap_qty, 0), 0) AS open_qty,
            GREATEST(COALESCE(issue.issued_qty, 0) - COALESCE(receive.received_qty, 0) - COALESCE(receive.short_qty, 0) - COALESCE(receive.scrap_qty, 0), 0) AS wip_qty,
            COALESCE(payable.payable_amount, 0) AS payable_amount,
            COALESCE(payable.payable_balance, 0) AS payable_balance,
            so.status
        FROM subcontract_orders so
        LEFT JOIN suppliers s ON s.id=so.supplier_id
        LEFT JOIN products p ON p.id=so.product_id
        LEFT JOIN issue ON issue.subcontract_order_id=so.id
        LEFT JOIN receive ON receive.subcontract_order_id=so.id
        LEFT JOIN payable ON payable.subcontract_order_id=so.id
        WHERE COALESCE(so.status,'') NOT IN ('已作废','已取消','void','voided','cancelled','canceled')
        ORDER BY so.order_date DESC NULLS LAST, so.id DESC
        LIMIT 300
        """
    )
    subcontract_inout_detail_rows = query_for(
        ("subcontract-inout-detail",),
        """
        SELECT
            sio.date AS doc_date,
            sio.issue_no AS doc_no,
            '委外发料' AS doc_action,
            so.order_no,
            s.name AS processor_name,
            p.code AS product_code,
            COALESCE(sil.material_name, p.name) AS product_name,
            COALESCE(sil.material_spec, p.specification) AS specification,
            sil.project_code,
            sil.serial_no,
            COALESCE(sil.quantity, 0) AS issue_qty,
            0::numeric AS receive_qty,
            0::numeric AS short_qty,
            0::numeric AS scrap_qty,
            COALESCE(so.unit_price, 0) AS unit_cost,
            COALESCE(sil.quantity, 0) * COALESCE(so.unit_price, 0) AS amount,
            sio.status
        FROM subcontract_issue_lines sil
        JOIN subcontract_issue_orders sio ON sio.id=sil.issue_id
        LEFT JOIN subcontract_orders so ON so.id=COALESCE(sil.subcontract_order_id, sio.subcontract_order_id)
        LEFT JOIN suppliers s ON s.id=sio.supplier_id
        LEFT JOIN products p ON p.id=sil.product_id
        WHERE COALESCE(sio.status,'') NOT IN ('已作废','已取消','void','voided','cancelled','canceled')
        UNION ALL
        SELECT
            sro.date AS doc_date,
            sro.receive_no AS doc_no,
            '委外收回' AS doc_action,
            so.order_no,
            s.name AS processor_name,
            p.code AS product_code,
            COALESCE(srl.material_name, p.name) AS product_name,
            COALESCE(srl.material_spec, p.specification) AS specification,
            srl.project_code,
            srl.serial_no,
            0::numeric AS issue_qty,
            COALESCE(srl.quantity, 0) AS receive_qty,
            COALESCE(sro.short_qty, 0) AS short_qty,
            COALESCE(srl.scrap_quantity, 0) AS scrap_qty,
            COALESCE(so.unit_price, 0) AS unit_cost,
            COALESCE(srl.quantity, 0) * COALESCE(so.unit_price, 0) AS amount,
            sro.status
        FROM subcontract_receive_lines srl
        JOIN subcontract_receive_orders sro ON sro.id=srl.receive_id
        LEFT JOIN subcontract_orders so ON so.id=COALESCE(srl.subcontract_order_id, sro.subcontract_order_id)
        LEFT JOIN suppliers s ON s.id=sro.supplier_id
        LEFT JOIN products p ON p.id=srl.product_id
        WHERE COALESCE(sro.status,'') NOT IN ('已作废','已取消','void','voided','cancelled','canceled')
        ORDER BY doc_date DESC NULLS LAST, doc_no DESC
        LIMIT 300
        """
    )
    subcontract_variance_rows = query_for(
        ("subcontract-variance",),
        """
        SELECT
            sro.receive_no,
            sro.date AS receive_date,
            so.order_no,
            s.name AS processor_name,
            so.project_code AS project_code,
            so.serial_no AS serial_no,
            COALESCE(sro.total_quantity, 0) AS received_qty,
            COALESCE(sro.short_qty, 0) AS short_qty,
            COALESCE(sro.scrap_qty, 0) AS scrap_qty,
            COALESCE(sro.deduction_amount, 0) AS deduction_amount,
            COALESCE(sro.variance_amount, 0) AS variance_amount,
            sro.variance_reason,
            sro.responsible_party,
            sro.status
        FROM subcontract_receive_orders sro
        LEFT JOIN subcontract_orders so ON so.id=sro.subcontract_order_id
        LEFT JOIN suppliers s ON s.id=sro.supplier_id
        WHERE COALESCE(sro.status,'') NOT IN ('已作废','已取消','void','voided','cancelled','canceled')
          AND (
              COALESCE(sro.short_qty, 0) <> 0
           OR COALESCE(sro.scrap_qty, 0) <> 0
           OR COALESCE(sro.deduction_amount, 0) <> 0
           OR COALESCE(sro.variance_amount, 0) <> 0
           OR COALESCE(sro.variance_reason, '') <> ''
          )
        ORDER BY sro.date DESC NULLS LAST, sro.id DESC
        LIMIT 300
        """
    )
    subcontract_payable_reconcile_rows = query_for(
        ("subcontract-payable-reconcile",),
        """
        WITH payment AS (
            SELECT payable_id, SUM(COALESCE(applied_amount, 0)) AS settled_amount
            FROM supplier_payment_settlements
            GROUP BY payable_id
        )
        SELECT
            sp.doc_no,
            sp.doc_date,
            sp.doc_type,
            COALESCE(so.order_no, sro.receive_no, sp.doc_no) AS subcontract_doc_no,
            s.name AS processor_name,
            COALESCE(sp.project_code, so.project_code) AS project_code,
            COALESCE(sp.serial_no, so.serial_no) AS serial_no,
            COALESCE(sp.amount, 0) AS payable_amount,
            COALESCE(payment.settled_amount, sp.paid_amount, 0) AS paid_amount,
            COALESCE(sp.balance, GREATEST(COALESCE(sp.amount, 0) - COALESCE(payment.settled_amount, sp.paid_amount, 0), 0)) AS payable_balance,
            sp.due_date,
            GREATEST(CURRENT_DATE - COALESCE(sp.due_date, CURRENT_DATE), 0) AS overdue_days,
            sp.status,
            sp.finance_remark
        FROM supplier_payables sp
        LEFT JOIN payment ON payment.payable_id=sp.id
        LEFT JOIN subcontract_orders so
          ON sp.doc_type='subcontract_order' AND so.id=sp.doc_id
        LEFT JOIN subcontract_receive_orders sro
          ON sp.doc_type='subcontract_receive' AND sro.id=sp.doc_id
        LEFT JOIN suppliers s ON s.id=COALESCE(sp.supplier_id, so.supplier_id, sro.supplier_id)
        WHERE sp.doc_type IN ('subcontract_order', 'subcontract_receive')
        ORDER BY sp.doc_date DESC NULLS LAST, sp.id DESC
        LIMIT 300
        """
    )
    check_difference_rows = query_for(
        ("check-difference",),
        f"""
        SELECT COALESCE(st.transaction_date::date, st.created_at::date) AS transaction_date,
               st.reference_no, p.code AS product_code, p.name AS product_name, p.specification,
               w.name AS warehouse_name, l.code AS location_code,
               st.project_code, st.lot_no, st.serial_no,
               CASE WHEN COALESCE(st.quantity,0) > 0 THEN COALESCE(st.quantity,0) ELSE 0 END AS gain_qty,
               CASE WHEN COALESCE(st.quantity,0) < 0 THEN ABS(COALESCE(st.quantity,0)) ELSE 0 END AS loss_qty,
               COALESCE(st.unit_cost,0) AS unit_cost,
               ABS(COALESCE(st.quantity,0) * COALESCE(st.unit_cost,0)) AS diff_amount,
               st.remark
        FROM stock_transactions st
        LEFT JOIN products p ON p.id=st.product_id
        LEFT JOIN warehouses w ON w.id=st.warehouse_id
        LEFT JOIN locations l ON l.id=st.location_id
        {tx_where + (' AND ' if tx_where else ' WHERE ') + "(st.transaction_type ILIKE %s OR st.source_type ILIKE %s OR st.source_doc_type ILIKE %s)"}
        ORDER BY COALESCE(st.transaction_date, st.created_at) DESC NULLS LAST, st.id DESC
        LIMIT 300
        """,
        tx_params + ("%盘点%", "%check%", "%check%"),
    )
    ledger_in = sum(as_decimal(r.get("inbound_qty")) for r in ledger_rows)
    ledger_out = sum(as_decimal(r.get("outbound_qty")) for r in ledger_rows)
    account_closing_amount = sum(as_decimal(r.get("closing_amount")) for r in account_book_rows)
    closing_qty = sum(as_decimal(r.get("closing_qty")) for r in fund_rows)
    stock_amount = sum(as_decimal(r.get("stock_amount")) for r in fund_rows)
    return {
        "title": "库存报表",
        "subtitle": "只读库存报表，按物料、仓库、库位、批号、机号和项目号核对明细账、收发存、资金占用和批次追溯。",
        "filters": filters,
        "metrics": [
            {"label": "流水行数", "value": len(ledger_rows), "hint": "标准库存明细账"},
            {"label": "期间入库", "value": qty_metric(ledger_in), "hint": "按正向库存流水汇总"},
            {"label": "期间出库", "value": qty_metric(ledger_out), "hint": "按负向库存流水绝对值汇总"},
            {"label": "台账金额", "value": money_metric(account_closing_amount), "hint": "库存台账期末金额"},
            {"label": "期末数量", "value": qty_metric(closing_qty), "hint": "来自库存余额"},
            {"label": "库存金额", "value": money_metric(stock_amount), "hint": "期末数量 * 单位成本"},
            {"label": "批次记录", "value": len(batch_rows), "hint": "批次/机号追溯"},
        ],
        "sections": [
            {"title": "库存成本总账", "key": "inventory-cost-summary", "url": "/finance/inventory-cost/summary", "rows": inventory_cost_summary_rows, "columns": columns(("product_code", "物料编码"), ("product_name", "物料名称"), ("specification", "规格"), ("warehouse_name", "仓库"), ("location_code", "库位"), ("project_code", "项目号"), ("lot_no", "批号"), ("serial_no", "机号"), ("inbound_qty", "本期入库数量"), ("inbound_amount", "本期入库成本金额"), ("outbound_qty", "本期出库数量"), ("outbound_amount", "本期出库成本金额"), ("closing_qty", "期末数量"), ("locked_qty", "锁定数量"), ("available_qty", "可用数量"), ("unit_cost", "期末单位成本"), ("closing_amount", "期末库存成本金额"), ("last_transaction_date", "最后流水日期"), ("updated_at", "余额更新时间"), ("cost_basis_note", "成本依据"))},
            {"title": "库存成本明细账", "key": "inventory-cost-detail", "url": "/finance/inventory-cost/detail", "rows": cost_detail_rows, "columns": _with_url_key(columns(("transaction_date", "日期"), ("source_doc_label", "来源单号"), ("source_type", "来源类型"), ("transaction_type", "库存动作"), ("product_code", "物料编码"), ("product_name", "物料名称"), ("specification", "规格"), ("warehouse_name", "仓库"), ("location_code", "库位"), ("project_code", "项目号"), ("lot_no", "批号"), ("serial_no", "机号"), ("inbound_qty", "入库数量"), ("outbound_qty", "出库数量"), ("net_qty", "结存影响数量"), ("unit_cost", "成本单价"), ("inbound_amount", "入库成本金额"), ("outbound_amount", "出库成本金额"), ("balance_impact_amount", "结存影响金额"), ("cost_basis_note", "成本依据"), ("remark", "备注")), "source_doc_label", "source_doc_url")},
            {"title": "标准库存明细账", "key": "ledger", "url": "/inventory/reports/ledger", "rows": ledger_rows, "columns": columns(("transaction_date", "日期"), ("reference_no", "来源单号"), ("transaction_type", "类型"), ("product_code", "物料编码"), ("product_name", "物料名称"), ("specification", "规格"), ("warehouse_name", "仓库"), ("location_code", "库位"), ("project_code", "项目号"), ("lot_no", "批号"), ("serial_no", "机号"), ("inbound_qty", "入库"), ("outbound_qty", "出库"), ("net_qty", "结存影响"), ("unit_cost", "单位成本"), ("amount", "金额"))},
            {"title": "库存台账", "key": "account-book", "url": "/inventory/reports/account-book", "rows": account_book_rows, "columns": columns(("product_code", "物料编码"), ("product_name", "物料名称"), ("specification", "规格"), ("warehouse_name", "仓库"), ("location_code", "库位"), ("project_code", "项目号"), ("lot_no", "批号"), ("serial_no", "机号"), ("opening_qty", "期初数量"), ("opening_amount", "期初金额"), ("inbound_qty", "本期入库"), ("inbound_amount", "入库金额"), ("outbound_qty", "本期出库"), ("outbound_amount", "出库金额"), ("closing_qty", "期末数量"), ("closing_amount", "期末金额"), ("avg_unit_cost", "平均成本"))},
            {"title": "库存月报表", "key": "monthly", "url": "/inventory/reports/monthly", "rows": monthly_rows, "columns": columns(("report_month", "月份"), ("opening_qty", "期初数量"), ("opening_amount", "期初金额"), ("inbound_qty", "本月入库"), ("inbound_amount", "入库金额"), ("outbound_qty", "本月出库"), ("outbound_amount", "出库金额"), ("closing_qty", "期末数量"), ("closing_amount", "期末金额"))},
            {"title": "收发存汇总表", "key": "inout-summary", "url": "/inventory/reports/inout-summary", "rows": summary_rows, "columns": columns(("product_code", "物料编码"), ("product_name", "物料名称"), ("specification", "规格"), ("warehouse_name", "仓库"), ("location_code", "库位"), ("project_code", "项目号"), ("lot_no", "批号"), ("serial_no", "机号"), ("opening_qty", "期初"), ("inbound_qty", "入库"), ("outbound_qty", "出库"), ("closing_qty", "期末"), ("purchase_pending_qty", "采购未入"), ("sales_pending_qty", "销售未出"), ("avg_unit_cost", "平均成本"), ("closing_amount", "期末金额"))},
            {"title": "库存余额表", "key": "balance", "url": "/inventory/reports/balance", "rows": balance_rows, "columns": columns(("product_code", "物料编码"), ("product_name", "物料名称"), ("specification", "规格"), ("warehouse_name", "仓库"), ("location_code", "库位"), ("project_code", "项目号"), ("lot_no", "批号"), ("serial_no", "机号"), ("stock_qty", "库存数量"), ("locked_qty", "锁定数量"), ("available_qty", "可用库存"), ("unit_cost", "单位成本"), ("stock_amount", "库存金额"), ("updated_at", "更新时间"))},
            {"title": "收发存明细表", "key": "inout-detail", "url": "/inventory/reports/inout-detail", "rows": ledger_rows, "columns": columns(("transaction_date", "日期"), ("reference_no", "来源单号"), ("source_type", "来源类型"), ("transaction_type", "类型"), ("product_code", "物料编码"), ("product_name", "物料名称"), ("specification", "规格"), ("warehouse_name", "仓库"), ("location_code", "库位"), ("project_code", "项目号"), ("lot_no", "批号"), ("serial_no", "机号"), ("inbound_qty", "入库数量"), ("outbound_qty", "出库数量"), ("net_qty", "结存影响"), ("unit_cost", "单位成本"), ("amount", "金额"))},
            {"title": "库位库存表", "key": "location-stock", "url": "/inventory/reports/location-stock", "rows": location_stock_rows, "columns": columns(("warehouse_name", "仓库"), ("location_code", "库位编码"), ("location_name", "库位名称"), ("product_code", "物料编码"), ("product_name", "物料名称"), ("specification", "规格"), ("project_code", "项目号"), ("lot_no", "批号"), ("serial_no", "机号"), ("stock_qty", "库存数量"), ("available_qty", "可用库存"), ("stock_amount", "库存金额"))},
            {"title": "可用库存表", "key": "available-stock", "url": "/inventory/reports/available-stock", "rows": available_rows, "columns": columns(("product_code", "物料编码"), ("product_name", "物料名称"), ("specification", "规格"), ("warehouse_name", "仓库"), ("location_code", "库位"), ("project_code", "项目号"), ("lot_no", "批号"), ("serial_no", "机号"), ("stock_qty", "库存数量"), ("locked_qty", "锁定数量"), ("available_qty", "可用库存"))},
            {"title": "安全库存/短缺报表", "key": "shortage", "url": "/inventory/reports/shortage", "rows": shortage_rows, "columns": columns(("product_code", "物料编码"), ("product_name", "物料名称"), ("specification", "规格"), ("safety_stock", "安全库存"), ("stock_qty", "库存数量"), ("locked_qty", "锁定数量"), ("available_qty", "可用库存"), ("shortage_qty", "短缺数量"), ("default_supplier_name", "默认供应商"))},
            {"title": "库存周转率报表", "key": "turnover", "url": "/inventory/reports/turnover", "rows": turnover_rows, "columns": columns(("product_code", "物料编码"), ("product_name", "物料名称"), ("specification", "规格"), ("outbound_qty", "期间出库数量"), ("ending_qty", "期末库存"), ("avg_stock_qty", "平均库存"), ("turnover_times", "周转次数"), ("turnover_days", "周转天数"), ("stock_amount", "库存金额"))},
            {"title": "项目/机号库存占用表", "key": "project-occupation", "url": "/inventory/reports/project-occupation", "rows": project_occupation_rows, "columns": columns(("project_code", "项目号"), ("serial_no", "机号"), ("product_code", "物料编码"), ("product_name", "物料名称"), ("specification", "规格"), ("warehouse_name", "仓库"), ("location_code", "库位"), ("stock_qty", "库存数量"), ("locked_qty", "锁定数量"), ("stock_amount", "库存金额"))},
            {"title": "委外发出未回报表", "key": "subcontract-wip", "url": "/inventory/reports/subcontract-wip", "rows": subcontract_wip_rows, "columns": columns(("processor_name", "加工商"), ("product_code", "物料编码"), ("product_name", "物料名称"), ("specification", "规格"), ("issued_qty", "发出数量"), ("received_qty", "收回数量"), ("wip_qty", "在制数量"), ("issue_date", "发料日期"), ("last_receive_date", "最后收货日期"), ("days_outstanding", "未回天数"), ("status", "状态"), ("order_no", "委外单号"), ("project_code", "项目号"), ("serial_no", "机号"))},
            {"title": "委外订单执行报表", "key": "subcontract-execution", "url": "/inventory/reports/subcontract-execution", "rows": subcontract_execution_rows, "columns": columns(("order_no", "委外单号"), ("order_date", "下单日期"), ("processor_name", "加工商"), ("product_code", "物料编码"), ("product_name", "物料名称"), ("specification", "规格"), ("project_code", "项目号"), ("serial_no", "机号"), ("order_qty", "委外数量"), ("issued_qty", "已发料"), ("received_qty", "已收回"), ("short_qty", "短收"), ("scrap_qty", "报废"), ("open_qty", "未完数量"), ("wip_qty", "在制数量"), ("payable_amount", "应付金额"), ("payable_balance", "应付余额"), ("status", "状态"))},
            {"title": "委外收发明细报表", "key": "subcontract-inout-detail", "url": "/inventory/reports/subcontract-inout-detail", "rows": subcontract_inout_detail_rows, "columns": columns(("doc_date", "日期"), ("doc_no", "单号"), ("doc_action", "动作"), ("order_no", "委外单号"), ("processor_name", "加工商"), ("product_code", "物料编码"), ("product_name", "物料名称"), ("specification", "规格"), ("project_code", "项目号"), ("serial_no", "机号"), ("issue_qty", "发料数量"), ("receive_qty", "收回数量"), ("short_qty", "短收数量"), ("scrap_qty", "报废数量"), ("unit_cost", "单位成本"), ("amount", "金额"), ("status", "状态"))},
            {"title": "委外短少报废差异报表", "key": "subcontract-variance", "url": "/inventory/reports/subcontract-variance", "rows": subcontract_variance_rows, "columns": columns(("receive_no", "收回单号"), ("receive_date", "收回日期"), ("order_no", "委外单号"), ("processor_name", "加工商"), ("project_code", "项目号"), ("serial_no", "机号"), ("received_qty", "收回数量"), ("short_qty", "短收数量"), ("scrap_qty", "报废数量"), ("deduction_amount", "扣款金额"), ("variance_amount", "差异金额"), ("variance_reason", "差异原因"), ("responsible_party", "责任方"), ("status", "状态"))},
            {"title": "委外应付对账报表", "key": "subcontract-payable-reconcile", "url": "/inventory/reports/subcontract-payable-reconcile", "rows": subcontract_payable_reconcile_rows, "columns": columns(("doc_no", "应付单号"), ("doc_date", "应付日期"), ("doc_type", "来源类型"), ("subcontract_doc_no", "委外来源单号"), ("processor_name", "加工商"), ("project_code", "项目号"), ("serial_no", "机号"), ("payable_amount", "应付金额"), ("paid_amount", "已付金额"), ("payable_balance", "应付余额"), ("due_date", "到期日"), ("overdue_days", "逾期天数"), ("status", "状态"), ("finance_remark", "财务备注"))},
            {"title": "盘点差异汇总表", "key": "check-difference", "url": "/inventory/reports/check-difference", "rows": check_difference_rows, "columns": columns(("transaction_date", "日期"), ("reference_no", "盘点/来源单"), ("product_code", "物料编码"), ("product_name", "物料名称"), ("specification", "规格"), ("warehouse_name", "仓库"), ("location_code", "库位"), ("project_code", "项目号"), ("lot_no", "批号"), ("serial_no", "机号"), ("gain_qty", "盘盈数量"), ("loss_qty", "盘亏数量"), ("unit_cost", "单位成本"), ("diff_amount", "差异金额"), ("remark", "说明"))},
            {"title": "库存资金占用表", "key": "fund-occupation", "url": "/inventory/reports/fund-occupation", "rows": fund_rows, "columns": columns(("product_code", "物料编码"), ("product_name", "物料名称"), ("specification", "规格"), ("warehouse_name", "仓库"), ("location_code", "库位"), ("project_code", "项目号"), ("lot_no", "批号"), ("serial_no", "机号"), ("closing_qty", "期末数量"), ("locked_qty", "锁定数量"), ("unit_cost", "单位成本"), ("stock_amount", "库存金额"), ("last_transaction_date", "最后流水"), ("stagnant_days", "呆滞天数"), ("occupation_level", "占用等级"))},
            {"title": "呆滞料分析", "key": "stagnant", "url": "/inventory/reports/fund-occupation", "rows": stagnant_rows, "columns": columns(("product_code", "物料编码"), ("product_name", "物料名称"), ("specification", "规格"), ("warehouse_name", "仓库"), ("location_code", "库位"), ("project_code", "项目号"), ("lot_no", "批号"), ("serial_no", "机号"), ("closing_qty", "期末数量"), ("stock_amount", "库存金额"), ("last_transaction_date", "最后流水"), ("stagnant_days", "呆滞天数"))},
            {"title": "批次追溯报表", "key": "batch-trace", "url": "/inventory/reports/batch-trace", "rows": batch_rows, "columns": columns(("lot_no", "批号"), ("serial_no", "机号"), ("project_code", "项目号"), ("product_code", "物料编码"), ("product_name", "物料名称"), ("specification", "规格"), ("warehouse_name", "仓库"), ("location_code", "库位"), ("closing_qty", "期末数量"), ("inbound_qty", "入库"), ("outbound_qty", "出库"), ("transaction_count", "流水笔数"), ("first_transaction_date", "首次流水"), ("last_transaction_date", "最后流水"), ("source_order_no", "来源单号"), ("status", "状态"))},
        ],
    }


def build_module_report_config(
    kind,
    query_rows,
    sum_value,
    as_decimal,
    money_metric,
    qty_metric,
    columns,
    request_args,
):
    if kind == "sales":
        where, params, filters = report_where_from_args(
            request_args,
            "so.order_date",
            ("so.order_no", "c.name", "so.project_code", "so.serial_no"),
            "so.status",
            ("so.project_code", "so.serial_no"),
        )
        scope_filter = request_args.get("_data_scope_filter") if hasattr(request_args, "get") else None
        if scope_filter:
            scope_clause, scoped_params = scope_filter({"project": "so.project_code", "serial": "so.serial_no"}, params=params)
            if scope_clause:
                if where:
                    where += scope_clause
                else:
                    where = " WHERE 1=1" + scope_clause
                params = scoped_params
        rows = query_rows(
            f"""
            SELECT so.order_no, so.order_date, c.name AS partner, so.project_code, so.serial_no,
                   so.total_amount, so.shipped_amount,
                   GREATEST(COALESCE(so.total_amount,0)-COALESCE(so.shipped_amount,0),0) AS pending_amount,
                   so.status
            FROM sales_orders so
            LEFT JOIN customers c ON c.id=so.customer_id
            {where}
            ORDER BY so.order_date DESC NULLS LAST, so.id DESC
            LIMIT 300
            """,
            params,
        )
        receivable_scope_clause = ""
        receivable_scope_params = ()
        if scope_filter:
            receivable_scope_clause, receivable_scope_params = scope_filter({"project": "cr.project_code", "serial": "cr.serial_no"})
        receivable_rows = query_rows(
            f"""
            SELECT cr.source_no AS order_no, cr.receivable_date AS order_date, c.name AS partner,
                   cr.project_code, cr.serial_no, cr.total_amount, cr.received_amount, cr.balance, cr.status,
                   cr.due_date,
                   GREATEST(CURRENT_DATE - COALESCE(cr.due_date, CURRENT_DATE), 0) AS overdue_days
            FROM customer_receivables cr
            LEFT JOIN customers c ON c.id=cr.customer_id
            WHERE COALESCE(cr.balance, 0) > 0{receivable_scope_clause}
            ORDER BY cr.due_date NULLS FIRST, cr.id DESC
            LIMIT 120
            """,
            receivable_scope_params,
        )
        receipt_scope_clause = ""
        receipt_scope_params = ()
        if scope_filter:
            receipt_scope_clause, receipt_scope_params = scope_filter({"project": "r.project_code", "serial": "r.serial_no"})
        receipt_rows = query_rows(
            f"""
            SELECT r.receipt_no, r.receipt_date, c.name AS partner, r.source_no,
                   r.project_code, r.serial_no, r.amount, r.payment_method, r.status
            FROM customer_receipts r
            LEFT JOIN customers c ON c.id=r.customer_id
            WHERE 1=1{receipt_scope_clause}
            ORDER BY r.receipt_date DESC NULLS LAST, r.id DESC
            LIMIT 120
            """,
            receipt_scope_params,
        )
        invoice_scope_clause = ""
        invoice_scope_params = ()
        if scope_filter:
            invoice_scope_clause, invoice_scope_params = scope_filter({"project": "si.project_code", "serial": "si.serial_no"})
        invoice_rows = query_rows(
            f"""
            SELECT si.invoice_no, si.invoice_date, c.name AS partner, si.source_no,
                   si.project_code, si.serial_no, si.amount_with_tax, si.tax_amount, si.status
            FROM sales_invoices si
            LEFT JOIN customers c ON c.id=si.customer_id
            WHERE 1=1{invoice_scope_clause}
            ORDER BY si.invoice_date DESC NULLS LAST, si.id DESC
            LIMIT 120
            """,
            invoice_scope_params,
        )
        return_scope_clause = ""
        return_scope_params = ()
        if scope_filter:
            return_scope_clause, return_scope_params = scope_filter({"project": "sr.project_code", "serial": "sr.serial_no"})
        return_rows = query_rows(
            f"""
            SELECT sr.return_no, sr.return_date, c.name AS partner,
                   COALESCE(NULLIF(sr.source_no,''), sr.source_order_no) AS source_no,
                   sr.project_code, sr.serial_no, sr.amount_with_tax, sr.status
            FROM sales_returns sr
            LEFT JOIN customers c ON c.id=sr.customer_id
            WHERE 1=1{return_scope_clause}
            ORDER BY sr.return_date DESC NULLS LAST, sr.id DESC
            LIMIT 120
            """,
            return_scope_params,
        )
        total = sum(as_decimal(r.get("total_amount")) for r in rows)
        pending = sum(as_decimal(r.get("pending_amount")) for r in rows)
        receivable_balance = sum(as_decimal(r.get("balance")) for r in receivable_rows)
        received_total = sum(as_decimal(r.get("amount")) for r in receipt_rows)
        invoiced_total = sum(as_decimal(r.get("amount_with_tax")) for r in invoice_rows)
        returned_total = sum(as_decimal(r.get("amount_with_tax")) for r in return_rows)
        pending_rows = [row for row in rows if as_decimal(row.get("pending_amount")) > 0][:80]
        overdue_receivable_rows = [row for row in receivable_rows if as_decimal(row.get("overdue_days")) > 0][:80]
        customer_summary = {}
        for row in rows:
            partner = row.get("partner") or "-"
            bucket = customer_summary.setdefault(
                partner,
                {
                    "partner": partner,
                    "order_count": 0,
                    "total_amount": Decimal("0"),
                    "pending_amount": Decimal("0"),
                },
            )
            bucket["order_count"] += 1
            bucket["total_amount"] += as_decimal(row.get("total_amount"))
            bucket["pending_amount"] += as_decimal(row.get("pending_amount"))
        customer_rows = sorted(customer_summary.values(), key=lambda item: item["pending_amount"], reverse=True)[:50]
        return {
            "title": "销售报表",
            "subtitle": "销售订单、发货、应收、回款、开票、退货和项目/机号执行统计。",
            "filters": filters,
            "metrics": [
                {"label": "订单数", "value": len(rows), "hint": "当前筛选"},
                {"label": "销售含税金额", "value": money_metric(total), "hint": "订单含税金额合计"},
                {"label": "未交金额", "value": money_metric(pending), "hint": "订单金额 - 已发货金额"},
                {"label": "应收余额", "value": money_metric(receivable_balance), "hint": "未清应收余额"},
                {"label": "已回款金额", "value": money_metric(received_total), "hint": "客户回款金额"},
                {"label": "已开票金额", "value": money_metric(invoiced_total), "hint": "销售发票含税金额"},
                {"label": "退货金额", "value": money_metric(returned_total), "hint": "销售退货含税金额"},
                {"label": "客户数", "value": len({r.get("partner") for r in rows if r.get("partner")}), "hint": "涉及客户"},
            ],
            "sections": [
                {"title": "销售未交专题", "rows": pending_rows, "columns": columns(("order_no", "销售订单"), ("order_date", "日期"), ("partner", "客户"), ("project_code", "项目号"), ("serial_no", "机号"), ("total_amount", "含税金额"), ("shipped_amount", "已发货"), ("pending_amount", "未交"), ("status", "状态"))},
                {"title": "应收逾期专题", "rows": overdue_receivable_rows, "columns": columns(("order_no", "来源单"), ("due_date", "到期日"), ("partner", "客户"), ("project_code", "项目号"), ("serial_no", "机号"), ("total_amount", "应收金额"), ("received_amount", "已收"), ("balance", "余额"), ("overdue_days", "逾期天数"), ("status", "状态"))},
                {"title": "客户未交排行", "rows": customer_rows, "columns": columns(("partner", "客户"), ("order_count", "订单数"), ("total_amount", "销售金额"), ("pending_amount", "未交金额"))},
                {"title": "客户回款明细", "rows": receipt_rows, "columns": columns(("receipt_no", "回款单"), ("receipt_date", "回款日期"), ("partner", "客户"), ("source_no", "来源单"), ("project_code", "项目号"), ("serial_no", "机号"), ("amount", "回款金额"), ("payment_method", "结算方式"), ("status", "状态"))},
                {"title": "销售开票明细", "rows": invoice_rows, "columns": columns(("invoice_no", "发票号"), ("invoice_date", "开票日期"), ("partner", "客户"), ("source_no", "来源单"), ("project_code", "项目号"), ("serial_no", "机号"), ("amount_with_tax", "含税金额"), ("tax_amount", "税额"), ("status", "状态"))},
                {"title": "销售退货明细", "rows": return_rows, "columns": columns(("return_no", "退货单"), ("return_date", "退货日期"), ("partner", "客户"), ("source_no", "来源单"), ("project_code", "项目号"), ("serial_no", "机号"), ("amount_with_tax", "含税金额"), ("status", "状态"))},
                {"title": "销售执行明细", "rows": rows, "columns": columns(("order_no", "销售订单"), ("order_date", "日期"), ("partner", "客户"), ("project_code", "项目号"), ("serial_no", "机号"), ("total_amount", "含税金额"), ("shipped_amount", "已发货"), ("pending_amount", "未交"), ("status", "状态"))},
            ],
        }
    if kind == "purchase":
        where, params, filters = report_where_from_args(
            request_args,
            "po.order_date",
            ("po.order_no", "s.name", "po.project_code", "po.serial_no"),
            "po.status",
            ("po.project_code", "po.serial_no"),
        )
        scope_filter = request_args.get("_data_scope_filter") if hasattr(request_args, "get") else None
        if scope_filter:
            scope_clause, scoped_params = scope_filter({"project": "po.project_code", "serial": "po.serial_no"}, params=params)
            if scope_clause:
                if where:
                    where += scope_clause
                else:
                    where = " WHERE 1=1" + scope_clause
                params = scoped_params
        rows = query_rows(
            f"""
            SELECT po.order_no, po.order_date, s.name AS partner, po.project_code, po.serial_no,
                   po.total_amount, po.received_amount,
                   GREATEST(COALESCE(po.total_amount,0)-COALESCE(po.received_amount,0),0) AS pending_amount,
                   po.status
            FROM purchase_orders po
            LEFT JOIN suppliers s ON s.id=po.supplier_id
            {where}
            ORDER BY po.order_date DESC NULLS LAST, po.id DESC
            LIMIT 300
            """,
            params,
        )
        total = sum(as_decimal(r.get("total_amount")) for r in rows)
        pending = sum(as_decimal(r.get("pending_amount")) for r in rows)
        pending_rows = [row for row in rows if as_decimal(row.get("pending_amount")) > 0][:80]
        supplier_summary = {}
        for row in rows:
            partner = row.get("partner") or "-"
            bucket = supplier_summary.setdefault(
                partner,
                {
                    "partner": partner,
                    "order_count": 0,
                    "total_amount": Decimal("0"),
                    "pending_amount": Decimal("0"),
                },
            )
            bucket["order_count"] += 1
            bucket["total_amount"] += as_decimal(row.get("total_amount"))
            bucket["pending_amount"] += as_decimal(row.get("pending_amount"))
        supplier_rows = sorted(supplier_summary.values(), key=lambda item: item["pending_amount"], reverse=True)[:50]
        return {
            "title": "采购报表",
            "subtitle": "采购订单、收货执行和未到金额统计。",
            "filters": filters,
            "metrics": [
                {"label": "采购单数", "value": len(rows), "hint": "当前筛选"},
                {"label": "采购金额", "value": money_metric(total), "hint": "订单金额合计"},
                {"label": "未到金额", "value": money_metric(pending), "hint": "订单金额 - 已收货金额"},
                {"label": "供应商数", "value": len({r.get("partner") for r in rows if r.get("partner")}), "hint": "涉及供应商"},
            ],
            "sections": [
                {"title": "采购未到专题", "rows": pending_rows, "columns": columns(("order_no", "采购单"), ("order_date", "日期"), ("partner", "供应商"), ("project_code", "项目号"), ("serial_no", "机号"), ("total_amount", "金额"), ("received_amount", "已收货"), ("pending_amount", "未到"), ("status", "状态"))},
                {"title": "供应商未到排行", "rows": supplier_rows, "columns": columns(("partner", "供应商"), ("order_count", "订单数"), ("total_amount", "采购金额"), ("pending_amount", "未到金额"))},
                {"title": "采购执行明细", "rows": rows, "columns": columns(("order_no", "采购单"), ("order_date", "日期"), ("partner", "供应商"), ("project_code", "项目号"), ("serial_no", "机号"), ("total_amount", "金额"), ("received_amount", "已收货"), ("pending_amount", "未到"), ("status", "状态"))},
            ],
        }
    if kind == "inventory":
        return _build_inventory_report_config(query_rows, as_decimal, money_metric, qty_metric, columns, request_args)
        where, params, filters = report_where_from_args(
            request_args,
            "COALESCE(ib.updated_at::date, CURRENT_DATE)",
            ("p.code", "p.name", "p.specification", "w.name", "l.name", "ib.lot_no", "ib.serial_no"),
            None,
            ("ib.serial_no",),
        )
        rows = query_rows(
            f"""
            SELECT p.code AS product_code, p.name AS product_name, p.specification,
                   w.name AS warehouse_name, l.name AS location_name, ib.lot_no, ib.serial_no,
                   ib.quantity, ib.locked_qty, ib.unit_cost,
                   COALESCE(ib.quantity,0) * COALESCE(ib.unit_cost,0) AS stock_amount
            FROM inventory_balances ib
            LEFT JOIN products p ON p.id=ib.product_id
            LEFT JOIN warehouses w ON w.id=ib.warehouse_id
            LEFT JOIN locations l ON l.id=ib.location_id
            {where}
            ORDER BY stock_amount DESC NULLS LAST, p.code
            LIMIT 300
            """,
            params,
        )
        qty = sum(as_decimal(r.get("quantity")) for r in rows)
        amount = sum(as_decimal(r.get("stock_amount")) for r in rows)
        stagnant_rows = query_rows(
            """
            SELECT p.code AS product_code, p.name AS product_name, p.specification,
                   w.name AS warehouse_name, l.name AS location_name, ib.lot_no, ib.serial_no,
                   ib.quantity, ib.unit_cost,
                   COALESCE(ib.quantity,0) * COALESCE(ib.unit_cost,0) AS stock_amount,
                   MAX(st.transaction_date) AS last_transaction_date
            FROM inventory_balances ib
            LEFT JOIN products p ON p.id=ib.product_id
            LEFT JOIN warehouses w ON w.id=ib.warehouse_id
            LEFT JOIN locations l ON l.id=ib.location_id
            LEFT JOIN stock_transactions st ON st.product_id=ib.product_id
            WHERE COALESCE(ib.quantity,0) > 0
            GROUP BY p.code, p.name, p.specification, w.name, l.name, ib.lot_no, ib.serial_no, ib.quantity, ib.unit_cost
            ORDER BY MAX(st.transaction_date) NULLS FIRST, stock_amount DESC
            LIMIT 80
            """
        )
        negative_rows = [row for row in rows if as_decimal(row.get("quantity")) < 0][:80]
        return {
            "title": "库存报表",
            "subtitle": "库存余额、批次/机号、库位和库存金额统计。",
            "filters": filters,
            "metrics": [
                {"label": "库存行", "value": len(rows), "hint": "余额记录"},
                {"label": "库存数量", "value": qty_metric(qty), "hint": "数量合计"},
                {"label": "库存金额", "value": money_metric(amount), "hint": "按余额成本"},
                {"label": "物料数", "value": len({r.get("product_code") for r in rows if r.get("product_code")}), "hint": "涉及物料"},
            ],
            "sections": [
                {"title": "库存呆滞专题", "rows": stagnant_rows, "columns": columns(("product_code", "物料编码"), ("product_name", "物料名称"), ("specification", "规格"), ("warehouse_name", "仓库"), ("location_name", "库位"), ("lot_no", "批号"), ("serial_no", "机号"), ("quantity", "数量"), ("stock_amount", "金额"), ("last_transaction_date", "最后流水"))},
                {"title": "负库存异常", "rows": negative_rows, "columns": columns(("product_code", "物料编码"), ("product_name", "物料名称"), ("warehouse_name", "仓库"), ("location_name", "库位"), ("lot_no", "批号"), ("serial_no", "机号"), ("quantity", "数量"), ("stock_amount", "金额"))},
                {"title": "库存余额明细", "rows": rows, "columns": columns(("product_code", "物料编码"), ("product_name", "物料名称"), ("specification", "规格"), ("warehouse_name", "仓库"), ("location_name", "库位"), ("lot_no", "批号"), ("serial_no", "机号"), ("quantity", "数量"), ("locked_qty", "锁定"), ("stock_amount", "金额"))},
            ],
        }
    if kind == "production":
        where, params, filters = report_where_from_args(
            request_args,
            "wo.wo_date",
            ("wo.wo_no", "p.code", "p.name", "wo.project_code", "wo.serial_no"),
            "wo.status",
            ("wo.project_code", "wo.serial_no"),
        )
        scope_filter = request_args.get("_data_scope_filter") if hasattr(request_args, "get") else None
        if scope_filter:
            scope_clause, scoped_params = scope_filter({"project": "wo.project_code", "serial": "wo.serial_no"}, params=params)
            if scope_clause:
                if where:
                    where += scope_clause
                else:
                    where = " WHERE 1=1" + scope_clause
                params = scoped_params
        rows = query_rows(
            f"""
            SELECT wo.wo_no, wo.wo_date, p.code AS product_code, p.name AS product_name,
                   wo.project_code, wo.serial_no, wo.quantity, wo.status,
                   wo.planned_start_date, wo.planned_end_date, wo.actual_start_date, wo.actual_end_date
            FROM work_orders wo
            LEFT JOIN products p ON p.id=wo.product_id
            {where}
            ORDER BY wo.wo_date DESC NULLS LAST, wo.id DESC
            LIMIT 300
            """,
            params,
        )
        qty = sum(as_decimal(r.get("quantity")) for r in rows)
        open_count = sum(1 for r in rows if str(r.get("status") or "") not in {"已完工", "已关闭", "已取消", "completed", "closed"})
        open_rows = [row for row in rows if str(row.get("status") or "") not in {"已完工", "已关闭", "已取消", "completed", "closed"}][:80]
        shortage_where = " WHERE GREATEST(COALESCE(mi.required_qty,0)-COALESCE(mi.issued_qty,0)+COALESCE(mi.returned_qty,0),0) > 0"
        shortage_params = ()
        if scope_filter:
            scope_clause, shortage_params = scope_filter({"project": "wo.project_code", "serial": "wo.serial_no"})
            shortage_where += scope_clause
        shortage_rows = query_rows(
            f"""
            SELECT wo.wo_no, wo.wo_date, wo.project_code, wo.serial_no,
                   p.code AS product_code, p.name AS product_name,
                   mi.required_qty, mi.issued_qty,
                   GREATEST(COALESCE(mi.required_qty,0)-COALESCE(mi.issued_qty,0)+COALESCE(mi.returned_qty,0),0) AS shortage_qty,
                   wo.status
            FROM wo_material_items mi
            JOIN work_orders wo ON wo.id=mi.wo_id
            LEFT JOIN products p ON p.id=mi.product_id
            {shortage_where}
            ORDER BY shortage_qty DESC, wo.wo_date DESC NULLS LAST
            LIMIT 80
            """,
            shortage_params,
        )
        return {
            "title": "生产报表",
            "subtitle": "生产工单、计划日期、完工状态和项目机号统计。",
            "filters": filters,
            "metrics": [
                {"label": "工单数", "value": len(rows), "hint": "当前筛选"},
                {"label": "未完工单", "value": open_count, "hint": "仍需执行"},
                {"label": "计划数量", "value": qty_metric(qty), "hint": "工单数量合计"},
                {"label": "物料数", "value": len({r.get("product_code") for r in rows if r.get("product_code")}), "hint": "涉及产品"},
            ],
            "sections": _with_section_urls([
                {"title": "生产未完专题", "rows": open_rows, "columns": columns(("wo_no", "工单"), ("wo_date", "日期"), ("product_code", "产品编码"), ("product_name", "产品名称"), ("project_code", "项目号"), ("serial_no", "机号"), ("quantity", "数量"), ("status", "状态"), ("planned_start_date", "计划开始"), ("planned_end_date", "计划结束"))},
                {"title": "生产缺料报表", "rows": shortage_rows, "columns": columns(("wo_no", "工单"), ("wo_date", "日期"), ("project_code", "项目号"), ("serial_no", "机号"), ("product_code", "物料编码"), ("product_name", "物料名称"), ("required_qty", "需求"), ("issued_qty", "已领"), ("shortage_qty", "缺料"), ("status", "状态"))},
                {"title": "生产工单明细", "rows": rows, "columns": columns(("wo_no", "工单"), ("wo_date", "日期"), ("product_code", "产品编码"), ("product_name", "产品名称"), ("project_code", "项目号"), ("serial_no", "机号"), ("quantity", "数量"), ("status", "状态"), ("planned_start_date", "计划开始"), ("planned_end_date", "计划结束"))},
            ], (
                "/production/reports/work-order-execution-summary",
                "/production/reports/shortage",
                "/production/reports/work-order-detail",
            )),
        }
    if kind == "subcontract":
        where, params, filters = report_where_from_args(
            request_args,
            "so.order_date",
            ("so.order_no", "s.name", "p.code", "p.name", "so.project_code", "so.serial_no", "so.status"),
            "so.status",
            ("so.project_code", "so.serial_no"),
        )
        scope_filter = request_args.get("_data_scope_filter") if hasattr(request_args, "get") else None
        if scope_filter:
            scope_clause, scoped_params = scope_filter({"project": "so.project_code", "serial": "so.serial_no"}, params=params)
            if scope_clause:
                if where:
                    where += scope_clause
                else:
                    where = " WHERE 1=1" + scope_clause
                params = scoped_params
        rows = query_rows(
            f"""
            SELECT so.id, so.order_no, so.order_date, s.name AS processor_name,
                   p.code AS product_code, p.name AS product_name, p.specification,
                   so.project_code, so.serial_no,
                   COALESCE(so.quantity,0) AS order_qty,
                   COALESCE(so.received_qty,0) AS received_qty,
                   COALESCE(so.shortage_qty,0) AS shortage_qty,
                   GREATEST(COALESCE(so.quantity,0)-COALESCE(so.received_qty,0)-COALESCE(so.shortage_qty,0),0) AS open_qty,
                   COALESCE(so.unit_price,0) AS unit_price,
                   COALESCE(so.total_amount,0) AS total_amount,
                   so.status,
                   so.required_date,
                   so.arrival_status
            FROM subcontract_orders so
            LEFT JOIN suppliers s ON s.id=so.supplier_id
            LEFT JOIN products p ON p.id=so.product_id
            {where}
            ORDER BY so.order_date DESC NULLS LAST, so.id DESC
            LIMIT 300
            """,
            params,
        )
        issue_rows = query_rows(
            """
            SELECT sio.issue_no, sio.date AS issue_date, s.name AS processor_name,
                   so.order_no, so.project_code, so.serial_no,
                   COALESCE(sio.total_quantity,0) AS issued_qty,
                   sio.status, sio.posted
            FROM subcontract_issue_orders sio
            LEFT JOIN subcontract_orders so ON so.id=sio.subcontract_order_id
            LEFT JOIN suppliers s ON s.id=sio.supplier_id
            ORDER BY sio.date DESC NULLS LAST, sio.id DESC
            LIMIT 150
            """
        )
        receive_rows = query_rows(
            """
            SELECT sro.receive_no, sro.date AS receive_date, s.name AS processor_name,
                   so.order_no, so.project_code, so.serial_no,
                   COALESCE(sro.total_quantity,0) AS received_qty,
                   COALESCE(sro.total_scrap,0)+COALESCE(sro.scrap_qty,0) AS scrap_qty,
                   COALESCE(sro.short_qty,0) AS short_qty,
                   COALESCE(sro.variance_amount,0) AS variance_amount,
                   sro.status, sro.posted
            FROM subcontract_receive_orders sro
            LEFT JOIN subcontract_orders so ON so.id=sro.subcontract_order_id
            LEFT JOIN suppliers s ON s.id=sro.supplier_id
            ORDER BY sro.date DESC NULLS LAST, sro.id DESC
            LIMIT 150
            """
        )
        payable_rows = query_rows(
            """
            SELECT sp.doc_no, sp.doc_date, s.name AS processor_name,
                   sp.project_code, sp.serial_no,
                   COALESCE(sp.amount,0) AS payable_amount,
                   COALESCE(sp.paid_amount,0) AS paid_amount,
                   COALESCE(sp.balance,0) AS balance,
                   sp.status
            FROM supplier_payables sp
            LEFT JOIN suppliers s ON s.id=sp.supplier_id
            WHERE COALESCE(sp.doc_type,'') ILIKE %s
               OR COALESCE(sp.source_type,'') ILIKE %s
            ORDER BY sp.doc_date DESC NULLS LAST, sp.id DESC
            LIMIT 150
            """,
            ("%subcontract%", "%subcontract%"),
        )
        wip_rows = [row for row in rows if as_decimal(row.get("open_qty")) > 0][:100]
        variance_rows = [
            row
            for row in receive_rows
            if as_decimal(row.get("scrap_qty")) > 0
            or as_decimal(row.get("short_qty")) > 0
            or as_decimal(row.get("variance_amount")) != 0
        ][:100]
        total_amount = sum(as_decimal(row.get("total_amount")) for row in rows)
        open_qty = sum(as_decimal(row.get("open_qty")) for row in rows)
        payable_balance = sum(as_decimal(row.get("balance")) for row in payable_rows)
        return {
            "title": "委外报表",
            "subtitle": "委外订单、发料、收货、短收报废、在制和应付对账的只读统计。",
            "filters": filters,
            "metrics": [
                {"label": "委外订单数", "value": len(rows), "hint": "当前筛选"},
                {"label": "委外金额", "value": money_metric(total_amount), "hint": "委外订单金额合计"},
                {"label": "未回数量", "value": qty_metric(open_qty), "hint": "订单数量 - 已收 - 短收"},
                {"label": "应付余额", "value": money_metric(payable_balance), "hint": "委外应付未付款"},
            ],
            "sections": [
                {"title": "委外订单执行明细", "rows": rows, "columns": columns(("order_no", "委外订单"), ("order_date", "日期"), ("processor_name", "加工商"), ("product_code", "物料编码"), ("product_name", "物料名称"), ("project_code", "项目号"), ("serial_no", "机号"), ("order_qty", "订单数量"), ("received_qty", "已收数量"), ("shortage_qty", "短收数量"), ("open_qty", "未回数量"), ("total_amount", "委外金额"), ("status", "状态"))},
                {"title": "委外在制分析", "rows": wip_rows, "columns": columns(("order_no", "委外订单"), ("processor_name", "加工商"), ("product_code", "物料编码"), ("product_name", "物料名称"), ("project_code", "项目号"), ("serial_no", "机号"), ("order_qty", "订单数量"), ("received_qty", "已收数量"), ("shortage_qty", "短收数量"), ("open_qty", "未回数量"), ("required_date", "需求日期"), ("arrival_status", "到货状态"))},
                {"title": "委外发料明细", "rows": issue_rows, "columns": columns(("issue_no", "发料单"), ("issue_date", "日期"), ("processor_name", "加工商"), ("order_no", "委外订单"), ("project_code", "项目号"), ("serial_no", "机号"), ("issued_qty", "发料数量"), ("status", "状态"), ("posted", "库存过账"))},
                {"title": "委外收货明细", "rows": receive_rows, "columns": columns(("receive_no", "收货单"), ("receive_date", "日期"), ("processor_name", "加工商"), ("order_no", "委外订单"), ("project_code", "项目号"), ("serial_no", "机号"), ("received_qty", "收货数量"), ("scrap_qty", "报废数量"), ("short_qty", "短收数量"), ("variance_amount", "差异金额"), ("status", "状态"), ("posted", "库存过账"))},
                {"title": "委外短收报废差异", "rows": variance_rows, "columns": columns(("receive_no", "收货单"), ("receive_date", "日期"), ("processor_name", "加工商"), ("order_no", "委外订单"), ("project_code", "项目号"), ("serial_no", "机号"), ("scrap_qty", "报废数量"), ("short_qty", "短收数量"), ("variance_amount", "差异金额"), ("status", "状态"))},
                {"title": "委外应付对账明细", "rows": payable_rows, "columns": columns(("doc_no", "来源单据"), ("doc_date", "日期"), ("processor_name", "加工商"), ("project_code", "项目号"), ("serial_no", "机号"), ("payable_amount", "应付金额"), ("paid_amount", "已付金额"), ("balance", "未付余额"), ("status", "状态"))},
            ],
        }
    if kind == "finance":
        filters = report_filters(request_args)
        scope_filter = request_args.get("_data_scope_filter") if hasattr(request_args, "get") else None
        receivable_scope_clause = ""
        receivable_scope_params = ()
        if scope_filter:
            receivable_scope_clause, receivable_scope_params = scope_filter({"project": "project_code", "serial": "serial_no"})
        receivables = query_rows(
            f"""
            SELECT source_no AS doc_no, receivable_date AS doc_date, '应收' AS kind,
                   total_amount, received_amount AS settled_amount, balance, status, project_code, serial_no
            FROM customer_receivables
            WHERE 1=1{receivable_scope_clause}
            ORDER BY receivable_date DESC NULLS LAST, id DESC
            LIMIT 150
            """,
            receivable_scope_params,
        )
        payable_scope_clause = ""
        payable_scope_params = ()
        if scope_filter:
            payable_scope_clause, payable_scope_params = scope_filter({"project": "project_code", "serial": "serial_no"})
        payables = query_rows(
            f"""
            SELECT doc_no, doc_date, '应付' AS kind,
                   amount AS total_amount, paid_amount AS settled_amount, balance, status, NULL AS project_code, NULL AS serial_no
            FROM supplier_payables
            WHERE 1=1{payable_scope_clause}
            ORDER BY doc_date DESC NULLS LAST, id DESC
            LIMIT 150
            """,
            payable_scope_params,
        )
        rows = receivables + payables
        for row in rows:
            is_receivable = row.get("kind") in {"应收", "应付"}
            row["detail_url"] = f"{'/receivables' if is_receivable else '/payables'}?keyword={row.get('doc_no') or ''}"
            settled = as_decimal(row.get("settled_amount"))
            balance_value = as_decimal(row.get("balance"))
            if balance_value <= 0:
                row["settlement_status"] = "已核销"
            elif settled > 0:
                row["settlement_status"] = "部分核销"
            else:
                row["settlement_status"] = "未核销"
        total = sum(as_decimal(r.get("total_amount")) for r in rows)
        balance = sum(as_decimal(r.get("balance")) for r in rows)
        aging_rows = query_rows(
            """
            SELECT '应收' AS kind, source_no AS doc_no, receivable_date AS doc_date,
                   COALESCE(due_date, receivable_date) AS due_date,
                   total_amount, received_amount AS settled_amount, balance, status, project_code, serial_no,
                   CURRENT_DATE - COALESCE(due_date, receivable_date, CURRENT_DATE) AS age_days
            FROM customer_receivables
            WHERE COALESCE(balance,0) <> 0
            UNION ALL
            SELECT '应付' AS kind, doc_no, doc_date,
                   COALESCE(next_follow_up_date, doc_date) AS due_date,
                   amount AS total_amount, paid_amount AS settled_amount, balance, status, NULL AS project_code, NULL AS serial_no,
                   CURRENT_DATE - COALESCE(next_follow_up_date, doc_date, CURRENT_DATE) AS age_days
            FROM supplier_payables
            WHERE COALESCE(balance,0) <> 0
            ORDER BY age_days DESC, balance DESC
            LIMIT 120
            """
        )
        for row in aging_rows:
            is_receivable = row.get("kind") in {"应收", "应付"}
            row["detail_url"] = f"{'/receivables' if is_receivable else '/payables'}?keyword={row.get('doc_no') or ''}"
            settled = as_decimal(row.get("settled_amount"))
            balance_value = as_decimal(row.get("balance"))
            if balance_value <= 0:
                row["settlement_status"] = "已核销"
            elif settled > 0:
                row["settlement_status"] = "部分核销"
            else:
                row["settlement_status"] = "未核销"
            age_days = as_decimal(row.get("age_days"))
            if age_days < 0:
                row["aging_bucket"] = "未到期"
            elif age_days <= 30:
                row["aging_bucket"] = "0-30天"
            elif age_days <= 60:
                row["aging_bucket"] = "31-60天"
            elif age_days <= 90:
                row["aging_bucket"] = "61-90天"
            else:
                row["aging_bucket"] = "90天以上"
        aging_buckets = [
            {
                "bucket": bucket,
                "receivable_amount": sum(as_decimal(r.get("balance")) for r in aging_rows if r.get("aging_bucket") == bucket and r.get("kind") == "应收"),
                "payable_amount": sum(as_decimal(r.get("balance")) for r in aging_rows if r.get("aging_bucket") == bucket and r.get("kind") == "应付"),
                "amount": sum(as_decimal(r.get("balance")) for r in aging_rows if r.get("aging_bucket") == bucket),
                "count": sum(1 for r in aging_rows if r.get("aging_bucket") == bucket),
            }
            for bucket in ("未到期", "0-30天", "31-60天", "61-90天", "90天以上")
        ]
        return {
            "title": "财务报表",
            "subtitle": "应收、应付、收付款、账龄和往来余额的一期经营口径统计；不包含完整总账、税务、工资或固定资产。",
            "filters": filters,
            "metrics": [
                {"label": "单据数", "value": len(rows), "hint": "应收+应付"},
                {"label": "发生金额", "value": money_metric(total), "hint": "业务金额合计"},
                {"label": "余额", "value": money_metric(balance), "hint": "未结算余额"},
                {"label": "应收余额", "value": money_metric(sum_value("customer_receivables", "balance")), "hint": "客户未回款"},
            ],
            "sections": [
                {"title": "应收应付账龄专题", "rows": aging_rows, "columns": _with_url_key(columns(("kind", "类型"), ("doc_no", "来源单"), ("doc_date", "单据日期"), ("due_date", "到期/跟进日"), ("age_days", "逾期天数"), ("aging_bucket", "账龄分层"), ("total_amount", "金额"), ("settled_amount", "已核销"), ("balance", "余额"), ("settlement_status", "核销状态"), ("status", "业务状态"), ("project_code", "项目号"), ("serial_no", "机号")), "doc_no", "detail_url")},
                {"title": "账龄区间汇总", "rows": aging_buckets, "columns": columns(("bucket", "账龄区间"), ("count", "单据数"), ("receivable_amount", "应收余额"), ("payable_amount", "应付余额"), ("amount", "余额合计"))},
                {"title": "往来余额明细", "rows": rows, "columns": _with_url_key(columns(("kind", "类型"), ("doc_no", "来源单"), ("doc_date", "日期"), ("total_amount", "金额"), ("settled_amount", "已核销"), ("balance", "余额"), ("settlement_status", "核销状态"), ("status", "业务状态"), ("project_code", "项目号"), ("serial_no", "机号")), "doc_no", "detail_url")},
            ],
        }
    if kind == "service":
        where, params, filters = report_where_from_args(
            request_args,
            "mso.service_date",
            ("mso.order_no", "mso.service_type", "mso.project_code", "mso.serial_no", "mso.issue_summary"),
            "mso.status",
            ("mso.project_code", "mso.serial_no"),
        )
        scope_filter = request_args.get("_data_scope_filter") if hasattr(request_args, "get") else None
        if scope_filter:
            scope_clause, scoped_params = scope_filter({"project": "mso.project_code", "serial": "mso.serial_no"}, params=params)
            if scope_clause:
                if where:
                    where += scope_clause
                else:
                    where = " WHERE 1=1" + scope_clause
                params = scoped_params
        rows = query_rows(
            f"""
            SELECT mso.order_no, mso.service_date, mso.service_type, mso.project_code, mso.serial_no,
                   mso.status, mso.parts_cost, mso.labor_cost, mso.travel_cost, mso.total_cost,
                   mso.billable_amount, mso.settlement_status
            FROM machine_service_orders mso
            {where}
            ORDER BY mso.service_date DESC NULLS LAST, mso.id DESC
            LIMIT 300
            """,
            params,
        )
        cost = sum(as_decimal(r.get("total_cost")) for r in rows)
        billable = sum(as_decimal(r.get("billable_amount")) for r in rows)
        cost_rows = sorted(
            rows,
            key=lambda row: as_decimal(row.get("total_cost")),
            reverse=True,
        )[:80]
        rma_rows = query_rows(
            """
            SELECT rma_no, rma_date, project_code, serial_no, warranty_scope, responsibility_type,
                   internal_claim_amount, supplier_claim_amount, supplier_recovered_amount,
                   claim_status, status
            FROM machine_service_rmas
            ORDER BY rma_date DESC NULLS LAST, id DESC
            LIMIT 120
            """
        )
        return {
            "title": "售后报表",
            "subtitle": "服务单、维修成本、可收费金额和结算状态统计。",
            "filters": filters,
            "metrics": [
                {"label": "服务单数", "value": len(rows), "hint": "当前筛选"},
                {"label": "服务成本", "value": money_metric(cost), "hint": "人工+差旅+备件"},
                {"label": "可收费", "value": money_metric(billable), "hint": "应向客户收费"},
                {"label": "未结算", "value": sum(1 for r in rows if str(r.get("settlement_status") or "") not in {"已结算", "settled"}), "hint": "结算状态"},
            ],
            "sections": [
                {"title": "售后成本专题", "rows": cost_rows, "columns": columns(("order_no", "服务单"), ("service_date", "日期"), ("service_type", "类型"), ("project_code", "项目号"), ("serial_no", "机号"), ("parts_cost", "备件"), ("labor_cost", "人工"), ("travel_cost", "差旅"), ("total_cost", "成本"), ("billable_amount", "可收费"), ("settlement_status", "结算"))},
                {"title": "RMA索赔专题", "rows": rma_rows, "columns": columns(("rma_no", "RMA"), ("rma_date", "日期"), ("project_code", "项目号"), ("serial_no", "机号"), ("warranty_scope", "质保"), ("responsibility_type", "责任"), ("internal_claim_amount", "内部金额"), ("supplier_claim_amount", "供应商索赔"), ("supplier_recovered_amount", "已追回"), ("claim_status", "索赔"), ("status", "状态"))},
                {"title": "售后服务明细", "rows": rows, "columns": columns(("order_no", "服务单"), ("service_date", "日期"), ("service_type", "类型"), ("project_code", "项目号"), ("serial_no", "机号"), ("status", "状态"), ("parts_cost", "备件"), ("labor_cost", "人工"), ("travel_cost", "差旅"), ("total_cost", "成本"), ("billable_amount", "可收费"), ("settlement_status", "结算"))},
            ],
        }
    return None
