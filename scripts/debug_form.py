"""Debug form page toolbar check."""
import os
import sys
import re
sys.path.insert(0, r"c:\erp")
os.environ.setdefault("PG_PASSWORD", "admin")
import requests

BASE = "http://127.0.0.1:5000"

from scripts.trial_audit_auth import prepare_trial_audit_passwords
pwd = prepare_trial_audit_passwords(["admin"]).get("admin", "admin")
session = requests.Session()
r_get = session.get(f"{BASE}/login", timeout=10)
csrf_match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r_get.text)
csrf_token = csrf_match.group(1) if csrf_match else None
data = {"username": "admin", "password": pwd}
if csrf_token:
    data["csrf_token"] = csrf_token
session.post(f"{BASE}/login", data=data, allow_redirects=False)

# Test a form page
r = session.get(f"{BASE}/purchase_order/new", timeout=10)
print(f"Status: {r.status_code}")
print(f"Length: {len(r.text)}")

# Check for menu_bar
has_menu = "document-menu-bar" in r.text or "document_menu_bar" in r.text or "operation-toolbar" in r.text
print(f"menu_bar found: {has_menu}")

# Check for save
has_save = "保存" in r.text or "bi-save" in r.text or "submit" in r.text.lower() or "global-submit" in r.text
print(f"save found: {has_save}")

# Check for back
has_back = "返回列表" in r.text or "返回" in r.text or "bi-arrow-left" in r.text or "新增" in r.text
print(f"back found: {has_back}")

# Check for status
has_status = "doc_status" in r.text or "status" in r.text.lower()
print(f"status found: {has_status}")

# Debug regex
import re
print("\n--- Regex debug ---")
for key, patterns in [("menu_bar", [r"document-menu-bar", r"document_menu_bar", r"operation-toolbar"]),
                       ("save", [r"保存", r"bi-save", r"submit", r"global-submit"]),
                       ("back", [r"返回列表", r"返回", r"bi-arrow-left", r"新增"]),
                       ("status", [r"doc_status", r"status.*pill", r"document-menu-bar__status"])]:
    for pat in patterns:
        m = re.search(pat, r.text, re.IGNORECASE)
        print(f"  {key} pattern '{pat}': {'FOUND' if m else 'not found'}")
