"""Validate C-1 voucher generation: 4 source types, preview, list, post."""
import os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
os.environ.setdefault("PG_PASSWORD", "admin")
os.environ.setdefault("INVENTORY_SECRET_KEY", "voucher-c1-validation")
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

print("\n=== Step 1: Voucher list page ===")
resp = client.get("/finance/vouchers", follow_redirects=False)
print(f"GET /finance/vouchers: {resp.status_code}")
if resp.status_code == 200:
    print("  OK - voucher list rendered")

print("\n=== Step 2: Voucher generation preview page ===")
resp = client.get("/finance/vouchers/generate", follow_redirects=False)
print(f"GET /finance/vouchers/generate: {resp.status_code}")
if resp.status_code == 200:
    print("  OK - preview page rendered")

print("\n=== Step 3: Batch generation form ===")
resp = client.get("/finance/vouchers/generate-batch", follow_redirects=False)
print(f"GET /finance/vouchers/generate-batch: {resp.status_code}")
if resp.status_code == 200:
    print("  OK - batch form rendered")

print("\n=== Step 4: Generate voucher from sales invoice ===")
# Find a sales invoice without a voucher
cur.execute("""
    SELECT si.id, si.invoice_no, si.amount_with_tax, si.total_amount, si.tax_amount
    FROM sales_invoices si
    LEFT JOIN vouchers v ON v.source_type='sales_invoice' AND v.source_no=si.invoice_no
    WHERE v.id IS NULL AND si.amount_with_tax > 0
    ORDER BY si.id LIMIT 1
""")
si = cur.fetchone()
if si:
    print(f"  Using sales invoice: id={si['id']} no={si['invoice_no']} amount_with_tax={si['amount_with_tax']}")
    resp = client.post("/finance/vouchers/generate-batch", data={
        "selected_items": [f"sales_invoice:{si['id']}"],
    }, follow_redirects=False)
    print(f"  POST /finance/vouchers/generate-batch: {resp.status_code}")
    if resp.status_code == 302:
        # Check voucher was created
        cur.execute("SELECT id, voucher_no, status, auto_generated, total_debit, total_credit FROM vouchers WHERE source_type='sales_invoice' AND source_no=%s ORDER BY id DESC LIMIT 1", (si['invoice_no'],))
        v = cur.fetchone()
        if v:
            print(f"  Voucher created: id={v['id']} no={v['voucher_no']} status={v['status']} auto_generated={v['auto_generated']} debit={v['total_debit']} credit={v['total_credit']}")
            if v['auto_generated'] == True:
                print("  OK - auto_generated=TRUE set correctly")
            else:
                print("  BUG: auto_generated not set to TRUE")
            if v['total_debit'] == v['total_credit']:
                print("  OK - debit=credit (balanced)")
            else:
                print("  BUG: debit != credit (unbalanced)")
        else:
            print("  BUG: voucher not created")
    elif resp.status_code == 200:
        content = resp.data.decode("utf-8", errors="replace")
        if "错误" in content or "danger" in content:
            print("  Generation may have failed - check response")
        print(f"  Response length: {len(content)}")
else:
    print("  No sales invoices without vouchers found")

print("\n=== Step 5: Generate voucher from purchase invoice ===")
cur.execute("""
    SELECT pi.id, pi.invoice_no, pi.amount_with_tax
    FROM purchase_invoices pi
    LEFT JOIN vouchers v ON v.source_type='purchase_invoice' AND v.source_no=pi.invoice_no
    WHERE v.id IS NULL AND pi.amount_with_tax > 0
    ORDER BY pi.id LIMIT 1
""")
pi = cur.fetchone()
if pi:
    print(f"  Using purchase invoice: id={pi['id']} no={pi['invoice_no']}")
    resp = client.post("/finance/vouchers/generate-batch", data={
        "selected_items": [f"purchase_invoice:{pi['id']}"],
    }, follow_redirects=False)
    print(f"  POST /finance/vouchers/generate-batch: {resp.status_code}")
    if resp.status_code == 302:
        cur.execute("SELECT id, voucher_no, status, auto_generated FROM vouchers WHERE source_type='purchase_invoice' AND source_no=%s ORDER BY id DESC LIMIT 1", (pi['invoice_no'],))
        v = cur.fetchone()
        if v:
            print(f"  Voucher created: id={v['id']} no={v['voucher_no']} status={v['status']} auto_generated={v['auto_generated']}")
