"""Artifact-level secret checks that report paths without echoing matches."""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

_SECRET_PATTERNS = (
    re.compile(r"\bsk(?:-proj)?-[A-Za-z0-9_-]{12,}\b", re.IGNORECASE),
    re.compile(r"\bbearer\s+[A-Za-z0-9._~+/=-]{12,}\b", re.IGNORECASE),
    re.compile(r"\b(?:api[_-]?key|access[_-]?token|authorization)\s*[:=]", re.IGNORECASE),
)
_SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|access[_-]?token|authorization|bearer|secret|password|credential|cookie)",
    re.IGNORECASE,
)
_REDACTIONS = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)((?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]+\b", re.IGNORECASE),
)
_FAILURE_LOG_NAMES = {"trial.log", "stdout.txt", "stderr.txt"}
SECRET_ENV_VARS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "HAI_API_KEY",
    "OPENROUTER_API_KEY",
    "DAYTONA_API_KEY",
)


def load_known_secret_values(
    env_file: Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    variable_names: Iterable[str] = SECRET_ENV_VARS,
) -> tuple[str, ...]:
    """Load exact credential values without mutating the process environment."""

    environment = os.environ if environ is None else environ
    file_values: dict[str, str] = {}
    if env_file is not None and env_file.is_file():
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            file_values[name.strip()] = value.strip().strip('"').strip("'")

    secrets: list[str] = []
    for name in variable_names:
        value = (environment.get(name) or file_values.get(name) or "").strip()
        if len(value) >= 8 and value not in secrets:
            secrets.append(value)
    return tuple(secrets)


def scan_artifact_tree(
    root: Path,
    *,
    known_secret_values: Iterable[str] = (),
    max_file_bytes: int = 1_000_000,
) -> list[str]:
    """Return secret-bearing paths without echoing matches.

    Files are scanned incrementally, including binary and oversized files;
    ``max_file_bytes`` is the bounded chunk size rather than a skip threshold.
    """

    root = root.resolve()
    secrets = tuple(value for value in known_secret_values if len(value) >= 8)
    findings: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        if _file_contains_secret(path, secrets=secrets, chunk_bytes=max_file_bytes):
            findings.append(path.relative_to(root).as_posix())
    return findings


def redact_sensitive_text(text: str, *, known_secret_values: Iterable[str] = ()) -> str:
    """Redact common credential shapes and exact known values from text."""

    redacted = text.replace("\x00", "")
    for secret in known_secret_values:
        if len(secret) >= 8:
            redacted = redacted.replace(secret, "[REDACTED]")
    for pattern in _REDACTIONS:
        redacted = pattern.sub(
            lambda match: (match.group(1) if match.lastindex else "") + "[REDACTED]",
            redacted,
        )
    return redacted


def redact_sensitive_value(value: Any, *, key: str | None = None) -> Any:
    """Recursively redact values stored beneath sensitive mapping keys."""

    if key is not None and _SENSITIVE_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            str(item_key): redact_sensitive_value(item, key=str(item_key))
            for item_key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact_sensitive_value(item) for item in value]
    if isinstance(value, str):
        return redact_sensitive_text(value)
    return value


def sanitize_failure_logs(
    source: Path,
    destination: Path,
    *,
    max_log_bytes: int = 256_000,
    known_secret_values: Iterable[str] = (),
) -> list[str]:
    """Copy only bounded diagnostic logs after redacting credential material."""

    source = source.resolve()
    destination = destination.resolve()
    written: list[str] = []
    if not source.is_dir():
        return written
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.is_symlink() or path.name not in _FAILURE_LOG_NAMES:
            continue
        raw = path.read_bytes()
        if len(raw) > max_log_bytes:
            raw = raw[-max_log_bytes:]
        text = raw.decode("utf-8", errors="replace")
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            redact_sensitive_text(text, known_secret_values=known_secret_values),
            encoding="utf-8",
        )
        written.append(relative.as_posix())
    return written


def _file_contains_secret(path: Path, *, secrets: tuple[str, ...], chunk_bytes: int) -> bool:
    if chunk_bytes <= 0:
        raise ValueError("max_file_bytes must be positive")
    overlap = ""
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_bytes):
            text = overlap + chunk.decode("utf-8", errors="ignore")
            if any(secret in text for secret in secrets) or any(
                pattern.search(text) for pattern in _SECRET_PATTERNS
            ):
                return True
            overlap = text[-512:]
    return False
