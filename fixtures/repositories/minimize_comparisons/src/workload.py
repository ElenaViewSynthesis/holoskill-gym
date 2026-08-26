from __future__ import annotations

from collections.abc import Iterable


def deduplicate[T](values: Iterable[T]) -> list[T]:
    """Return first occurrences in input order."""

    result: list[T] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
