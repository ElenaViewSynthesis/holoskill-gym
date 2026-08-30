"""Resolve dependency versions from their authoritative provenance source."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname

from .configuration import project_root

HARBOR_CHECKOUT = Path("reference/seagym/reference/harbor")


def package_version(distribution: str, *, root: Path | None = None) -> str | None:
    """Return a version suitable for manifests without trusting stale Harbor metadata.

    Harbor is installed editable from the nested checkout, so its distribution
    metadata can retain the version from the last environment sync even while
    Python executes newer source. The checkout's Git description is authoritative.
    """

    if distribution == "harbor":
        checkout = (root or project_root()) / HARBOR_CHECKOUT
        if not _active_harbor_is_editable_checkout(checkout):
            return None
        return _git_describe(checkout)
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def _active_harbor_is_editable_checkout(checkout: Path) -> bool:
    """Verify both Harbor's distribution and import resolve to ``checkout``."""

    expected_checkout = checkout.resolve()
    expected_package = (expected_checkout / "src" / "harbor").resolve()
    try:
        distribution = importlib.metadata.distribution("harbor")
    except importlib.metadata.PackageNotFoundError:
        return False

    try:
        direct_url = distribution.read_text("direct_url.json")
        if direct_url is None:
            return False
        direct_url_data = json.loads(direct_url)
        installed_root = _path_from_file_url(str(direct_url_data["url"]))
        editable = direct_url_data.get("dir_info", {}).get("editable") is True
    except (AttributeError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return False
    if not editable or installed_root != expected_checkout:
        return False

    try:
        spec = importlib.util.find_spec("harbor")
    except (AttributeError, ImportError, ValueError):
        return False
    if spec is None:
        return False
    candidates = [spec.origin, *(spec.submodule_search_locations or ())]
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            Path(candidate).resolve().relative_to(expected_package)
        except (OSError, ValueError):
            continue
        return True
    return False


def _path_from_file_url(value: str) -> Path | None:
    parsed = urlsplit(value)
    if parsed.scheme != "file" or parsed.query or parsed.fragment:
        return None
    path = url2pathname(unquote(parsed.path))
    if parsed.netloc and parsed.netloc != "localhost":
        path = f"//{parsed.netloc}{path}"
    return Path(path).resolve()


def _git_describe(checkout: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(checkout), "describe", "--tags"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    version = result.stdout.strip()
    return version if result.returncode == 0 and version else None
