"""Test login and debug."""
import os
import sys
sys.path.insert(0, r"c:\erp")
os.environ.setdefault("PG_PASSWORD", "admin")
import requests

BASE = "http://127.0.0.1:5000"

# First try to reset password
try:
    from scripts.trial_audit_auth import prepare_trial_audit_passwords
    result = prepare_trial_audit_passwords(["admin", "pilot_admin"])
    print(f"Password reset result: {result}")
except Exception as e:
    print(f"Password reset error: {type(e).__name__}: {e}")

# Try login - first GET to obtain CSRF token
session = requests.Session()
r_get = session.get(f"{BASE}/login")
print(f"GET /login: status={r_get.status_code}")

# Extract CSRF token
import re
csrf_match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r_get.text)
csrf_token = csrf_match.group(1) if csrf_match else None
print(f"CSRF token found: {bool(csrf_token)}")

for user, pwd in [("admin", "admin"), ("pilot_admin", "admin")]:
    data = {"username": user, "password": pwd}
    if csrf_token:
        data["csrf_token"] = csrf_token
    r = session.post(f"{BASE}/login", data=data, allow_redirects=False)
    print(f"Login {user}/{pwd}: status={r.status_code}, location={r.headers.get('Location', 'N/A')}")
    if r.status_code in (302, 303):
        print(f"  SUCCESS - logged in as {user}")
        # Test a page
        r2 = session.get(f"{BASE}/", timeout=10)
        print(f"  Home page: status={r2.status_code}, length={len(r2.text)}")
        break
    else:
        # Check flash message
        flashes = re.findall(r'flash[^>]*>([^<]+)<', r.text)
        if flashes:
            print(f"  Flash messages: {flashes}")
        if 'name="username"' in r.text:
            print("  Login form present")
        if "错误" in r.text:
            idx = r.text.find("错误")
            print(f"  Error context: ...{r.text[max(0,idx-30):idx+80]}...")
