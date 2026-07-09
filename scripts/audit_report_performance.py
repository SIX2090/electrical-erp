from pathlib import Path
import os
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


REPORT_HINTS = (
    "/reports",
    "/report",
    "/finance/financial-statements",
    "/finance/period-close",
    "/finance/inventory-cost",
    "/finance/reports",
    "/production/reports",
    "/sales/reports",
    "/service/reports",
    "/inventory/reports",
)


SKIP_PREFIXES = ("/static/", "/api/")


def collect_report_paths(app):
    paths = set()
    for rule in app.url_map.iter_rules():
        if "GET" not in rule.methods:
            continue
        path = str(rule.rule)
        if any(path.startswith(prefix) for prefix in SKIP_PREFIXES):
            continue
        if "<" in path:
            continue
        if any(hint in path for hint in REPORT_HINTS):
            paths.add(path)
    return sorted(paths)


def main():
    os.environ.setdefault("INVENTORY_SECRET_KEY", "report-performance-audit")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")
    os.environ.setdefault("LOGIN_RATE_LIMIT", "1000")

    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    rows = []
    with app.test_client() as client:
        client.post("/login", data={"username": "admin", "password": "admin"}, follow_redirects=False)
        for path in collect_report_paths(app):
            start = time.perf_counter()
            try:
                response = client.get(path, follow_redirects=False)
                elapsed_ms = (time.perf_counter() - start) * 1000
                body = response.get_data()
                rows.append(
                    {
                        "path": path,
                        "status": response.status_code,
                        "elapsed_ms": elapsed_ms,
                        "bytes": len(body),
                        "location": response.headers.get("Location", ""),
                    }
                )
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - start) * 1000
                rows.append(
                    {
                        "path": path,
                        "status": "error",
                        "elapsed_ms": elapsed_ms,
                        "bytes": 0,
                        "location": type(exc).__name__,
                    }
                )

    rows.sort(key=lambda item: item["elapsed_ms"], reverse=True)
    print("report_performance_audit=ok")
    print(f"checked_reports={len(rows)}")
    for row in rows:
        flag = "slow" if row["elapsed_ms"] >= 1000 else "ok"
        size_flag = "large" if row["bytes"] >= 500_000 else "normal"
        print(
            f"{flag} | {size_flag} | {row['elapsed_ms']:.1f} ms | "
            f"{row['bytes']} bytes | HTTP {row['status']} | {row['path']} | {row['location']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
