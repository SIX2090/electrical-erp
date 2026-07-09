"""Inspect purchase_requisitions schema."""
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(host="localhost", port=5432, database="wms", user="postgres", password="admin")
cur = conn.cursor(cursor_factory=RealDictCursor)

for tbl in ("purchase_requisitions", "purchase_requisition_items"):
    cur.execute(
        """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = %s
        ORDER BY ordinal_position
        """,
        (tbl,),
    )
    print(f"=== {tbl} ===")
    for row in cur.fetchall():
        print(f"  {row['column_name']:30s} {row['data_type']:20s} nullable={row['is_nullable']}")

cur.close()
conn.close()
