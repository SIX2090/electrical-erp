from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.app_runtime import connect_db
from services.env_config import get_pg_password


PREFIX = "QA-BASIC-AUDIT"


def get_db_config():
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "database": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }


def fetch_one(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchone()


def cleanup(cur):
    cur.execute(
        """
        DELETE FROM quality_inspection_records
        WHERE inspection_no LIKE %s OR project_code LIKE %s OR serial_no LIKE %s
        """,
        (f"{PREFIX}%", f"{PREFIX}%", f"{PREFIX}%"),
    )


def main():
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "quality-basics-audit")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")

    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    client = app.test_client()
    checks = []

    login = client.post("/login", data={"username": "admin", "password": "admin"})
    checks.append(("admin_login", login.status_code == 302, login.status_code))

    conn = connect_db(get_db_config())
    try:
        with conn.cursor() as cur:
            cleanup(cur)
            product = fetch_one(
                cur,
                """
                SELECT id, name
                FROM products
                WHERE COALESCE(name,'') <> ''
                ORDER BY id
                LIMIT 1
                """,
            )
            checks.append(("product_available", bool(product), product.get("name") if product else "missing"))
            conn.commit()
    finally:
        conn.close()

    if not product:
        failures = [(name, detail) for name, ok, detail in checks if not ok]
        for name, ok, detail in checks:
            print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
        return 1 if failures else 0

    create_response = client.post(
        "/production-enhance/quality-inspections/new",
        data={
            "inspection_no": f"{PREFIX}-001",
            "inspection_date": "2026-06-06",
            "inspection_type": "iqc",
            "source_document_type": "manual",
            "product_id": str(product["id"]),
            "product_name": product["name"],
            "project_code": f"{PREFIX}-PJ",
            "serial_no": f"{PREFIX}-SN",
            "batch_no": f"{PREFIX}-LOT",
            "inspector": "quality audit",
            "sample_size": "10",
            "passed_quantity": "8",
            "failed_quantity": "2",
            "inspection_result": "fail",
            "defect_description": "audit defect",
            "corrective_action": "audit corrective action",
            "blocked_reason": "audit blocked reason",
            "next_action": "audit next action",
            "downstream_impact": "audit downstream impact",
            "defect_category": "尺寸",
            "severity_level": "重要",
            "disposition": "rework",
            "nonconformance_status": "待处理",
            "responsible_party": "供应商",
            "owner_role": "采购/质量",
            "reinspection_required": "1",
            "capa_required": "1",
            "capa_status": "待制定",
            "capa_owner": "quality owner",
            "root_cause": "audit root cause",
            "preventive_action": "audit preventive action",
            "quality_cost_amount": "123.45",
            "cost_category": "返工",
        },
        follow_redirects=False,
    )
    checks.append(("create_quality_iqc", create_response.status_code == 302, create_response.status_code))

    conn = connect_db(get_db_config())
    try:
        with conn.cursor() as cur:
            row = fetch_one(cur, "SELECT * FROM quality_inspection_records WHERE inspection_no=%s", (f"{PREFIX}-001",))
            checks.append(("created_record_found", bool(row), row.get("id") if row else "missing"))
            if row:
                checks.append(("created_as_draft", row.get("status") in {"草稿", "draft"}, row.get("status")))
                checks.append(("iqc_type_saved", row.get("inspection_type") == "iqc", row.get("inspection_type")))
                checks.append(("ncr_fields_saved", row.get("blocked_reason") == "audit blocked reason" and row.get("disposition") == "rework", "ncr"))
                checks.append(("capa_fields_saved", bool(row.get("capa_required")) and row.get("capa_owner") == "quality owner", "capa"))
                checks.append(("quality_cost_saved", str(row.get("quality_cost_amount")) in {"123.45", "123.4500"}, row.get("quality_cost_amount")))
    finally:
        conn.close()

    if row:
        judge_response = client.post(
            f"/production-enhance/quality-inspections/{row['id']}/judge",
            data={
                "inspection_result": "fail",
                "conclusion": "audit judged fail",
                "defect_description": "audit defect",
                "corrective_action": "audit corrective action",
                "blocked_reason": "audit blocked reason",
                "next_action": "audit next action",
                "defect_category": "尺寸",
                "severity_level": "重要",
                "disposition": "rework",
                "responsible_party": "供应商",
                "owner_role": "采购/质量",
                "nonconformance_status": "处理中",
                "capa_required": "1",
                "capa_status": "待验证",
                "capa_owner": "quality owner",
                "root_cause": "audit root cause",
                "preventive_action": "audit preventive action",
                "quality_cost_amount": "123.45",
                "cost_category": "返工",
            },
            follow_redirects=False,
        )
        checks.append(("judge_failed_quality", judge_response.status_code == 302, judge_response.status_code))
        blocked_close = client.post(f"/production-enhance/quality-inspections/{row['id']}/close", data={"remark": "audit close"}, follow_redirects=True)
        checks.append(("close_blocked_by_capa", "CAPA 未关闭或未验证" in blocked_close.get_data(as_text=True), blocked_close.status_code))

        conn = connect_db(get_db_config())
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE quality_inspection_records SET capa_status='已验证', effectiveness_result='audit verified' WHERE id=%s",
                    (row["id"],),
                )
                conn.commit()
        finally:
            conn.close()
        close_response = client.post(f"/production-enhance/quality-inspections/{row['id']}/close", data={"remark": "audit close"}, follow_redirects=False)
        checks.append(("close_after_capa_verified", close_response.status_code == 302, close_response.status_code))

        detail = client.get(f"/production-enhance/quality-inspections/{row['id']}")
        body = detail.get_data(as_text=True)
        checks.append(("detail_status", detail.status_code == 200, detail.status_code))
        for marker in ("IQC来料检验", "不合格处理", "CAPA 与质量成本", "audit blocked reason", "audit next action"):
            checks.append((f"detail_marker:{marker}", marker in body, "visible"))
        listing = client.get(f"/production-enhance/quality-inspections?keyword={PREFIX}")
        list_body = listing.get_data(as_text=True)
        checks.append(("list_status", listing.status_code == 200, listing.status_code))
        for marker in ("不合格状态", "处置方式", "责任岗位", "质量成本估算"):
            checks.append((f"list_marker:{marker}", marker in list_body, "visible"))

    conn = connect_db(get_db_config())
    try:
        with conn.cursor() as cur:
            cleanup(cur)
            conn.commit()
    finally:
        conn.close()

    failures = [(name, detail) for name, ok, detail in checks if not ok]
    print("quality_basics_closure_audit=ok" if not failures else "quality_basics_closure_audit=failed")
    print(f"checked_items={len(checks)}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
