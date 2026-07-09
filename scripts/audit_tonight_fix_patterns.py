from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


OUT_PATH = ROOT / "logs" / "tonight_fix_patterns_audit.json"


def scan_text_patterns() -> list[dict]:
    findings = []
    patterns = [
        ("fake_same_header_placeholder", re.compile(r"(同表头|当前版本保存首行|后续可扩展|工单/工艺行)")),
    ]
    for base in ("templates", "static", "routes"):
        for path in (ROOT / base).rglob("*"):
            if path.suffix.lower() not in {".html", ".js", ".py"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for name, pattern in patterns:
                for match in pattern.finditer(text):
                    findings.append(
                        {
                            "type": name,
                            "path": str(path.relative_to(ROOT)),
                            "line": text.count("\n", 0, match.start()) + 1,
                            "text": match.group(0),
                        }
                    )
    return findings


def check_database_patterns() -> dict:
    import psycopg2
    from psycopg2.extras import RealDictCursor

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
            SELECT pg_get_constraintdef(oid) AS definition
            FROM pg_constraint
            WHERE conrelid='subcontract_orders'::regclass
              AND conname='subcontract_orders_status_check'
            """
        )
        constraint = cur.fetchone() or {}
        cur.execute(
            """
            SELECT pr.id, pr.req_no,
                   COUNT(*) FILTER (WHERE COALESCE(pri.quantity,0) > 0 AND COALESCE(pri.suggested_supplier_id,0) <= 0) AS missing_supplier_lines
            FROM purchase_requisitions pr
            JOIN purchase_requisition_items pri ON pri.req_id=pr.id
            WHERE COALESCE(pr.status, '') IN ('已审核', 'approved')
            GROUP BY pr.id, pr.req_no
            HAVING COUNT(*) FILTER (WHERE COALESCE(pri.quantity,0) > 0 AND COALESCE(pri.suggested_supplier_id,0) <= 0) > 0
            ORDER BY pr.id DESC
            LIMIT 20
            """
        )
        blocked_purchase_requests = [dict(row) for row in cur.fetchall()]
    conn.close()
    return {
        "subcontract_status_constraint": constraint.get("definition") or "",
        "blocked_purchase_requests_missing_supplier": blocked_purchase_requests,
    }


def check_runtime_pages() -> dict:
    os.environ.setdefault("PG_PASSWORD", "admin")
    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    result = {}
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = 1
            session["username"] = "audit"
            session["role"] = "admin"
        for path in (
            "/subcontract/new",
            "/purchase_request/591",
            "/inventory_checks/new",
            "/transfers/new",
            "/adjustments/new",
        ):
            response = client.get(path)
            text = response.get_data(as_text=True)
            result[path] = {
                "status_code": response.status_code,
                "has_fake_same_header_placeholder": "同表头" in text,
                "has_subcontract_product_search": "js-product-search" in text if path == "/subcontract/new" else None,
                "has_purchase_blocker": "当前采购申请不能生成采购订单" in text if path.startswith("/purchase_request/") else None,
            }
    return result


def main() -> int:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "text_findings": scan_text_patterns(),
        "database": check_database_patterns(),
        "runtime_pages": check_runtime_pages(),
    }
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    blocking_text = [row for row in result["text_findings"] if row["type"] == "fake_same_header_placeholder"]
    runtime_failures = [
        path
        for path, row in result["runtime_pages"].items()
        if row["status_code"] != 200 or row["has_fake_same_header_placeholder"] is True
    ]
    print(f"audit_output={OUT_PATH}")
    print(f"text_findings={len(result['text_findings'])}")
    print(f"blocking_text_findings={len(blocking_text)}")
    print(f"runtime_failures={len(runtime_failures)}")
    print(f"blocked_purchase_requests_missing_supplier={len(result['database']['blocked_purchase_requests_missing_supplier'])}")
    for row in blocking_text[:20]:
        print(f"{row['path']}:{row['line']} {row['type']} {row['text']}")
    for path in runtime_failures:
        print(f"runtime_failure={path} {result['runtime_pages'][path]}")
    return 1 if blocking_text or runtime_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
