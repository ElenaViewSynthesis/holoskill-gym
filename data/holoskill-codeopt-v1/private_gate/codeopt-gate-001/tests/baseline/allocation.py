from __future__ import annotations


def build_buffer(chunks: list[str]) -> str:
    """Concatenate chunks in order."""

    parts: list[str] = []
    for chunk in chunks:
        parts = parts + [chunk]
    return "".join(parts)
