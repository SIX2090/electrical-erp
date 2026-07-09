from __future__ import annotations

import json
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

import os


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.env_config import get_pg_password

OUT_PATH = ROOT / "logs" / "document_schema_fact_check.json"


DOCUMENT_TABLES = {
    "purchase_requisitions": {"doc_no": "req_no", "date": "req_date", "detail": "purchase_requisition_items"},
    "purchase_orders": {"doc_no": "order_no", "date": "order_date", "detail": "purchase_order_items"},
    "purchase_receipts": {"doc_no": "receipt_no", "date": "receipt_date", "detail": "purchase_receipt_items"},
    "purchase_invoices": {"doc_no": "invoice_no", "date": "invoice_date"},
    "purchase_returns": {"doc_no": "return_no", "date": "return_date"},
    "sales_orders": {"doc_no": "order_no", "date": "order_date", "detail": "sales_order_items"},
    "sales_shipments": {"doc_no": "shipment_no", "date": "shipment_date", "detail": "sales_shipment_items"},
    "sales_invoices": {"doc_no": "invoice_no", "date": "invoice_date"},
    "sales_returns": {"doc_no": "return_no", "date": "return_date"},
    "transfer_orders": {"doc_no": "transfer_no", "detail": "transfer_order_items"},
    "inventory_adjustments": {"doc_no": "adj_no"},
    "inventory_adjustment_orders": {"doc_no": "adj_no"},
    "inventory_check_orders": {"doc_no": "check_no", "detail": "inventory_check_order_items"},
    "inventory_assembly_orders": {"doc_no": "assembly_no", "date": "doc_date", "detail": "inventory_assembly_items"},
    "work_orders": {"doc_no": "wo_no"},
    "subcontract_orders": {"doc_no": "order_no", "date": "order_date"},
    "subcontract_issue_orders": {"doc_no": "issue_no", "date": "date", "detail": "subcontract_issue_lines"},
    "subcontract_receive_orders": {"doc_no": "receive_no", "date": "date", "detail": "subcontract_receive_lines"},
    "supplier_payments": {"doc_no": "payment_no", "date": "payment_date"},
    "customer_receipts": {"doc_no": "receipt_no"},
    "supplier_payables": {"doc_no": "doc_no", "date": "doc_date"},
    "customer_receivables": {"doc_no": "doc_no", "date": "doc_date"},
    "stock_transactions": {"doc_no": "reference_no", "date": "transaction_date"},
}


FOREIGN_KEY_EXPECTATIONS = {
    ("purchase_orders", "supplier_id"): ("suppliers", "id"),
    ("purchase_receipts", "supplier_id"): ("suppliers", "id"),
    ("purchase_invoices", "supplier_id"): ("suppliers", "id"),
    ("sales_orders", "customer_id"): ("customers", "id"),
    ("sales_shipments", "customer_id"): ("customers", "id"),
    ("sales_invoices", "customer_id"): ("customers", "id"),
    ("work_orders", "product_id"): ("products", "id"),
    ("transfer_orders", "from_warehouse_id"): ("warehouses", "id"),
    ("transfer_orders", "to_warehouse_id"): ("warehouses", "id"),
    ("inventory_adjustments", "warehouse_id"): ("warehouses", "id"),
    ("subcontract_orders", "supplier_id"): ("suppliers", "id"),
    ("supplier_payments", "supplier_id"): ("suppliers", "id"),
    ("customer_receipts", "customer_id"): ("customers", "id"),
    ("machine_service_cards", "customer_id"): ("customers", "id"),
    ("machine_service_cards", "product_id"): ("products", "id"),
}


def connect():
    return psycopg2.connect(
        host=os.environ.get("PG_HOST", "127.0.0.1"),
        port=int(os.environ.get("PG_PORT", "5432")),
        dbname=os.environ.get("PG_DATABASE", "wms"),
        user=os.environ.get("PG_USER", "wms_user"),
        password=get_pg_password(),
        cursor_factory=RealDictCursor,
    )


def fetchall(cur, sql, params=()):
    cur.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


