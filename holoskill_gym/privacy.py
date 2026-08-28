"""Artifact-level secret checks that report paths without echoing matches."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

_SECRET_PATTERNS = (
    re.compile(r"\bsk(?:-proj)?-[A-Za-z0-9_-]{12,}\b", re.IGNORECASE),
    re.compile(r"\bbearer\s+[A-Za-z0-9._~+/=-]{12,}\b", re.IGNORECASE),
    re.compile(r"\b(?:api[_-]?key|access[_-]?token|authorization)\s*[:=]", re.IGNORECASE),
)


def scan_artifact_tree(
    root: Path,
    *,
    known_secret_values: Iterable[str] = (),
    max_file_bytes: int = 8_000_000,
) -> list[str]:
    """Return relative paths containing secret-shaped text, never matched values."""

    root = root.resolve()
    secrets = tuple(value for value in known_secret_values if len(value) >= 8)
    findings: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink() or path.stat().st_size > max_file_bytes:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(secret in text for secret in secrets) or any(
            pattern.search(text) for pattern in _SECRET_PATTERNS
        ):
            findings.append(path.relative_to(root).as_posix())
    return findings
