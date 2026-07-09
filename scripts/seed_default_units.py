from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.app_runtime import create_db_helpers
from services.env_config import get_pg_password
from services.industry_defaults import seed_default_units


def get_db_config():
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "database": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }


def main():
    _, _, execute_db, _ = create_db_helpers(None, get_db_config())
    count = seed_default_units(execute_db)
    print(f"seeded_units={count}")


if __name__ == "__main__":
    main()
