from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "holoskill-codeopt-v1"
TASKS = sorted(DATA.glob("*/*/task.toml"))


def test_all_canary_images_install_git_before_initializing_repository() -> None:
    assert len(TASKS) == 5
    for task_toml in TASKS:
        dockerfile = task_toml.parent / "environment" / "Dockerfile"
        text = dockerfile.read_text(encoding="utf-8")
        assert "apt-get install -y --no-install-recommends git" in text
        assert text.index("apt-get install") < text.index("git init")


def test_all_canary_tasks_use_phase_specific_network_policy() -> None:
    for task_toml in TASKS:
        config = tomllib.loads(task_toml.read_text(encoding="utf-8"))
        assert config["metadata"]["benchmark_trust"] == "synthetic_canary"
        assert config["environment"]["network_mode"] == "allowlist"
        assert "github.com" in config["environment"]["allowed_hosts"]
        assert "registry.npmjs.org" in config["environment"]["allowed_hosts"]
        assert config["agent"]["network_mode"] == "allowlist"
        assert "api.openai.com" in config["agent"]["allowed_hosts"]
        assert config["verifier"]["network_mode"] == "no-network"


def test_runtime_shell_scripts_are_lf_only() -> None:
    for script in DATA.rglob("*.sh"):
        assert b"\r\n" not in script.read_bytes(), script


def test_task_verifiers_match_shared_template() -> None:
    subprocess.run(
        [str(ROOT / "scripts" / "render-harbor-task-verifiers"), "--check"],
        cwd=ROOT,
        check=True,
    )