else:
    print("  No purchase invoices without vouchers found")

print("\n=== Step 6: Generate voucher from customer receipt ===")
cur.execute("""
    SELECT r.id, r.receipt_no, r.amount
    FROM customer_receipts r
    LEFT JOIN vouchers v ON v.source_type='customer_receipt' AND v.source_no=r.receipt_no
    WHERE v.id IS NULL AND r.amount > 0
    ORDER BY r.id LIMIT 1
""")
cr = cur.fetchone()
if cr:
    print(f"  Using customer receipt: id={cr['id']} no={cr['receipt_no']}")
    resp = client.post("/finance/vouchers/generate-batch", data={
        "selected_items": [f"customer_receipt:{cr['id']}"],
    }, follow_redirects=False)
    print(f"  POST /finance/vouchers/generate-batch: {resp.status_code}")
    if resp.status_code == 302:
        cur.execute("SELECT id, voucher_no, status, auto_generated FROM vouchers WHERE source_type='customer_receipt' AND source_no=%s ORDER BY id DESC LIMIT 1", (cr['receipt_no'],))
        v = cur.fetchone()
        if v:
            print(f"  Voucher created: id={v['id']} no={v['voucher_no']} status={v['status']} auto_generated={v['auto_generated']}")
else:
    print("  No customer receipts without vouchers found")

print("\n=== Step 7: Generate voucher from supplier payment ===")
cur.execute("""
    SELECT p.id, p.payment_no, p.amount
    FROM supplier_payments p
    LEFT JOIN vouchers v ON v.source_type='supplier_payment' AND v.source_no=p.payment_no
    WHERE v.id IS NULL AND p.amount > 0
    ORDER BY p.id LIMIT 1
""")
sp = cur.fetchone()
if sp:
    print(f"  Using supplier payment: id={sp['id']} no={sp['payment_no']}")
    resp = client.post("/finance/vouchers/generate-batch", data={
        "selected_items": [f"supplier_payment:{sp['id']}"],
    }, follow_redirects=False)
    print(f"  POST /finance/vouchers/generate-batch: {resp.status_code}")
    if resp.status_code == 302:
        cur.execute("SELECT id, voucher_no, status, auto_generated FROM vouchers WHERE source_type='supplier_payment' AND source_no=%s ORDER BY id DESC LIMIT 1", (sp['payment_no'],))
        v = cur.fetchone()
        if v:
            print(f"  Voucher created: id={v['id']} no={v['voucher_no']} status={v['status']} auto_generated={v['auto_generated']}")
else:
    print("  No supplier payments without vouchers found")

print("\n=== Step 8: Verify voucher detail page ===")
cur.execute("SELECT id FROM vouchers ORDER BY id DESC LIMIT 1")
v = cur.fetchone()
if v:
    resp = client.get(f"/finance/vouchers/{v['id']}", follow_redirects=False)
    print(f"GET /finance/vouchers/{v['id']}: {resp.status_code}")
    if resp.status_code == 200:
        print("  OK - voucher detail rendered")

print("\n=== Step 9: Verify auto_generated shows in preview ===")
resp = client.get("/finance/vouchers/generate", follow_redirects=False)
print(f"GET /finance/vouchers/generate (after generation): {resp.status_code}")
if resp.status_code == 200:
    content = resp.data.decode("utf-8", errors="replace")
    # Check if the preview shows the voucher as generated
    if "已生成" in content or "auto_generated" in content.lower():
        print("  OK - preview shows generated status")
    else:
        print("  Preview page rendered (checking if generated vouchers are marked)")

cur.close()
conn.close()
print("\nDone.")
