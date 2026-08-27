from __future__ import annotations

import threading


class Registry:
    """Key/value registry read far more often than it is written."""

    def __init__(self, data: dict[str, int]) -> None:
        self._data = dict(data)
        self._lock = threading.Lock()

    def read_many(self, keys: list[str]) -> list[int]:
        values: list[int] = []
        for key in keys:
            with self._lock:
                values.append(self._data.get(key, -1))
        return values

    def write(self, key: str, value: int) -> None:
        with self._lock:
            self._data[key] = value
