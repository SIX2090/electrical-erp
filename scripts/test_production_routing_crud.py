import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from routes.registry import deps


def main():
    create_app()
    query_db = deps["query_db"]
    execute_db = deps["execute_db"]
    execute_and_return = deps["execute_and_return"]

    execute_db("ALTER TABLE production_routings ADD COLUMN IF NOT EXISTS status VARCHAR(40)")
    execute_db("ALTER TABLE production_routings ADD COLUMN IF NOT EXISTS remark TEXT")
    routing_no = "RT20990101001"
    execute_db("DELETE FROM routing_operations WHERE routing_id IN (SELECT id FROM production_routings WHERE routing_no=%s)", (routing_no,))
    execute_db("DELETE FROM production_routings WHERE routing_no=%s", (routing_no,))

    product = execute_and_return(
        """
        INSERT INTO products (code, name, category, unit, status)
        VALUES ('CODEX-ROUTING-PRODUCT', 'CODEx routing test product', 'test', 'set', '启用')
        ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name, category=EXCLUDED.category, unit=EXCLUDED.unit, status=EXCLUDED.status
        RETURNING id
        """
    )
    center = execute_and_return(
        """
        INSERT INTO work_centers (code, name, is_active)
        VALUES ('CODEX-ROUTING-WC', 'CODEx routing test center', TRUE)
        ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name, is_active=TRUE
        RETURNING id
        """
    )
    product_id = product["id"]
    center_id = center["id"]

    routing = execute_and_return(
        """
        INSERT INTO production_routings (routing_no, name, product_id, revision, status, is_active, remark)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
        """,
        (routing_no, "CODEx routing create", product_id, "V1.0", "draft", False, "crud audit"),
    )
    routing_id = routing["id"]
    execute_db(
        """
        INSERT INTO routing_operations
            (routing_id, sequence, operation_no, operation_name, work_center_id, process_note, quality_note, setup_time, run_time)
        VALUES (%s,10,'OP10','Cut',%s,'process','quality',1,2),
               (%s,20,'OP20','Assemble',%s,'process','quality',1,2)
        """,
        (routing_id, center_id, routing_id, center_id),
    )
    created_ops = query_db("SELECT COUNT(*) AS value FROM routing_operations WHERE routing_id=%s", (routing_id,), one=True)
    assert int(created_ops["value"]) == 2, created_ops

    execute_db(
        """
        UPDATE production_routings
        SET name=%s, product_id=%s, revision=%s, status=%s, is_active=%s, remark=%s
        WHERE id=%s
        """,
        ("CODEx routing edit", product_id, "V2.0", "enabled", True, "edited", routing_id),
    )
    execute_db("DELETE FROM routing_operations WHERE routing_id=%s", (routing_id,))
    execute_db(
        """
        INSERT INTO routing_operations
            (routing_id, sequence, operation_no, operation_name, work_center_id, process_note, quality_note, setup_time, run_time)
        VALUES (%s,10,'OP10','Cut edited',%s,'process','quality',1,2),
               (%s,30,'OP30','Inspect',%s,'process','quality',1,2),
               (%s,20,'OP20','Assemble edited',%s,'process','quality',1,2)
        """,
        (routing_id, center_id, routing_id, center_id, routing_id, center_id),
    )
    edited = query_db("SELECT name, status, is_active FROM production_routings WHERE id=%s", (routing_id,), one=True)
    assert edited["name"] == "CODEx routing edit", edited
    assert edited["status"] == "enabled", edited
    assert edited["is_active"] is True, edited
    edited_ops = query_db("SELECT operation_no FROM routing_operations WHERE routing_id=%s ORDER BY sequence", (routing_id,))
    assert [row["operation_no"] for row in edited_ops] == ["OP10", "OP20", "OP30"], edited_ops

    execute_db("DELETE FROM routing_operations WHERE routing_id=%s", (routing_id,))
    execute_db("DELETE FROM production_routings WHERE id=%s", (routing_id,))
    deleted = query_db("SELECT COUNT(*) AS value FROM production_routings WHERE id=%s", (routing_id,), one=True)
    assert int(deleted["value"]) == 0, deleted

    print("production routing CRUD ok")


if __name__ == "__main__":
    main()
