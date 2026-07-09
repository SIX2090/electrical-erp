from pathlib import Path
import csv
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.app_runtime import connect_db
from services.env_config import get_pg_password


def get_db_config():
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "database": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }


def clean_status(status):
    value = (status or "").strip()
    return bool(value) and "?" not in value and chr(0xFFFD) not in value


STATUS_LABELS = {
    "草稿": "draft",
    "已提交": "submitted",
    "已审核": "audited",
    "待发货": "pending shipment",
    "已发货": "shipped",
    "已关闭": "closed",
    "已作废": "voided",
    "已完成": "completed",
}


def clean_for_report(value, fallback="-", allow_non_ascii=False):
    text = (str(value) if value is not None else "").strip()
    if not text:
        return fallback
    if "?" in text or chr(0xFFFD) in text:
        return "dirty/unknown"
    if allow_non_ascii:
        return text
    if all(ord(ch) < 128 for ch in text):
        return text
    return "non-ascii data"


def status_for_report(status):
    value = (status or "").strip()
    if not clean_status(value):
        return "dirty/unknown"
    return STATUS_LABELS.get(value, clean_for_report(value))


def main():
    output_dir = ROOT / "release" / "trial_run"
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "trial_machine_candidates.csv"
    md_path = output_dir / "trial_machine_candidates.md"
    conn = connect_db(get_db_config())
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT so.id, so.order_no, so.project_code, so.serial_no, so.status,
                       so.delivery_date, so.total_amount, c.name AS customer_name,
                       COUNT(DISTINCT soi.id) AS item_lines,
                       COUNT(DISTINCT soi.product_id) AS product_count,
                       COUNT(DISTINCT b.id) AS bom_count,
                       COUNT(DISTINCT bi.id) AS bom_item_count,
                       COUNT(DISTINCT mr.id) AS mrp_count
                FROM sales_orders so
                LEFT JOIN customers c ON c.id=so.customer_id
                LEFT JOIN sales_order_items soi ON soi.order_id=so.id
                LEFT JOIN boms b ON b.product_id=soi.product_id
                LEFT JOIN bom_items bi ON bi.bom_id=b.id
                LEFT JOIN mrp_requirements mr
                  ON (mr.source_document_type='sales_order' AND mr.source_document_id=so.id)
                  OR (NULLIF(so.project_code, '') IS NOT NULL AND mr.project_code=so.project_code)
                  OR (NULLIF(so.serial_no, '') IS NOT NULL AND mr.serial_no=so.serial_no)
                WHERE so.id IS NOT NULL
                GROUP BY so.id, so.order_no, so.project_code, so.serial_no, so.status,
                         so.delivery_date, so.total_amount, c.name
                ORDER BY so.id DESC
                LIMIT 500
                """
            )
            rows = [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()

    candidates = []
    rejected = []
    for row in rows:
        reasons = []
        if not row.get("customer_name"):
            reasons.append("missing customer")
        if not row.get("project_code"):
            reasons.append("missing project number")
        if not row.get("serial_no"):
            reasons.append("missing serial number")
        if not clean_status(row.get("status")):
            reasons.append("dirty or unknown status")
        if int(row.get("item_lines") or 0) <= 0:
            reasons.append("missing sales lines")
        if int(row.get("bom_count") or 0) <= 0 or int(row.get("bom_item_count") or 0) <= 0:
            reasons.append("missing BOM")
        row["trial_ready"] = "yes" if not reasons else "no"
        row["trial_gaps"] = "; ".join(reasons) if reasons else "candidate"
        row["customer_report"] = clean_for_report(row.get("customer_name"), allow_non_ascii=True)
        row["status_report"] = status_for_report(row.get("status"))
        if reasons:
            rejected.append(row)
        else:
            candidates.append(row)

    headers = [
        "trial_ready",
        "trial_gaps",
        "id",
        "order_no",
        "customer",
        "project_code",
        "serial_no",
        "status",
        "delivery_date",
        "total_amount",
        "item_lines",
        "product_count",
        "bom_count",
        "bom_item_count",
        "mrp_count",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers)
        writer.writeheader()
        for row in candidates[:100] + rejected[:100]:
            writer.writerow(
                {
                    **{key: row.get(key, "") for key in headers},
                    "customer": row.get("customer_report", ""),
                    "status": row.get("status_report", ""),
                }
            )

    lines = [
        "# First Machine Trial Candidate Report",
        "",
        f"- Sales orders scanned: {len(rows)}",
        f"- Ready candidates: {len(candidates)}",
        f"- Rejected or incomplete orders: {len(rejected)}",
        "",
        "## Ready Candidates",
        "",
        "| Sales order | Customer | Project | Serial | Status | Lines | BOM | BOM lines | MRP |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in candidates[:20]:
        lines.append(
            f"| `{clean_for_report(row.get('order_no'), '')}` | {row.get('customer_report') or '-'} | `{clean_for_report(row.get('project_code'), '')}` | `{clean_for_report(row.get('serial_no'), '')}` | {row.get('status_report') or '-'} | {row.get('item_lines') or 0} | {row.get('bom_count') or 0} | {row.get('bom_item_count') or 0} | {row.get('mrp_count') or 0} |"
        )
    if not candidates:
        lines.append("| - | - | - | - | - | 0 | 0 | 0 | 0 |")
    lines.extend(
        [
            "",
            "## Rejected Order Samples",
            "",
            "| Sales order | Customer | Project | Serial | Status | Gap |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in rejected[:30]:
        lines.append(
            f"| `{clean_for_report(row.get('order_no'), '')}` | {row.get('customer_report') or '-'} | `{clean_for_report(row.get('project_code'), '')}` | `{clean_for_report(row.get('serial_no'), '')}` | {row.get('status_report') or '-'} | {row.get('trial_gaps') or ''} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"trial_candidates={len(candidates)}")
    print(f"trial_rejected={len(rejected)}")
    print(f"csv={csv_path}")
    print(f"report={md_path}")


if __name__ == "__main__":
    main()
