"""Lightweight TTL in-memory cache for read-only report metrics.

This cache is designed for short-lived (default 30s) caching of report queries
that are expensive but tolerate slight staleness, such as module report center
metrics summaries. It is NOT a general-purpose cache:
  - Process-local (not shared across workers).
  - No external dependency.
  - Thread-safe via a single threading.Lock.
  - Entries expire lazily on read.

Usage:
    from services.report_cache import report_cache

    rows = report_cache.get_or_fetch(
        key="inventory_metrics_ledger",
        fetch_fn=lambda: query_rows(sql, params),
        ttl_seconds=30,
    )
"""
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_DEFAULT_TTL = 30
_MAX_ENTRIES = 200


class _CacheEntry:
    __slots__ = ("value", "expires_at")

    def __init__(self, value: Any, expires_at: float):
        self.value = value
        self.expires_at = expires_at


class TTLCache:
    """Thread-safe TTL cache with a max-entries cap (LRU-ish eviction)."""

    def __init__(self, max_entries: int = _MAX_ENTRIES):
        self._store: Dict[str, _CacheEntry] = {}
        self._lock = threading.Lock()
        self._max_entries = max_entries
        # Stats
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, key: str) -> Optional[Any]:
        """Return cached value if present and not expired, else None."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            if entry.expires_at <= time.monotonic():
                # Expired: remove and count as miss
                del self._store[key]
                self._misses += 1
                return None
            self._hits += 1
            return entry.value

    def set(self, key: str, value: Any, ttl_seconds: int = _DEFAULT_TTL) -> None:
        """Store a value with the given TTL."""
        expires_at = time.monotonic() + max(int(ttl_seconds), 0)
        with self._lock:
            # Evict oldest entries if at capacity
            while len(self._store) >= self._max_entries:
                # Remove the entry with the earliest expiry (approximate LRU)
                oldest_key = min(self._store, key=lambda k: self._store[k].expires_at)
                del self._store[oldest_key]
                self._evictions += 1
            self._store[key] = _CacheEntry(value, expires_at)

    def get_or_fetch(
        self,
        key: str,
        fetch_fn: Callable[[], Any],
        ttl_seconds: int = _DEFAULT_TTL,
    ) -> Any:
        """Return cached value if fresh; otherwise call fetch_fn, cache, and return."""
        cached = self.get(key)
        if cached is not None:
            return cached
        value = fetch_fn()
        self.set(key, value, ttl_seconds=ttl_seconds)
        return value

    def invalidate(self, key: str) -> None:
        """Remove a specific key from the cache."""
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        """Remove all entries from the cache."""
        with self._lock:
            self._store.clear()

    def stats(self) -> Dict[str, int]:
        """Return cache statistics: hits, misses, evictions, current size."""
        with self._lock:
            return {
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "size": len(self._store),
                "max_entries": self._max_entries,
            }


# Singleton instance for application-wide use
report_cache = TTLCache()
