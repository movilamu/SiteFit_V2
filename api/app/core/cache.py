"""A very small time-to-live cache.

Several API responses are read-only views of a published data release:
the candidate-site inventory, the data-quality report, the set of
scorability criteria.  Reading them from the database on every request
costs a round trip to a remote database for every page load, and the
values change only when a new release is published.

The cache therefore holds a value for a short, explicitly configured
period.  It is deliberately not a general-purpose cache: there is one
entry per key, the value is replaced wholesale, and nothing is written
back to the database.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Optional


class TTLCache:
    """Hold one value per key for a fixed number of seconds."""

    def __init__(self, ttl_seconds: float) -> None:
        self.ttl_seconds = float(ttl_seconds)
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        """Return the cached value, or ``None`` when it has expired."""

        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            stored_at, value = entry
            if (time.monotonic() - stored_at) > self.ttl_seconds:
                self._entries.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any) -> Any:
        """Store a value and return it."""

        with self._lock:
            self._entries[key] = (time.monotonic(), value)
        return value

    def get_or_set(self, key: str, factory: Callable[[], Any]) -> Any:
        """Return the cached value, or compute, store and return it."""

        cached = self.get(key)
        if cached is not None:
            return cached
        return self.set(key, factory())

    def invalidate(self, key: Optional[str] = None) -> None:
        """Drop one entry, or every entry when no key is given."""

        with self._lock:
            if key is None:
                self._entries.clear()
            else:
                self._entries.pop(key, None)

    def __len__(self) -> int:  # pragma: no cover - diagnostic only
        with self._lock:
            return len(self._entries)


__all__ = ["TTLCache"]

