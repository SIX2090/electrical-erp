import os


DB_CONFIG = {
    "host": os.environ.get("PG_HOST") or os.environ.get("DB_HOST") or "127.0.0.1",
    "port": int(os.environ.get("PG_PORT") or os.environ.get("DB_PORT") or "5432"),
    "dbname": os.environ.get("PG_DATABASE") or os.environ.get("DB_NAME") or "wms",
    "user": os.environ.get("PG_USER") or os.environ.get("DB_USER") or "wms_user",
    "password": os.environ.get("PG_PASSWORD") or os.environ.get("DB_PASSWORD") or "",
}
