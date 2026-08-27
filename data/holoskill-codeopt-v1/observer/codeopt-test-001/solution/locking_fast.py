from __future__ import annotations

import threading


class Registry:
    """Key/value registry read far more often than it is written."""

    def __init__(self, data: dict[str, int]) -> None:
        self._data = dict(data)
        self._lock = threading.Lock()

    def read_many(self, keys: list[str]) -> list[int]:
        # One acquisition per call instead of one per key.
        with self._lock:
            snapshot = self._data
        return [snapshot.get(key, -1) for key in keys]

    def write(self, key: str, value: int) -> None:
        with self._lock:
            updated = dict(self._data)
            updated[key] = value
            self._data = updated
