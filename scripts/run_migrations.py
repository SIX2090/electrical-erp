"""Run schema migrations to add urgency/applicant columns."""
import os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PG_PASSWORD", "admin")

import psycopg2
from services.schema_migrations import MIGRATIONS, ensure_schema_migrations, apply_schema_migrations

conn = psycopg2.connect(host="localhost", port=5432, database="wms", user="postgres", password="admin")
conn.autocommit = True
cur = conn.cursor()
ensure_schema_migrations(cur)
applied = apply_schema_migrations(cur, MIGRATIONS)
print(f"Applied {applied} migrations.")
cur.close()
conn.close()
