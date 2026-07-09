"""Validate B-3 cost engine: run, list, detail, reconciliation, variance.

Steps:
1. Cost engine home page
2. Cost runs list
3. Cost run detail (if runs exist)
4. Cost reconciliation page
5. Cost variance report
6. Execute a cost calculation run (dry)
7. Execute cost reconciliation (dry)
"""
import os
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
os.environ.setdefault("PG_PASSWORD", "admin")
os.environ.setdefault("INVENTORY_SECRET_KEY", "cost-validation-session")
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

print("\n=== Step 1: Cost engine home page ===")
resp = client.get("/cost", follow_redirects=False)
print(f"GET /cost: {resp.status_code}")
if resp.status_code == 200:
    print("  Home page rendered")

print("\n=== Step 2: Cost runs list ===")
resp = client.get("/cost/runs", follow_redirects=False)
print(f"GET /cost/runs: {resp.status_code}")
if resp.status_code == 200:
    content = resp.data.decode("utf-8", errors="replace")
    if "COST-" in content or "cost_run" in content.lower():
        print("  Runs found in page")
    else:
        print("  No runs visible in page")

print("\n=== Step 3: Cost run detail (if runs exist) ===")
import psycopg2
from psycopg2.extras import RealDictCursor
conn = psycopg2.connect(host="localhost", port=5432, database="wms", user="postgres", password="admin")
cur = conn.cursor(cursor_factory=RealDictCursor)
cur.execute("SELECT id, run_no, status FROM cost_runs ORDER BY id DESC LIMIT 1")
run = cur.fetchone()
if run:
    print(f"  Latest run: id={run['id']} run_no={run['run_no']} status={run['status']}")
    resp = client.get(f"/cost/runs/{run['id']}", follow_redirects=False)
    print(f"  GET /cost/runs/{run['id']}: {resp.status_code}")
    if resp.status_code == 200:
        print("  Run detail rendered successfully")
else:
    print("  No cost runs found")

print("\n=== Step 4: Cost reconciliation page ===")
resp = client.get("/cost/reconciliation", follow_redirects=False)
print(f"GET /cost/reconciliation: {resp.status_code}")
if resp.status_code == 200:
    print("  Reconciliation page rendered")

print("\n=== Step 5: Cost variance report ===")
resp = client.get("/cost/variance", follow_redirects=False)
print(f"GET /cost/variance: {resp.status_code}")
if resp.status_code == 200:
    print("  Variance report rendered")
elif resp.status_code == 302:
    print(f"  Redirected to: {resp.headers.get('Location')}")

print("\n=== Step 6: Execute cost calculation run ===")
# Find any work order to run cost calculation
cur.execute("SELECT id, wo_no, status FROM work_orders ORDER BY id LIMIT 1")
wo = cur.fetchone()
if wo:
    print(f"  Using work order: id={wo['id']} no={wo['wo_no']} status={wo['status']}")
    resp = client.post("/cost/run", data={
        "work_order_id": str(wo['id']),
    }, follow_redirects=False)
    print(f"  POST /cost/run: {resp.status_code}")
    if resp.status_code == 302:
        location = resp.headers.get("Location", "")
        print(f"  Redirected to: {location}")
        cur.execute("SELECT id, run_no, status, total_cost FROM cost_runs ORDER BY id DESC LIMIT 1")
        new_run = cur.fetchone()
        if new_run:
            print(f"  New/latest run: id={new_run['id']} run_no={new_run['run_no']} status={new_run['status']} total_cost={new_run['total_cost']}")
    elif resp.status_code == 200:
        content = resp.data.decode("utf-8", errors="replace")
        if "danger" in content or "错误" in content:
            print("  Run may have failed - check response")
        print(f"  Response length: {len(content)}")
else:
    print("  No work orders found")

print("\n=== Step 7: Execute cost reconciliation ===")
resp = client.post("/cost/reconciliation/run", data={
    "period": "2026-06",
}, follow_redirects=False)
print(f"  POST /cost/reconciliation/run: {resp.status_code}")
if resp.status_code == 302:
    location = resp.headers.get("Location", "")
    print(f"  Redirected to: {location}")
elif resp.status_code == 200:
    content = resp.data.decode("utf-8", errors="replace")
    print(f"  Response length: {len(content)}")

print("\n=== Step 8: Check variance calculation correctness ===")
# Check if labor/overhead cost lines have correct variance (should be 0, not 100%)
cur.execute("""
    SELECT cri.cost_type, cri.amount, cri.standard_cost, cri.variance_amount, cri.variance_reason
    FROM cost_run_items cri
    WHERE cri.cost_type IN ('labor', 'overhead')
    ORDER BY cri.id DESC LIMIT 10
""")
variance_rows = cur.fetchall()
if variance_rows:
    print(f"  Found {len(variance_rows)} labor/overhead cost lines:")
    for r in variance_rows:
        pct = "N/A"
        if r['amount'] and r['amount'] != 0:
            pct = f"{(r['variance_amount'] / r['amount'] * 100):.1f}%"
        print(f"    type={r['cost_type']} amount={r['amount']} std={r['standard_cost']} variance={r['variance_amount']} ({pct}) reason={r['variance_reason']}")
    # Check for the bug: if variance_amount == amount for all labor/overhead lines, the bug exists
    buggy = all(r['variance_amount'] == r['amount'] for r in variance_rows if r['amount'] and r['amount'] != 0)
    if buggy:
        print("  BUG DETECTED: All labor/overhead lines show 100% variance (variance_amount == amount)")
    else:
        print("  Variance calculation looks correct for labor/overhead")
else:
    print("  No labor/overhead cost lines found to check")

cur.close()
conn.close()
print("\nDone.")
