from __future__ import annotations

import argparse
import asyncio
import json
import sys
from types import SimpleNamespace

import pytest

from holoskill_gym.configuration import load_project_environment, project_root
from holoskill_gym.preflight import (
    DAYTONA_ALLOWLIST_FIX,
    _daytona_api_url_status,
    _daytona_auth_ready,
    _harbor_has_daytona_allowlist_fix,
    _probe_daytona_control_plane,
    _runtime_preflight,
)


def test_default_env_contract_is_rooted_at_project(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)

    assert load_project_environment() == (project_root() / ".env").resolve()


def test_runtime_preflight_reports_presence_without_secret_values(
    monkeypatch, tmp_path, capsys
) -> None:
    secret = "codex-secret-for-test"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    monkeypatch.setattr(
        "holoskill_gym.preflight._docker_status",
        lambda: {"status": "ready", "server_version": "test"},
    )
    monkeypatch.setattr("holoskill_gym.preflight._installed_version", lambda _name: "test")
    args = argparse.Namespace(
        env_file=str(tmp_path / "absent.env"),
        condition="codex-static",
        json=True,
    )

    assert _runtime_preflight(args) == 0
    output = capsys.readouterr().out
    manifest = json.loads(output)
    assert manifest["credentials"] == {"OPENAI_API_KEY": "present"}
    assert secret not in output


def test_runtime_preflight_requires_optimizer_only_for_gated_condition(
    monkeypatch, tmp_path, capsys
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "present-test-key")
    monkeypatch.delenv("HAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "holoskill_gym.preflight._docker_status",
        lambda: {"status": "ready", "server_version": "test"},
    )
    monkeypatch.setattr("holoskill_gym.preflight._installed_version", lambda _name: "test")
    args = argparse.Namespace(
        env_file=str(tmp_path / "absent.env"),
        condition="codex-gated",
        json=True,
    )

    assert _runtime_preflight(args) == 12
    manifest = json.loads(capsys.readouterr().out)
    assert manifest["failures"] == ["credential:HAI_API_KEY"]


def test_runtime_preflight_validates_daytona_without_requiring_local_docker(
    monkeypatch, tmp_path, capsys
) -> None:
    secret = "daytona-secret-for-test"
    monkeypatch.setenv("OPENAI_API_KEY", "present-test-key")
    monkeypatch.setenv("DAYTONA_API_KEY", secret)
    monkeypatch.setenv("DAYTONA_API_URL", "https://app.daytona.io/api")
    monkeypatch.delenv("DAYTONA_JWT_TOKEN", raising=False)
    monkeypatch.delenv("DAYTONA_ORGANIZATION_ID", raising=False)
    monkeypatch.setattr("holoskill_gym.preflight._installed_version", lambda _name: "test")
    monkeypatch.setattr("holoskill_gym.preflight._harbor_has_daytona_allowlist_fix", lambda: True)
    monkeypatch.setattr("holoskill_gym.preflight._daytona_control_plane_status", lambda: "ready")
    monkeypatch.setattr(
        "holoskill_gym.preflight._docker_status",
        lambda: pytest.fail("Daytona preflight must not require local Docker"),
    )
    args = argparse.Namespace(
        env_file=str(tmp_path / "absent.env"),
        condition="codex-static",
        environment="daytona",
        json=True,
    )

    assert _runtime_preflight(args) == 0
    output = capsys.readouterr().out
    manifest = json.loads(output)
    assert manifest["environment"] == "daytona"
    assert manifest["docker"]["status"] == "not-required"
    assert manifest["daytona"] == {
        "allowlist_fix": DAYTONA_ALLOWLIST_FIX,
        "allowlist_status": "supported",
        "api_url_source": "environment",
        "api_url_status": "valid",
        "connectivity": "ready",
        "status": "ready",
    }
    assert manifest["packages"]["daytona"] == "test"
    assert secret not in output


