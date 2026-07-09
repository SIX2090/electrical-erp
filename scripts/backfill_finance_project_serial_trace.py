from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import get_db_config
from services.app_runtime import connect_db


def value(cur, sql):
    cur.execute(sql)
    row = cur.fetchone()
    return int((row or {}).get("value") or 0)


def main():
    with connect_db(get_db_config()) as conn:
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE customer_receivables ADD COLUMN IF NOT EXISTS project_code VARCHAR(120)")
            cur.execute("ALTER TABLE customer_receivables ADD COLUMN IF NOT EXISTS serial_no VARCHAR(120)")
            cur.execute("ALTER TABLE customer_receivables ADD COLUMN IF NOT EXISTS cost_object_id INTEGER")
            cur.execute("ALTER TABLE supplier_payables ADD COLUMN IF NOT EXISTS project_code VARCHAR(120)")
            cur.execute("ALTER TABLE supplier_payables ADD COLUMN IF NOT EXISTS serial_no VARCHAR(120)")
            cur.execute("ALTER TABLE supplier_payables ADD COLUMN IF NOT EXISTS cost_object_id INTEGER")

            before_ar_missing = value(
                cur,
                """
                SELECT COUNT(*) AS value
                FROM customer_receivables
                WHERE COALESCE(project_code,'')='' OR COALESCE(serial_no,'')=''
                """,
            )
            before_ap_missing = value(
                cur,
                """
                SELECT COUNT(*) AS value
                FROM supplier_payables
                WHERE COALESCE(project_code,'')='' OR COALESCE(serial_no,'')=''
                """,
            )

            cur.execute(
                """
                UPDATE customer_receivables cr
                SET project_code=COALESCE(NULLIF(cr.project_code,''), so.project_code),
                    serial_no=COALESCE(NULLIF(cr.serial_no,''), so.serial_no),
                    cost_object_id=COALESCE(cr.cost_object_id, so.cost_object_id)
                FROM sales_orders so
                WHERE cr.source_type='sales_order'
                  AND (cr.source_id=so.id OR cr.source_no=so.order_no)
                """
            )
            ar_sales_order = cur.rowcount

            cur.execute(
                """
                UPDATE customer_receivables cr
                SET project_code=COALESCE(NULLIF(cr.project_code,''), ss.project_code, so.project_code),
                    serial_no=COALESCE(NULLIF(cr.serial_no,''), ss.serial_no, so.serial_no),
                    cost_object_id=COALESCE(cr.cost_object_id, so.cost_object_id)
                FROM sales_shipments ss
                LEFT JOIN sales_orders so ON so.id=ss.order_id
                WHERE cr.source_type='sales_shipment'
                  AND (cr.source_id=ss.id OR cr.source_no=ss.shipment_no)
                """
            )
            ar_shipment = cur.rowcount

            cur.execute(
                """
                UPDATE supplier_payables sp
                SET project_code=COALESCE(NULLIF(sp.project_code,''), po.project_code),
                    serial_no=COALESCE(NULLIF(sp.serial_no,''), po.serial_no),
                    cost_object_id=COALESCE(sp.cost_object_id, po.cost_object_id)
                FROM purchase_orders po
                WHERE sp.doc_type='purchase_order'
                  AND (sp.doc_id=po.id OR sp.doc_no=po.order_no)
                """
            )
            ap_purchase_order = cur.rowcount

            cur.execute(
                """
                UPDATE supplier_payables sp
                SET project_code=COALESCE(NULLIF(sp.project_code,''), pr.project_code, po.project_code),
                    serial_no=COALESCE(NULLIF(sp.serial_no,''), pr.serial_no, po.serial_no),
                    cost_object_id=COALESCE(sp.cost_object_id, po.cost_object_id)
                FROM purchase_receipts pr
                LEFT JOIN purchase_orders po ON po.id=pr.order_id
                WHERE sp.doc_type='purchase_receipt'
                  AND (sp.doc_id=pr.id OR sp.doc_no=pr.receipt_no)
                """
            )
            ap_purchase_receipt = cur.rowcount

            cur.execute(
                """
                UPDATE supplier_payables sp
                SET project_code=COALESCE(NULLIF(sp.project_code,''), sc.project_code),
                    serial_no=COALESCE(NULLIF(sp.serial_no,''), sc.serial_no),
                    cost_object_id=COALESCE(sp.cost_object_id, sc.cost_object_id)
                FROM subcontract_orders sc
                WHERE sp.doc_type IN ('subcontract_order','subcontract_receipt')
                  AND (sp.doc_id=sc.id OR sp.doc_no=sc.order_no)
                """
            )
            ap_subcontract = cur.rowcount

            cur.execute("CREATE INDEX IF NOT EXISTS idx_customer_receivables_trace ON customer_receivables(project_code, serial_no)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_supplier_payables_trace ON supplier_payables(project_code, serial_no)")

            after_ar_missing = value(
                cur,
                """
                SELECT COUNT(*) AS value
                FROM customer_receivables
                WHERE COALESCE(project_code,'')='' OR COALESCE(serial_no,'')=''
                """,
            )
            after_ap_missing = value(
                cur,
                """
                SELECT COUNT(*) AS value
                FROM supplier_payables
                WHERE COALESCE(project_code,'')='' OR COALESCE(serial_no,'')=''
                """,
            )
        conn.commit()

    print("finance_project_serial_trace_backfill=ok")
    print(f"ar_missing_before={before_ar_missing}")
    print(f"ar_sales_order_rows={ar_sales_order}")
    print(f"ar_shipment_rows={ar_shipment}")
    print(f"ar_missing_after={after_ar_missing}")
    print(f"ap_missing_before={before_ap_missing}")
    print(f"ap_purchase_order_rows={ap_purchase_order}")
    print(f"ap_purchase_receipt_rows={ap_purchase_receipt}")
    print(f"ap_subcontract_rows={ap_subcontract}")
    print(f"ap_missing_after={after_ap_missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
