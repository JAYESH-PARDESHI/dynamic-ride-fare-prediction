"""A tiny in-memory TTL cache (enough for weather, route and geocoding lookups)."""
import time
from typing import Generic, Hashable, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    def __init__(self, ttl_seconds: float | None, max_entries: int | None = None):
        """ttl_seconds=None means entries never expire.

        max_entries (optional) bounds memory: when full, the oldest entry is dropped.
        Use it for caches keyed by user input (e.g. search text).
        """
        self._ttl = ttl_seconds
        self._max = max_entries
        self._data: dict[Hashable, tuple[float, T]] = {}

    def get(self, key: Hashable) -> T | None:
        item = self._data.get(key)
        if item is None:
            return None
        stored_at, value = item
        if self._ttl is not None and time.monotonic() - stored_at > self._ttl:
            del self._data[key]
            return None
        return value

    def set(self, key: Hashable, value: T) -> None:
        if self._max is not None and key not in self._data and len(self._data) >= self._max:
            self._data.pop(next(iter(self._data)))  # dicts keep insertion order -> oldest first
        self._data[key] = (time.monotonic(), value)
