from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Hashable


class LRUCache:
    def __init__(self, maxsize: int = 256, ttl: float = 300.0) -> None:
        self._maxsize = maxsize
        self._ttl = ttl
        self._store: OrderedDict[Hashable, tuple[Any, float]] = OrderedDict()

    def get(self, key: Hashable) -> Any | None:
        item = self._store.get(key)
        if item is None:
            return None
        value, expires_at = item
        if expires_at < time.monotonic():
            self._store.pop(key, None)
            return None
        self._store.move_to_end(key)
        return value

    def set(self, key: Hashable, value: Any) -> None:
        expires_at = time.monotonic() + self._ttl
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (value, expires_at)
        while len(self._store) > self._maxsize:
            self._store.popitem(last=False)

    def invalidate(self, key: Hashable) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()
