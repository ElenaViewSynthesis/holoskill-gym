from __future__ import annotations


def _score_chunk(chunk: list[str]) -> list[int]:
    return [len(item) * 7 + sum(ord(c) % 5 for c in item) for item in chunk]


def score_all(items: list[str]) -> list[int]:
    """Score every item, preserving input order."""

    scores: list[int] = []
    for item in items:
        scores.extend(_score_chunk([item]))
    return scores
