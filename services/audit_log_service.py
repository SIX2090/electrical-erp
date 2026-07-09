import os
import logging

import psycopg2

from services.env_config import get_pg_password

logger = logging.getLogger(__name__)


def _db_config():
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "dbname": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }


def _doc_context(endpoint):
    parts = [part for part in (endpoint or "").split("/") if part]
    if not parts:
        return None, None
    doc_type = parts[0][:64]
    doc_id = None
    if len(parts) > 1 and parts[1].isdigit():
        doc_id = parts[1][:64]
    return doc_type, doc_id


def log_action(user_id, username, method, endpoint, ip_address, doc_type=None, doc_id=None):
    resolved_doc_type, resolved_doc_id = _doc_context(endpoint)
    doc_type = doc_type or resolved_doc_type
    doc_id = doc_id or resolved_doc_id
    try:
        with psycopg2.connect(**_db_config(), connect_timeout=int(os.environ.get("PG_CONNECT_TIMEOUT", "5"))) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO audit_logs
                        (user_id, username, method, endpoint, doc_type, doc_id, ip_address)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        user_id,
                        (username or "")[:64],
                        (method or "")[:10],
                        (endpoint or "")[:256],
                        (doc_type or "")[:64],
                        (doc_id or "")[:64],
                        (ip_address or "")[:45],
                    ),
                )
    except Exception:
        logger.exception("audit log write failed")
        return False
    return True
