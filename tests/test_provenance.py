from __future__ import annotations

import importlib.metadata
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from holoskill_gym.provenance import _active_harbor_is_editable_checkout, package_version


def test_harbor_version_comes_from_vendored_git_tag(monkeypatch, tmp_path: Path) -> None:
    def fake_run(command, **kwargs):
        assert command == [
            "git",
            "-C",
            str(tmp_path / "reference/seagym/reference/harbor"),
            "describe",
            "--tags",
        ]
        assert kwargs == {
            "check": False,
            "capture_output": True,
            "text": True,
            "timeout": 5,
        }
        return SimpleNamespace(returncode=0, stdout="v0.22.0\n")

    monkeypatch.setattr("holoskill_gym.provenance.subprocess.run", fake_run)
    monkeypatch.setattr(
        "holoskill_gym.provenance._active_harbor_is_editable_checkout", lambda _path: True
    )
    monkeypatch.setattr(
        "holoskill_gym.provenance.importlib.metadata.version",
        lambda _distribution: (_ for _ in ()).throw(
            AssertionError("Harbor must not use stale version metadata")
        ),
    )

    assert package_version("harbor", root=tmp_path) == "v0.22.0"


def test_harbor_version_does_not_fall_back_to_stale_distribution_metadata(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "holoskill_gym.provenance._active_harbor_is_editable_checkout", lambda _path: True
    )
    monkeypatch.setattr(
        "holoskill_gym.provenance.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=128, stdout=""),
    )
    monkeypatch.setattr(
        "holoskill_gym.provenance.importlib.metadata.version",
        lambda _distribution: "0.15.0",
    )

    assert package_version("harbor", root=tmp_path) is None


def test_harbor_version_handles_git_execution_failure(monkeypatch, tmp_path: Path) -> None:
    def fail(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("git", 5)

    monkeypatch.setattr("holoskill_gym.provenance.subprocess.run", fail)
    monkeypatch.setattr(
        "holoskill_gym.provenance._active_harbor_is_editable_checkout", lambda _path: True
    )

    assert package_version("harbor", root=tmp_path) is None


def test_harbor_version_requires_active_editable_checkout(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "holoskill_gym.provenance._active_harbor_is_editable_checkout", lambda _path: False
    )
    monkeypatch.setattr(
        "holoskill_gym.provenance.subprocess.run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Git tag must not be read for an inactive checkout")
        ),
    )

    assert package_version("harbor", root=tmp_path) is None


def test_active_harbor_requires_matching_distribution_and_import(
    monkeypatch, tmp_path: Path
) -> None:
    checkout = tmp_path / "reference/seagym/reference/harbor"
    package = checkout / "src/harbor"
    direct_url = json.dumps({"url": checkout.resolve().as_uri(), "dir_info": {"editable": True}})
    distribution = SimpleNamespace(
        read_text=lambda name: direct_url if name == "direct_url.json" else None
    )
    spec = SimpleNamespace(
        origin=str(package / "__init__.py"),
        submodule_search_locations=[str(package)],
    )
    monkeypatch.setattr(
        "holoskill_gym.provenance.importlib.metadata.distribution", lambda _name: distribution
    )
    monkeypatch.setattr("holoskill_gym.provenance.importlib.util.find_spec", lambda _name: spec)

    assert _active_harbor_is_editable_checkout(checkout)

    spec.origin = str(tmp_path / "site-packages/harbor/__init__.py")
    spec.submodule_search_locations = [str(tmp_path / "site-packages/harbor")]
    assert not _active_harbor_is_editable_checkout(checkout)


def test_active_harbor_requires_matching_editable_distribution_root(
    monkeypatch, tmp_path: Path
) -> None:
    checkout = tmp_path / "reference/seagym/reference/harbor"
    other_checkout = tmp_path / "other-harbor"
    distribution = SimpleNamespace(
        read_text=lambda _name: json.dumps(
            {"url": other_checkout.resolve().as_uri(), "dir_info": {"editable": True}}
        )
    )
    monkeypatch.setattr(
        "holoskill_gym.provenance.importlib.metadata.distribution", lambda _name: distribution
    )
    monkeypatch.setattr(
        "holoskill_gym.provenance.importlib.util.find_spec",
        lambda _name: SimpleNamespace(
            origin=str(checkout / "src/harbor/__init__.py"),
            submodule_search_locations=[str(checkout / "src/harbor")],
        ),
    )

    assert not _active_harbor_is_editable_checkout(checkout)


def test_active_harbor_requires_installed_distribution(monkeypatch, tmp_path: Path) -> None:
    def missing(_name: str):
        raise importlib.metadata.PackageNotFoundError("harbor")

    monkeypatch.setattr("holoskill_gym.provenance.importlib.metadata.distribution", missing)

    assert not _active_harbor_is_editable_checkout(tmp_path)


def test_other_package_versions_still_use_distribution_metadata(monkeypatch) -> None:
    monkeypatch.setattr(
        "holoskill_gym.provenance.importlib.metadata.version",
        lambda distribution: f"metadata:{distribution}",
    )

    assert package_version("seagym") == "metadata:seagym"
