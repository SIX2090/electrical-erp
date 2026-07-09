"""Database connection helpers using environment-based configuration."""
import os

from services.app_runtime import connect_db
from services.env_config import get_pg_password


def get_db_config():
    """Return a dict of PostgreSQL connection parameters from environment variables."""
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "database": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }


def get_db_connection():
    """Return a new PostgreSQL connection using the current db config."""
    return connect_db(get_db_config(), cursor_factory=None)
