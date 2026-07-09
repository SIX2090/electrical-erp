import time


class FixedWindowRateLimiter:
    def __init__(self, limit=20, window_seconds=60, query_db=None, execute_db=None):
        self.limit = limit
        self.window_seconds = window_seconds
        self.query_db = query_db
        self.execute_db = execute_db
        self._windows = {}

    def _db_enabled(self):
        return self.query_db is not None and self.execute_db is not None

    def ensure_schema(self):
        if not self._db_enabled():
            return
        self.execute_db(
            """
            CREATE TABLE IF NOT EXISTS rate_limit_windows (
                limiter_key VARCHAR(160) NOT NULL,
                window_start BIGINT NOT NULL,
                request_count INTEGER NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (limiter_key, window_start)
            )
            """
        )

    def allow(self, key):
        now = time.time()
        window_start = int(now - (now % self.window_seconds))
        if self._db_enabled():
            row = self.query_db(
                """
                INSERT INTO rate_limit_windows (limiter_key, window_start, request_count, updated_at)
                VALUES (%s,%s,1,NOW())
                ON CONFLICT (limiter_key, window_start) DO UPDATE
                SET request_count=rate_limit_windows.request_count + 1,
                    updated_at=NOW()
                RETURNING request_count
                """,
                (str(key), window_start),
                one=True,
            )
            return int(row.get("request_count") or 0) <= self.limit
        # Prune expired windows to keep the in-memory dict bounded.
        expired_cutoff = window_start - self.window_seconds
        for k in list(self._windows.keys()):
            record = self._windows[k]
            if not record or record[0] < expired_cutoff:
                self._windows.pop(k, None)
        record = self._windows.get(key)
        if not record or record[0] != window_start:
            self._windows[key] = [window_start, 1]
            return True
        if record[1] >= self.limit:
            return False
        record[1] += 1
        return True
