"""Validate B-4 BOM/ECN engine: versions, snapshots, ECN impact, substitutes."""
import os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
os.environ.setdefault("PG_PASSWORD", "admin")
os.environ.setdefault("INVENTORY_SECRET_KEY", "bom-ecn-validation")
os.environ.setdefault("WTF_CSRF_ENABLED", "0")

from app import create_app
from scripts.trial_audit_auth import prepare_trial_audit_passwords
import psycopg2
from psycopg2.extras import RealDictCursor

app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
passwords = prepare_trial_audit_passwords()
client = app.test_client()
login = client.post("/login", data={"username": "pilot_admin", "password": passwords.get("pilot_admin")}, follow_redirects=False)
print(f"Login: {login.status_code}")
if login.status_code != 302:
    sys.exit(1)

conn = psycopg2.connect(host="localhost", port=5432, database="wms", user="postgres", password="admin")
cur = conn.cursor(cursor_factory=RealDictCursor)

print("\n=== Step 1: BOM versions list ===")
resp = client.get("/bom/versions", follow_redirects=False)
print(f"GET /bom/versions: {resp.status_code}")

print("\n=== Step 2: BOM versions by BOM (if BOM exists) ===")
cur.execute("SELECT id, bom_no FROM boms ORDER BY id LIMIT 1")
bom = cur.fetchone()
if bom:
    print(f"  Using BOM: id={bom['id']} no={bom['bom_no']}")
    resp = client.get(f"/bom/{bom['id']}/versions", follow_redirects=False)
    print(f"  GET /bom/{bom['id']}/versions: {resp.status_code}")
    if resp.status_code == 500:
        print("  BUG: 500 error - likely query_db list/dict issue")
    elif resp.status_code == 200:
        print("  OK")
else:
    print("  No BOMs found")

print("\n=== Step 3: BOM version detail (if version exists) ===")
cur.execute("SELECT id, version_no, bom_id FROM bom_versions ORDER BY id LIMIT 1")
version = cur.fetchone()
if version:
    print(f"  Using version: id={version['id']} no={version['version_no']}")
    resp = client.get(f"/bom/versions/{version['id']}", follow_redirects=False)
    print(f"  GET /bom/versions/{version['id']}: {resp.status_code}")
    if resp.status_code == 500:
        print("  BUG: 500 error - likely get_version query_db issue")
    elif resp.status_code == 200:
        print("  OK")
else:
    print("  No BOM versions found")

print("\n=== Step 4: Work order snapshots (if work order exists) ===")
cur.execute("SELECT id, wo_no FROM work_orders ORDER BY id LIMIT 1")
wo = cur.fetchone()
if wo:
    print(f"  Using work order: id={wo['id']} no={wo['wo_no']}")
    resp = client.get(f"/work-orders/{wo['id']}/snapshots", follow_redirects=False)
    print(f"  GET /work-orders/{wo['id']}/snapshots: {resp.status_code}")
    if resp.status_code == 500:
        print("  BUG: 500 error - likely snapshot service query_db issue")
    elif resp.status_code == 200:
        print("  OK")

print("\n=== Step 5: ECN impact view (if ECN exists) ===")
cur.execute("SELECT id, ecn_no FROM bom_engineering_changes ORDER BY id LIMIT 1")
ecn = cur.fetchone()
if ecn:
    print(f"  Using ECN: id={ecn['id']} no={ecn['ecn_no']}")
    resp = client.get(f"/ecn/{ecn['id']}/impact", follow_redirects=False)
    print(f"  GET /ecn/{ecn['id']}/impact: {resp.status_code}")
    if resp.status_code == 500:
        print("  BUG: 500 error - likely ECN impact service query_db issue")
    elif resp.status_code == 200:
        print("  OK")
else:
    print("  No ECNs found")

print("\n=== Step 6: ECN impact tasks queue ===")
resp = client.get("/ecn/impact-tasks", follow_redirects=False)
print(f"GET /ecn/impact-tasks: {resp.status_code}")

print("\n=== Step 7: ECN action tasks ===")
resp = client.get("/ecn/action-tasks", follow_redirects=False)
print(f"GET /ecn/action-tasks: {resp.status_code}")

print("\n=== Step 8: BOM substitutes (if BOM item exists) ===")
cur.execute("SELECT id FROM bom_items ORDER BY id LIMIT 1")
bi = cur.fetchone()
if bi:
    print(f"  Using BOM item: id={bi['id']}")
    resp = client.get(f"/bom/items/{bi['id']}/substitutes", follow_redirects=False)
    print(f"  GET /bom/items/{bi['id']}/substitutes: {resp.status_code}")
    if resp.status_code == 500:
        print("  BUG: 500 error - likely substitute service query_db issue")
    elif resp.status_code == 200:
        print("  OK")
else:
    print("  No BOM items found")

cur.close()
conn.close()
print("\nDone.")
