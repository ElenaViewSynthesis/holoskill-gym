from __future__ import annotations

import argparse
import json

from holoskill_gym.configuration import load_project_environment, project_root
from holoskill_gym.preflight import _runtime_preflight


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
