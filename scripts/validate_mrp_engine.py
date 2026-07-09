"""Validate B-1 MRP engine: run, list, suggestions, kitting analysis.

This script validates the MRP engine by:
1. Listing existing MRP runs
2. Viewing run details
3. Listing suggestions
4. Running kitting analysis for a work order
5. Optionally running a new MRP execution (dry validation)
"""
import os
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
os.environ.setdefault("PG_PASSWORD", "admin")
os.environ.setdefault("INVENTORY_SECRET_KEY", "mrp-validation-session")
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

print("\n=== Step 1: MRP home page ===")
resp = client.get("/mrp", follow_redirects=False)
print(f"GET /mrp: {resp.status_code}")

print("\n=== Step 2: MRP runs list ===")
resp = client.get("/mrp/runs", follow_redirects=False)
print(f"GET /mrp/runs: {resp.status_code}")
if resp.status_code == 200:
    content = resp.data.decode("utf-8", errors="replace")
    # Check for run entries
    if "MRP-" in content or "mrp_run" in content.lower():
        print("  Runs found in page")
    else:
        print("  No runs visible in page")

print("\n=== Step 3: MRP suggestions list ===")
resp = client.get("/mrp/suggestions", follow_redirects=False)
print(f"GET /mrp/suggestions: {resp.status_code}")
if resp.status_code == 200:
    content = resp.data.decode("utf-8", errors="replace")
    if "suggestion" in content.lower():
        print("  Suggestions page rendered")

print("\n=== Step 4: MRP kitting analysis ===")
# Find a work order to analyze
import psycopg2
from psycopg2.extras import RealDictCursor
conn = psycopg2.connect(host="localhost", port=5432, database="wms", user="postgres", password="admin")
cur = conn.cursor(cursor_factory=RealDictCursor)
cur.execute("SELECT id, wo_no FROM work_orders ORDER BY id LIMIT 1")
wo = cur.fetchone()
if wo:
    print(f"  Using work order: id={wo['id']} no={wo['wo_no']}")
    resp = client.get(f"/mrp/kitting?work_order_id={wo['id']}", follow_redirects=False)
    print(f"  GET /mrp/kitting?work_order_id={wo['id']}: {resp.status_code}")
    if resp.status_code == 200:
        print("  Kitting analysis rendered successfully")
    elif resp.status_code == 302:
        print(f"  Redirected to: {resp.headers.get('Location')}")
else:
    print("  No work orders found")

print("\n=== Step 5: MRP run detail (if runs exist) ===")
cur.execute("SELECT id, run_no FROM mrp_runs ORDER BY id DESC LIMIT 1")
run = cur.fetchone()
if run:
    print(f"  Latest run: id={run['id']} run_no={run['run_no']}")
    resp = client.get(f"/mrp/runs/{run['id']}", follow_redirects=False)
    print(f"  GET /mrp/runs/{run['id']}: {resp.status_code}")
    if resp.status_code == 200:
        print("  Run detail rendered successfully")

print("\n=== Step 6: API - MRP run suggestions ===")
if run:
    resp = client.get(f"/api/mrp/runs/{run['id']}/suggestions", follow_redirects=False)
    print(f"  GET /api/mrp/runs/{run['id']}/suggestions: {resp.status_code}")
    if resp.status_code == 200:
        try:
            data = resp.get_json()
            if data:
                print(f"  API returned: {json.dumps(data, ensure_ascii=False, default=str)[:200]}")
        except Exception as e:
            print(f"  JSON parse error: {e}")

print("\n=== Step 7: MRP run execution (dry) ===")
# Run MRP for a sales order if one exists
cur.execute("SELECT id, order_no FROM sales_orders ORDER BY id LIMIT 1")
so = cur.fetchone()
if so:
    print(f"  Using sales order: id={so['id']} no={so['order_no']}")
    resp = client.post("/mrp/run", data={
        "source_type": "sales_order",
        "source_id": str(so['id']),
    }, follow_redirects=False)
    print(f"  POST /mrp/run: {resp.status_code}")
    if resp.status_code == 302:
        location = resp.headers.get("Location", "")
        print(f"  Redirected to: {location}")
        # Check if new run was created
        cur.execute("SELECT id, run_no, status FROM mrp_runs ORDER BY id DESC LIMIT 1")
        new_run = cur.fetchone()
        if new_run:
            print(f"  New/latest run: id={new_run['id']} run_no={new_run['run_no']} status={new_run['status']}")
else:
    print("  No sales orders found for MRP run")

cur.close()
conn.close()
print("\nDone.")
