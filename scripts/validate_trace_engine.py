"""Run trace integrity scan and backfill via Flask test client to validate B-2 engine.

This script:
1. Logs in as admin
2. Runs trace integrity scan to discover gaps
3. Reports findings
4. Runs backfill to auto-repair missing links and fields
5. Re-runs scan to verify remaining gaps
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
os.environ.setdefault("PG_PASSWORD", "admin")
os.environ.setdefault("INVENTORY_SECRET_KEY", "trace-validation-session")
os.environ.setdefault("WTF_CSRF_ENABLED", "0")

from app import create_app
from scripts.trial_audit_auth import prepare_trial_audit_passwords

app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
passwords = prepare_trial_audit_passwords()

client = app.test_client()
login = client.post("/login", data={"username": "pilot_admin", "password": passwords.get("pilot_admin")}, follow_redirects=False)
print(f"Login: {login.status_code} (expected 302)")
if login.status_code != 302:
    print("Login failed, aborting.")
    sys.exit(1)

print("\n=== Step 1: Run trace integrity scan ===")
resp = client.post("/trace/integrity/scan", follow_redirects=False)
print(f"Scan response: {resp.status_code} (expected 302 redirect to /trace/integrity)")

print("\n=== Step 2: Check findings after scan ===")
import psycopg2
from psycopg2.extras import RealDictCursor
conn = psycopg2.connect(host="localhost", port=5432, database="wms", user="postgres", password="admin")
cur = conn.cursor(cursor_factory=RealDictCursor)

cur.execute("SELECT COUNT(*) as cnt FROM trace_integrity_findings")
total = cur.fetchone()['cnt']
print(f"Total findings: {total}")

if total > 0:
    print("\nFindings by type:")
    cur.execute("""
        SELECT finding_type, status, COUNT(*) as cnt
        FROM trace_integrity_findings
        GROUP BY finding_type, status
        ORDER BY finding_type, status
    """)
    for row in cur.fetchall():
        print(f"  type={row['finding_type']:40s} status={row['status']:10s} count={row['cnt']}")

    print("\nSample findings (first 10):")
    cur.execute("""
        SELECT id, finding_type, severity, doc_type, doc_id,
               description, status
        FROM trace_integrity_findings
        ORDER BY id LIMIT 10
    """)
    for row in cur.fetchall():
        print(f"  #{row['id']} [{row['finding_type']}] severity={row['severity']} "
              f"doc={row['doc_type']}:{row['doc_id']} status={row['status']}")
        print(f"       desc: {row['description'][:100] if row['description'] else '(none)'}")

print("\n=== Step 3: Run trace backfill (auto-repair) ===")
resp = client.post("/trace/integrity/backfill", follow_redirects=False)
print(f"Backfill response: {resp.status_code}")

print("\n=== Step 4: Re-run scan to verify remaining gaps ===")
resp = client.post("/trace/integrity/scan", follow_redirects=False)
print(f"Re-scan response: {resp.status_code}")

cur.execute("SELECT COUNT(*) as cnt FROM trace_integrity_findings")
after_total = cur.fetchone()['cnt']
print(f"Findings after backfill+rescan: {after_total}")

if after_total > 0:
    print("\nRemaining findings by type:")
    cur.execute("""
        SELECT finding_type, COUNT(*) as cnt
        FROM trace_integrity_findings
        GROUP BY finding_type
        ORDER BY cnt DESC
    """)
    for row in cur.fetchall():
        print(f"  {row['finding_type']}: {row['cnt']}")

print("\n=== Step 5: Trace completeness score ===")
cur.execute("SELECT COUNT(*) as cnt FROM trace_links")
links = cur.fetchone()['cnt']
print(f"Total trace_links: {links}")

cur.close()
conn.close()
print("\nDone.")
