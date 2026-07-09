from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("WTF_CSRF_ENABLED", "0")

from app import create_app, get_db_config  # noqa: E402
from services.app_runtime import connect_db  # noqa: E402


ENGINEERING_PATHS = [
    "/engineering/technical-confirmations",
    "/engineering/technical-confirmations/new",
    "/engineering/drawings",
    "/bom",
    "/bom/ecn",
    "/production-routings",
    "/work-centers",
]

REQUIRED_COLUMNS = {
    "process_program_no",
    "tooling_requirement",
    "inspection_standard",
    "ecn_impact_summary",
}


def main() -> int:
    app = create_app()
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "engineering_audit"
        session["role"] = "admin"

    failures: list[str] = []
    print("engineering_runtime_smoke=running")
    for path in ENGINEERING_PATHS:
        response = client.get(path, follow_redirects=False)
        print(f"{path} status={response.status_code}")
        if response.status_code >= 400:
            failures.append(f"{path} returned {response.status_code}")

    with connect_db(get_db_config()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='engineering_technical_confirmations'
                  AND column_name IN ('process_program_no', 'tooling_requirement', 'inspection_standard', 'ecn_impact_summary')
                """
            )
            rows = cur.fetchall()
    found = {row["column_name"] for row in rows}
    missing = sorted(REQUIRED_COLUMNS - found)
    print("engineering_readiness_columns=" + ",".join(sorted(found)))
    if missing:
        failures.append("missing columns: " + ",".join(missing))

    print("engineering_runtime_smoke=ok" if not failures else "engineering_runtime_smoke=failed")
    for failure in failures:
        print("failed | " + failure)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
