import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


PATHS = [
    "/adjustments",
    "/transfers",
    "/inventory_checks",
    "/assembly-orders",
    "/disassembly-orders",
    "/sales-returns",
    "/purchase-returns",
]

REQUIRED_MARKERS = [
    "批量确认过账",
    "批量关闭",
    "批量取消",
    "批量打印/导出提示",
    "bulk-row-check",
    "/inventory/bulk-action",
]

FORBIDDEN_MARKERS = ["\ufffd", "????"]


def main():
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "inventory-bulk-list-runtime-audit")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")

    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    failures = []
    with app.test_client() as client:
        client.post("/login", data={"username": "admin", "password": "admin"}, follow_redirects=False)
        for path in PATHS:
            response = client.get(path)
            text = response.get_data(as_text=True)
            missing = [marker for marker in REQUIRED_MARKERS if marker not in text]
            dirty = [marker for marker in FORBIDDEN_MARKERS if marker in text]
            ok = response.status_code == 200 and not missing and not dirty
            print(f"{'ok' if ok else 'failed'} | {path} | status={response.status_code}")
            if not ok:
                failures.append({"path": path, "status": response.status_code, "missing": missing, "dirty": dirty})
    print("inventory_bulk_list_runtime=ok" if not failures else "inventory_bulk_list_runtime=failed")
    if failures:
        for failure in failures:
            print(f"failed | {failure}")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
