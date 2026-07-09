"""E-4: Data Archiving Service.

Provides a framework for archiving closed historical documents to reduce
the size of active transactional tables. The archiving strategy is:

1. Identify closed/cancelled documents older than a cutoff date
2. Count records eligible for archiving (preview, no mutation)
3. Record the archive batch in document_archive_records
4. The actual data movement (INSERT into archive schema + DELETE from active)
   is intentionally NOT automated by default - it must be triggered explicitly
   by an admin after reviewing the preview, because data movement is destructive.

This service focuses on safe, auditable archiving:
- Always records what was archived (batch_no, table, date range, count)
- Never deletes data without a prior backup
- Preview mode returns counts without mutating any data

Supported source tables (configurable):
- sales_orders (closed/cancelled)
- purchase_orders (closed/cancelled)
- sales_shipments (closed/cancelled)
- purchase_receipts (closed/cancelled)
- work_orders (completed/closed/cancelled)
- inventory_transactions (older than cutoff, all statuses)
"""

from datetime import date, timedelta
import logging

logger = logging.getLogger(__name__)


def _rollback_query_connection(query_fn):
    get_db = getattr(query_fn, "__self_get_db__", None)
    if not get_db:
        return
    try:
        conn = get_db()
        if conn and not conn.closed:
            conn.rollback()
    except Exception:
        logger.debug("failed to rollback archive query connection", exc_info=True)


def _table_exists(query_fn, table_name):
    _rollback_query_connection(query_fn)
    try:
        row = query_fn("SELECT to_regclass(%s) AS table_ref", (table_name,), one=True) or {}
        return bool(row.get("table_ref"))
    except Exception:
        _rollback_query_connection(query_fn)
        logger.warning("archive table existence check failed", exc_info=True)
        return False


ARCHIVE_TABLE_SPECS = {
    "sales_orders": {
        "label": "销售订单",
        "date_column": "order_date",
        "closed_statuses": ["已关闭", "closed", "已取消", "cancelled"],
    },
    "purchase_orders": {
        "label": "采购订单",
        "date_column": "order_date",
        "closed_statuses": ["已关闭", "closed", "已取消", "cancelled", "已完成", "completed"],
    },
    "sales_shipments": {
        "label": "销售发货",
        "date_column": "shipment_date",
        "closed_statuses": ["已关闭", "closed", "已取消", "cancelled"],
    },
    "purchase_receipts": {
        "label": "采购入库",
        "date_column": "receipt_date",
        "closed_statuses": ["已关闭", "closed", "已取消", "cancelled"],
    },
    "work_orders": {
        "label": "工单",
        "date_column": "planned_end_date",
        "closed_statuses": ["已完成", "completed", "已关闭", "closed", "已取消", "cancelled"],
    },
    "inventory_transactions": {
        "label": "库存流水",
        "date_column": "transaction_date",
        "closed_statuses": [],  # all statuses, purely date-based
    },
}


def preview_archive(query_fn, source_table, date_to):
    """Preview how many records are eligible for archiving.

    Returns a dict with table, label, date_to, eligible_count, and status_filter.
    Does NOT mutate any data.
    """
    spec = ARCHIVE_TABLE_SPECS.get(source_table)
    if not spec:
        return {"error": f"Unsupported source table: {source_table}"}

    date_col = spec["date_column"]
    statuses = spec["closed_statuses"]

    if statuses:
        placeholders = ", ".join(["%s"] * len(statuses))
        sql = f"""
            SELECT COUNT(*) AS cnt
            FROM {source_table}
            WHERE {date_col} IS NOT NULL
              AND {date_col} <= %s
              AND COALESCE(status, '') IN ({placeholders})
        """
        params = [date_to] + statuses
    else:
        sql = f"""
            SELECT COUNT(*) AS cnt
            FROM {source_table}
            WHERE {date_col} IS NOT NULL
              AND {date_col} <= %s
        """
        params = [date_to]

    try:
        row = query_fn(sql, tuple(params), one=True) or {}
    except Exception as exc:
        _rollback_query_connection(query_fn)
        return {"error": str(exc)}

    return {
        "table": source_table,
        "label": spec["label"],
        "date_column": date_col,
        "date_to": date_to,
        "eligible_count": int(row.get("cnt") or 0),
        "status_filter": statuses or "all",
    }


def list_archive_batches(query_fn, limit=50):
    """List recent archive batches."""
    if not _table_exists(query_fn, "document_archive_records"):
        return []
    try:
        rows = query_fn(
            """
            SELECT id, archive_batch_no, archive_date, source_table,
                   date_from, date_to, record_count, status, archived_by,
                   remark, created_at
            FROM document_archive_records
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        ) or []
        return [dict(r) for r in rows]
    except Exception:
        _rollback_query_connection(query_fn)
        logger.warning("list_archive_records failed", exc_info=True)
        return []


def record_archive_batch(execute_fn, source_table, date_from, date_to, record_count, archived_by, remark=""):
    """Record an archive batch in document_archive_records.

    This only records metadata - it does NOT move or delete data.
    The actual data movement must be done by a separate DBA operation
    after a verified backup.
    """
    from datetime import date as _date

    batch_no = f"ARCH-{source_table[:4].upper()}-{date_to.strftime('%Y%m%d')}"
    try:
        execute_fn(
            """
            INSERT INTO document_archive_records
                (archive_batch_no, archive_date, source_table, date_column,
                 date_from, date_to, record_count, status, archived_by, remark)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'completed', %s, %s)
            ON CONFLICT (archive_batch_no) DO UPDATE
            SET record_count = EXCLUDED.record_count,
                archived_by = EXCLUDED.archived_by,
                remark = EXCLUDED.remark,
                status = EXCLUDED.status
            """,
            (
                batch_no,
                _date.today(),
                source_table,
                ARCHIVE_TABLE_SPECS.get(source_table, {}).get("date_column", "created_at"),
                date_from,
                date_to,
                record_count,
                archived_by,
                remark,
            ),
        )
        return batch_no
    except Exception as exc:
        raise RuntimeError(f"Failed to record archive batch: {exc}")


def get_table_sizes(query_fn):
    """Get approximate row counts for large tables to inform archiving decisions."""
    tables = list(ARCHIVE_TABLE_SPECS.keys())
    results = []
    for table in tables:
        try:
            row = query_fn(f"SELECT COUNT(*) AS cnt FROM {table}", (), one=True) or {}
            results.append({
                "table": table,
                "label": ARCHIVE_TABLE_SPECS[table]["label"],
                "row_count": int(row.get("cnt") or 0),
            })
        except Exception:
            _rollback_query_connection(query_fn)
            results.append({
                "table": table,
                "label": ARCHIVE_TABLE_SPECS[table]["label"],
                "row_count": 0,
                "error": True,
            })
    return results
