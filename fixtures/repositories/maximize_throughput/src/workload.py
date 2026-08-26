from __future__ import annotations

from collections.abc import Iterable


def count_matches[T](values: Iterable[T], accepted: Iterable[T]) -> int:
    """Count values present in the accepted collection."""

    accepted_values = list(accepted)
    return sum(1 for value in values if value in accepted_values)
