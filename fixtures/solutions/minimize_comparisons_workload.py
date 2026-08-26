from __future__ import annotations

from collections.abc import Iterable


def deduplicate[T](values: Iterable[T]) -> list[T]:
    """Return first occurrences in input order."""

    return list(dict.fromkeys(values))
