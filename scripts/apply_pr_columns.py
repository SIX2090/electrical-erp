"""Apply the urgency/applicant columns directly."""
import psycopg2

conn = psycopg2.connect(host="localhost", port=5432, database="wms", user="postgres", password="admin")
conn.autocommit = True
cur = conn.cursor()

cur.execute("ALTER TABLE purchase_requisitions ADD COLUMN IF NOT EXISTS urgency VARCHAR(30) DEFAULT 'normal'")
cur.execute("ALTER TABLE purchase_requisitions ADD COLUMN IF NOT EXISTS applicant VARCHAR(120)")
cur.execute("UPDATE purchase_requisitions SET urgency='normal' WHERE urgency IS NULL OR urgency=''")

# Verify
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name='purchase_requisitions' AND column_name IN ('urgency','applicant')
""")
print("Columns added:", [r[0] for r in cur.fetchall()])

cur.close()
conn.close()
print("Done.")