def test_runtime_preflight_rejects_invalid_daytona_url_before_connecting(
    monkeypatch, tmp_path, capsys
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "present-test-key")
    monkeypatch.setenv("DAYTONA_API_KEY", "present-test-key")
    monkeypatch.setenv("DAYTONA_API_URL", "app.daytona.io/api")
    monkeypatch.setattr("holoskill_gym.preflight._installed_version", lambda _name: "test")
    monkeypatch.setattr("holoskill_gym.preflight._harbor_has_daytona_allowlist_fix", lambda: True)
    monkeypatch.setattr(
        "holoskill_gym.preflight._daytona_control_plane_status",
        lambda: pytest.fail("an invalid URL must fail before a provider request"),
    )
    args = argparse.Namespace(
        env_file=str(tmp_path / "absent.env"),
        condition="codex-static",
        environment="daytona",
        json=True,
    )

    assert _runtime_preflight(args) == 12
    manifest = json.loads(capsys.readouterr().out)
    assert manifest["daytona"]["status"] == "invalid-api-url"
    assert manifest["daytona"]["connectivity"] == "not-checked"
    assert manifest["failures"] == ["daytona"]


def test_runtime_preflight_blocks_daytona_without_allowlist_fix(
    monkeypatch, tmp_path, capsys
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "present-test-key")
    monkeypatch.setenv("DAYTONA_API_KEY", "present-test-key")
    monkeypatch.setenv("DAYTONA_API_URL", "https://app.daytona.io/api")
    monkeypatch.setattr("holoskill_gym.preflight._installed_version", lambda _name: "test")
    monkeypatch.setattr("holoskill_gym.preflight._harbor_has_daytona_allowlist_fix", lambda: False)
    monkeypatch.setattr(
        "holoskill_gym.preflight._daytona_control_plane_status",
        lambda: pytest.fail("unsupported containment must fail before a provider request"),
    )
    args = argparse.Namespace(
        env_file=str(tmp_path / "absent.env"),
        condition="codex-static",
        environment="daytona",
        json=True,
    )

    assert _runtime_preflight(args) == 12
    manifest = json.loads(capsys.readouterr().out)
    assert manifest["daytona"]["status"] == "containment-unsupported"
    assert manifest["daytona"]["allowlist_status"] == "unsupported"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://app.daytona.io/api", "valid"),
        ("http://localhost:3000/api", "valid"),
        ("app.daytona.io/api", "invalid"),
        ("ftp://app.daytona.io/api", "invalid"),
        ("https://user:password@app.daytona.io/api", "invalid"),
        ("https://app.daytona.io/api?token=secret", "invalid"),
        ("https://app.daytona.io:99999/api", "invalid"),
    ],
)
def test_daytona_api_url_validation(url: str, expected: str) -> None:
    assert _daytona_api_url_status(url) == expected


def test_daytona_auth_accepts_api_key_or_complete_jwt_pair() -> None:
    assert _daytona_auth_ready({"DAYTONA_API_KEY": "present"})
    assert _daytona_auth_ready(
        {"DAYTONA_JWT_TOKEN": "present", "DAYTONA_ORGANIZATION_ID": "present"}
    )
    assert not _daytona_auth_ready({"DAYTONA_JWT_TOKEN": "present"})


def test_daytona_control_plane_probe_is_read_only_and_bounded(monkeypatch) -> None:
    observed: dict[str, object] = {}

    class FakeQuery:
        def __init__(self, *, limit: int) -> None:
            observed["limit"] = limit

    class FakeClient:
        def list(self, query, *, request_timeout: int):
            observed["query"] = query
            observed["request_timeout"] = request_timeout

            async def empty_sandbox_list():
                if False:
                    yield None

            return empty_sandbox_list()

        async def close(self) -> None:
            observed["closed"] = True

    monkeypatch.setitem(
        sys.modules,
        "daytona",
        SimpleNamespace(AsyncDaytona=FakeClient, ListSandboxesQuery=FakeQuery),
    )

    assert asyncio.run(_probe_daytona_control_plane()) == "ready"
    assert observed["closed"] is True
    assert observed["limit"] == 1
    assert isinstance(observed["query"], FakeQuery)
    assert observed["request_timeout"] == 10


@pytest.mark.parametrize(("returncode", "expected"), [(0, True), (1, False), (128, None)])
def test_daytona_allowlist_fix_is_verified_from_git_ancestry(
    monkeypatch, returncode: int, expected: bool | None
) -> None:
    def fake_run(command, **kwargs):
        assert command[-4:] == ["merge-base", "--is-ancestor", DAYTONA_ALLOWLIST_FIX, "HEAD"]
        assert kwargs == {"check": False, "capture_output": True, "timeout": 5}
        return SimpleNamespace(returncode=returncode)

    monkeypatch.setattr("holoskill_gym.preflight.subprocess.run", fake_run)

    assert _harbor_has_daytona_allowlist_fix() is expected
