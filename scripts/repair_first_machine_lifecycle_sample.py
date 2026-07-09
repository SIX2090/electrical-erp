from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.app_runtime import connect_db
from services.env_config import get_pg_password
from scripts.first_machine_trial_utils import ensure_first_machine_lifecycle_sample, load_first_machine_values


def get_db_config() -> dict:
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "database": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }


def main() -> int:
    os.environ.setdefault("PG_PASSWORD", "admin")
    values = load_first_machine_values()
    if values.get("project_code") != "PJ-GT-TRIAL-20260526-001" or values.get("serial_no") != "SN-GT-TRIAL-20260526-001":
        print("repair_first_machine_lifecycle_sample=blocked")
        print("reason=unexpected first-machine project or serial axis")
        return 1

    conn = connect_db(get_db_config())
    try:
        with conn.cursor() as cur:
            result = ensure_first_machine_lifecycle_sample(cur, values)
        conn.commit()
    finally:
        conn.close()

    print("repair_first_machine_lifecycle_sample=ok")
    for key in (
        "project_code",
        "serial_no",
        "sales_order_id",
        "bom_id",
        "work_order_id",
        "purchase_order_id",
        "subcontract_order_id",
        "shipment_id",
    ):
        print(f"{key}={result.get(key)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