def main() -> int:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn, conn.cursor() as cur:
        existing_tables = {
            row["table_name"]
            for row in fetchall(
                cur,
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema='public' AND table_type='BASE TABLE'
                """,
            )
        }
        audit_tables = sorted(set(DOCUMENT_TABLES) | {v.get("detail") for v in DOCUMENT_TABLES.values() if v.get("detail")})
        audit_tables = [table for table in audit_tables if table]
        columns = fetchall(
            cur,
            """
            SELECT table_name, column_name, data_type, udt_name,
                   character_maximum_length, numeric_precision, numeric_scale,
                   is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name = ANY(%s)
            ORDER BY table_name, ordinal_position
            """,
            (audit_tables,),
        )
        indexes = fetchall(
            cur,
            """
            SELECT schemaname, tablename, indexname, indexdef
            FROM pg_indexes
            WHERE schemaname='public' AND tablename = ANY(%s)
            ORDER BY tablename, indexname
            """,
            (audit_tables,),
        )
        fks = fetchall(
            cur,
            """
            SELECT tc.table_name, kcu.column_name,
                   ccu.table_name AS foreign_table_name,
                   ccu.column_name AS foreign_column_name,
                   tc.constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON ccu.constraint_name = tc.constraint_name
             AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type='FOREIGN KEY'
              AND tc.table_schema='public'
              AND tc.table_name = ANY(%s)
            ORDER BY tc.table_name, kcu.column_name
            """,
            (audit_tables,),
        )

    by_table: dict[str, list[dict]] = {}
    for row in columns:
        by_table.setdefault(row["table_name"], []).append(row)
    column_names = {table: {row["column_name"] for row in rows} for table, rows in by_table.items()}
    index_defs = {}
    for row in indexes:
        index_defs.setdefault(row["tablename"], []).append(row)
    fk_map = {(row["table_name"], row["column_name"]): row for row in fks}

    numeric_findings = []
    for row in columns:
        name = row["column_name"]
        if any(token in name for token in ("amount", "price", "cost", "quantity", "qty")) and row["data_type"] == "numeric":
            numeric_findings.append(row)

    status_findings = []
    for row in columns:
        if row["column_name"] == "status":
            status_findings.append(row)

    doc_no_findings = []
    for table, meta in DOCUMENT_TABLES.items():
        doc_col = meta.get("doc_no")
        if table not in existing_tables:
            doc_no_findings.append({"table": table, "exists": False, "doc_col": doc_col, "has_column": False, "has_index": False})
            continue
        has_col = doc_col in column_names.get(table, set())
        has_idx = any(doc_col and doc_col in idx["indexdef"] for idx in index_defs.get(table, []))
        doc_no_findings.append({"table": table, "exists": True, "doc_col": doc_col, "has_column": has_col, "has_index": has_idx})

    fk_findings = []
    for (table, column), (ref_table, ref_col) in FOREIGN_KEY_EXPECTATIONS.items():
        exists = table in existing_tables and column in column_names.get(table, set())
        actual = fk_map.get((table, column))
        fk_findings.append(
            {
                "table": table,
                "column": column,
                "exists": exists,
                "expected": f"{ref_table}.{ref_col}",
                "has_fk": bool(actual),
                "actual": actual,
            }
        )

    audit_field_findings = []
    for table in audit_tables:
        if table not in existing_tables:
            continue
        names = column_names.get(table, set())
        audit_field_findings.append(
            {
                "table": table,
                "has_created_at": "created_at" in names,
                "has_updated_at": "updated_at" in names,
            }
        )

    traceability_findings = []
    for table, meta in DOCUMENT_TABLES.items():
        detail = meta.get("detail")
        if not detail or table not in existing_tables or detail not in existing_tables:
            continue
        header_names = column_names.get(table, set())
        detail_names = column_names.get(detail, set())
        for field in ("project_code", "serial_no", "warehouse_id", "location_id", "lot_no", "source_line_no"):
            if field in header_names or field in detail_names:
                traceability_findings.append(
                    {
                        "header": table,
                        "detail": detail,
                        "field": field,
                        "header_has": field in header_names,
                        "detail_has": field in detail_names,
                    }
                )

    result = {
        "existing_document_tables": sorted([table for table in DOCUMENT_TABLES if table in existing_tables]),
        "missing_document_tables": sorted([table for table in DOCUMENT_TABLES if table not in existing_tables]),
        "columns": columns,
        "indexes": indexes,
        "foreign_keys": fks,
        "numeric_fields": numeric_findings,
        "status_fields": status_findings,
        "document_number_fields": doc_no_findings,
        "foreign_key_expectations": fk_findings,
        "audit_fields": audit_field_findings,
        "traceability_fields": traceability_findings,
    }
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print(f"fact_check_output={OUT_PATH}")
    print(f"document_tables_existing={len(result['existing_document_tables'])}")
    print(f"document_tables_missing={len(result['missing_document_tables'])}")
    print(f"numeric_fields={len(numeric_findings)}")
    print(f"status_fields={len(status_findings)}")
    print(f"doc_no_without_index={sum(1 for row in doc_no_findings if row['exists'] and row['has_column'] and not row['has_index'])}")
    print(f"fk_expectations_missing={sum(1 for row in fk_findings if row['exists'] and not row['has_fk'])}")
    print(f"audit_fields_missing={sum(1 for row in audit_field_findings if not row['has_created_at'] or not row['has_updated_at'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
