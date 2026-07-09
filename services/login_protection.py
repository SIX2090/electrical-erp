import time
from datetime import datetime, timedelta


class LoginAttemptTracker:
    def __init__(self, max_failures=5, lockout_seconds=900, query_db=None, execute_db=None):
        self.max_failures = max_failures
        self.lockout_seconds = lockout_seconds
        self.query_db = query_db
        self.execute_db = execute_db
        self._state = {}

    def _key(self, username):
        return (username or "").strip().lower()

    def _db_enabled(self):
        return self.query_db is not None and self.execute_db is not None

    def _db_record(self, key):
        rows = self.query_db(
            "SELECT username, failures, locked_until FROM login_attempts WHERE username=%s",
            (key,),
        )
        return rows[0] if rows else None

    def ensure_schema(self):
        if not self._db_enabled():
            return
        self.execute_db(
            """
            CREATE TABLE IF NOT EXISTS login_attempts (
                username VARCHAR(80) PRIMARY KEY,
                failures INTEGER DEFAULT 0,
                locked_until TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    def is_locked(self, username):
        key = self._key(username)
        if self._db_enabled():
            record = self._db_record(key)
            if not record:
                return False
            locked_until = record.get("locked_until")
            if not locked_until:
                return False
            if locked_until <= datetime.now():
                self.execute_db("UPDATE login_attempts SET locked_until=NULL WHERE username=%s", (key,))
                return False
            return True
        record = self._state.get(key)
        if not record:
            return False
        locked_until = record.get("locked_until", 0)
        if locked_until <= time.time():
            if locked_until:
                self._state.pop(key, None)
            return False
        return True

    def remaining_seconds(self, username):
        key = self._key(username)
        if self._db_enabled():
            record = self._db_record(key) or {}
            locked_until = record.get("locked_until")
            if not locked_until:
                return 0
            return max(0, int((locked_until - datetime.now()).total_seconds()))
        record = self._state.get(key) or {}
        return max(0, int(record.get("locked_until", 0) - time.time()))

    def record_failure(self, username):
        key = self._key(username)
        if self._db_enabled():
            # Use atomic increment via ON CONFLICT to avoid losing counts under
            # concurrent login attempts. Lock until timestamp is computed from
            # the post-increment value using a CASE expression.
            self.execute_db(
                """
                INSERT INTO login_attempts (username, failures, locked_until, updated_at)
                VALUES (%s, 1, NULL, NOW())
                ON CONFLICT (username) DO UPDATE
                SET failures=login_attempts.failures + 1,
                    locked_until=CASE
                        WHEN login_attempts.failures + 1 >= %s
                        THEN NOW() + (%s || ' seconds')::INTERVAL
                        ELSE NULL
                    END,
                    updated_at=NOW()
                """,
                (key, self.max_failures, str(self.lockout_seconds)),
            )
            return
        record = self._state.setdefault(key, {"failures": 0, "locked_until": 0})
        record["failures"] += 1
        if record["failures"] >= self.max_failures:
            record["locked_until"] = time.time() + self.lockout_seconds

    def record_success(self, username):
        key = self._key(username)
        if self._db_enabled():
            self.execute_db("DELETE FROM login_attempts WHERE username=%s", (key,))
            return
        self._state.pop(key, None)
