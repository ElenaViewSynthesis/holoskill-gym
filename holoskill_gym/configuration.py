"""Shared, fail-closed runtime configuration and credential loading."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_PLACEHOLDER_MARKERS = (
    "your-api-key",
    "your_api_key",
    "replace-me",
    "changeme",
    "placeholder",
)


def project_root() -> Path:
    """Return the checkout root containing this installed package."""

    return Path(__file__).resolve().parents[1]


def load_project_environment(env_file: str | Path | None = None) -> Path:
    """Load one project-root dotenv file without depending on the caller CWD."""

    path = Path(env_file) if env_file not in (None, "") else Path(".env")
    if not path.is_absolute():
        path = project_root() / path
    path = path.resolve()
    if path.is_file():
        load_dotenv(path, override=False)
    return path


def require_credential(variable: str, *, role: str) -> None:
    """Require a non-placeholder secret without returning or displaying it."""

    value = (os.environ.get(variable) or "").strip().strip('"').strip("'")
    if not value:
        raise ValueError(f"missing {role} credential: set {variable} in the project .env")
    lowered = value.lower()
    if any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
        raise ValueError(f"placeholder {role} credential: replace {variable} in the project .env")


def credential_status(variable: str) -> str:
    """Return a safe presence state suitable for preflight output."""

    value = (os.environ.get(variable) or "").strip().strip('"').strip("'")
    if not value:
        return "missing"
    lowered = value.lower()
    if any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
        return "placeholder"
    return "present"
