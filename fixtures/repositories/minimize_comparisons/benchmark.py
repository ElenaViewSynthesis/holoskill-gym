from __future__ import annotations

from src.workload import deduplicate


class TrackedValue:
    comparisons = 0

    def __init__(self, value: int) -> None:
        self.value = value

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        type(self).comparisons += 1
        return isinstance(other, TrackedValue) and self.value == other.value


values = [TrackedValue(value) for value in range(80)] * 3
deduplicate(values)
print(max(1, TrackedValue.comparisons))
