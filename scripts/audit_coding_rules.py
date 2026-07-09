from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from services.env_config import get_pg_password


def connect():
    return psycopg2.connect(
        host=os.environ.get("PG_HOST", "127.0.0.1"),
        port=int(os.environ.get("PG_PORT", "5432")),
        dbname=os.environ.get("PG_DATABASE", "wms"),
        user=os.environ.get("PG_USER", "wms_user"),
        password=get_pg_password(),
        cursor_factory=RealDictCursor,
    )


def table_exists(cur, table):
    cur.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema='public' AND table_name=%s
        LIMIT 1
        """,
        (table,),
    )
    return bool(cur.fetchone())


def count_rows(cur, sql, params=()):
    if params:
        cur.execute(sql, params)
    else:
        cur.execute(sql)
    row = cur.fetchone() or {}
    return int(row.get("value") or 0)


def main() -> int:
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")
    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    findings = []
    with app.app_context():
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 1
            session["username"] = "audit"
            session["role"] = "admin"
        session_check = client.get("/material/new", follow_redirects=False)
        if session_check.status_code != 200:
            findings.append(f"admin session failed: {session_check.status_code}")
        else:
            settings_page = client.get("/system_settings/form", follow_redirects=False)
            settings_text = settings_page.get_data().decode("utf-8", errors="ignore")
            if settings_page.status_code != 200:
                findings.append(f"system settings page failed: {settings_page.status_code}")
            required_markers = [
                "code_rule_count",
                "material:products.code",
                "document:PR",
                "document:PO",
                "document:SO",
                "document:WO",
                "document:TR",
                "下一号预览",
                "按分类",
            ]
            missing_markers = [marker for marker in required_markers if marker not in settings_text]
            if missing_markers:
                findings.append("coding rule maintenance controls missing from system settings page")
            save_response = client.post(
                "/system_settings/form/save",
                data={
                    "code_rule_count": "1",
                    "code_rule_key_0": "material:products.code",
                    "code_rule_target_type_0": "material",
                    "code_rule_prefix_0": "MAT",
                    "code_rule_date_format_0": "NONE",
                    "code_rule_sequence_length_0": "4",
                    "code_rule_separator_0": "",
                    "code_rule_reset_scope_0": "continuous",
                    "code_rule_manual_allowed_0": "1",
                    "code_rule_is_active_0": "1",
                    "code_rule_remark_0": "audit save",
                },
                follow_redirects=False,
            )
            if save_response.status_code != 200:
                findings.append(f"coding rule save failed: {save_response.status_code}")
            before = None
            with connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id
                    FROM product_categories
                    WHERE code=%s
                    ORDER BY id
                    LIMIT 1
                    """,
                    ("AUD",),
                )
                category = cur.fetchone()
                if category:
                    category_id = category["id"]
                else:
                    cur.execute(
                        """
                        INSERT INTO product_categories (code, name, remark)
                        VALUES (%s, %s, %s)
                        RETURNING id
                        """,
                        ("AUD", "Audit category", "audit coding rule category"),
                    )
                    category_id = category["id"] if category else cur.fetchone()["id"]
                conn.commit()
                before = count_rows(cur, "SELECT COUNT(*) AS value FROM products WHERE code LIKE 'AUD%'")
            marker = "coding rule audit category material"
            response = client.post(
                "/material/new",
                data={
                    "code": "",
                    "name": marker,
                    "specification": "audit",
                    "unit": "PCS",
                    "item_type": "audit",
                    "category_id": str(category_id),
                    "category": "",
                    "status": "enabled",
                },
                follow_redirects=False,
            )
            if response.status_code not in {302, 303}:
                findings.append(f"blank-code material creation did not redirect: {response.status_code}")
            with connect() as conn, conn.cursor() as cur:
                if not table_exists(cur, "erp_code_rules"):
                    findings.append("erp_code_rules table missing")
                else:
                    cur.execute("SELECT * FROM erp_code_rules WHERE rule_key=%s", ("material:products.code",))
                    rule = cur.fetchone()
                    if not rule:
                        findings.append("default material rule missing")
                    elif rule.get("prefix") != "MAT":
                        findings.append(f"default material prefix unexpected: {rule.get('prefix')}")
                    elif rule.get("date_format") != "NONE":
                        findings.append(f"default material date format should be NONE: {rule.get('date_format')}")
                cur.execute(
                    """
                    SELECT code, category_id
                    FROM products
                    WHERE name=%s
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (marker,),
                )
                material = cur.fetchone()
                if not material:
                    findings.append("blank-code material was not created")
                else:
                    material_code = str(material.get("code") or "")
                    today_text = datetime.now().strftime("%Y%m%d")
                    if not material_code.startswith("AUD"):
                        findings.append(f"generated material code does not use category prefix: {material_code}")
                    if today_text in material_code:
                        findings.append(f"generated material code still contains date: {material_code}")
                    if material.get("category_id") != category_id:
                        findings.append("generated material did not persist category_id")
                required_rules = {
                    "document:PR",
                    "document:PO",
                    "document:SO",
                    "document:WO",
                    "document:TR",
                    "document:IC",
                    "document:IA",
                    "document:OS",
                    "document:OSI",
                    "document:OSR",
                    "document:SS",
                    "document:SVO",
                    "document:RMA",
                }
                cur.execute("SELECT rule_key FROM erp_code_rules WHERE rule_key = ANY(%s)", (list(required_rules),))
                existing_rules = {row["rule_key"] for row in cur.fetchall()}
                missing_rules = sorted(required_rules - existing_rules)
                if missing_rules:
                    findings.append(f"missing document coding rules: {', '.join(missing_rules)}")
                after = count_rows(cur, "SELECT COUNT(*) AS value FROM products WHERE code LIKE 'AUD%'")
                if before is not None and after < before + 1:
                    findings.append("AUD material count did not increase")
    print("coding_rules_audit=ok" if not findings else "coding_rules_audit=failed")
    print(f"findings={len(findings)}")
    for finding in findings:
        print(f"finding | {finding}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
