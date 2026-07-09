"""Transaction context managers and DB cursor helpers for atomic operations."""
from contextlib import contextmanager


@contextmanager
def db_transaction(get_db, cursor_factory=None):
    """Context manager that commits on success and rolls back on exception."""
    conn = get_db(cursor_factory=cursor_factory) if cursor_factory is not None else get_db()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def execute_in_transaction(get_db, operations, cursor_factory=None):
    """Execute a callable of operations within a single transaction scope."""
    with db_transaction(get_db, cursor_factory=cursor_factory) as conn:
        with conn.cursor() as cur:
            return operations(cur)


def cursor_db_helpers(cur):
    """Build query_db, execute_db, and execute_and_return closures over a cursor."""
    def query_db(sql, params=None, one=False):
        cur.execute(sql, params or ())
        rows = cur.fetchall()
        if one:
            return rows[0] if rows else None
        return rows

    def execute_db(sql, params=None):
        cur.execute(sql, params or ())

    def execute_and_return(sql, params=None):
        cur.execute(sql, params or ())
        return cur.fetchone()

    query_db._uses_transaction_cursor = True
    execute_db._uses_transaction_cursor = True
    execute_and_return._uses_transaction_cursor = True
    return query_db, execute_db, execute_and_return
