from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    os.environ.setdefault("PG_PASSWORD", "admin")

    import psycopg2
    from psycopg2.extras import RealDictCursor

    from app import create_app
    from services.env_config import get_pg_password

    conn = psycopg2.connect(
        host=os.environ.get("PG_HOST", "127.0.0.1"),
        port=int(os.environ.get("PG_PORT", "5432")),
        dbname=os.environ.get("PG_DATABASE", "wms"),
        user=os.environ.get("PG_USER", "wms_user"),
        password=get_pg_password(),
        cursor_factory=RealDictCursor,
    )
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT pr.id, pr.req_no
            FROM purchase_requisitions pr
            JOIN purchase_requisition_items pri ON pri.req_id=pr.id
            WHERE COALESCE(pr.status, '') IN ('已审核', 'approved')
              AND COALESCE(pri.quantity, 0) > 0
              AND COALESCE(pri.suggested_supplier_id, 0) <= 0
            ORDER BY pr.id DESC
            LIMIT 1
            """
        )
        target = cur.fetchone()
    conn.close()

    if not target:
        print("detail_blocker_audit=skipped no approved purchase request with missing supplier")
        return 0

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = 1
            session["username"] = "audit"
        response = client.get(f"/purchase_request/{target['id']}")
        text = response.get_data(as_text=True)

    checks = {
        "status_200": response.status_code == 200,
        "shows_blocker": "当前采购申请不能生成采购订单" in text,
        "button_disabled": "disabled title=\"存在未指定建议供应商的未下推明细" in text,
        "line_warning": "未指定，阻塞下推" in text,
    }
    print(f"req_no={target['req_no']}")
    for name, ok in checks.items():
        print(f"{name}={'ok' if ok else 'fail'}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
