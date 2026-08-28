from pathlib import Path

import pytest
from seagym.baselines import BaselineState, TaskBatch
from seagym.data.types import TaskIndex
from seagym.envs import TaskRunResult

from holoskill_gym.rollout_agent import CliCodeOptRolloutAgent


@pytest.mark.parametrize(
    ("executor", "agent_id"),
    [("codex_exec", "codex"), ("claude_code_exec", "claude-code")],
)
def test_executor_maps_to_harbor_builtin(tmp_path, executor, agent_id) -> None:
    agent = CliCodeOptRolloutAgent.from_config(
        name="codeopt",
        config={"executor": executor, "n_attempts": 2},
        models={},
        run_dir=tmp_path,
        base_dir=tmp_path,
    )

    assert agent.agent_id == agent_id
    assert agent.agent_import_path is None
    assert agent.n_attempts == 2


def test_checkpointed_skill_is_injected_as_harbor_prompt_template(tmp_path) -> None:
    skill = tmp_path / "best_skill.md"
    skill.write_text("# Skill\n\nMeasure before optimizing.\n", encoding="utf-8")
    agent = CliCodeOptRolloutAgent.from_config(
        name="codeopt",
        config={"executor": "codex_exec"},
        models={},
        run_dir=tmp_path,
        base_dir=tmp_path,
    )

    spec = agent.harbor_agent_spec(BaselineState(tmp_path, {"prompt_template_path": str(skill)}))
    rendered = Path(spec.kwargs["prompt_template_path"])

    assert spec.agent_id == "codex"
    assert rendered != skill
    assert "Measure before optimizing." in rendered.read_text()
    assert "{{ instruction }}" in rendered.read_text()
    assert "{{ instruction }}" not in skill.read_text()


def test_optimizer_credentials_cannot_leak_into_target_agent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HAI_API_KEY", "secret")
    with pytest.raises(ValueError, match="optimizer-only"):
        CliCodeOptRolloutAgent.from_config(
            name="codeopt",
            config={"executor": "codex_exec"},
            models={
                "rollout_model": {
                    "model": "gpt-5.6-sol",
                    "api_key_env": "HAI_API_KEY",
                    "exports": {"HAI_API_KEY": "{api_key}"},
                }
            },
            run_dir=tmp_path,
            base_dir=tmp_path,
        )


def test_unknown_executor_fails_closed(tmp_path) -> None:
    with pytest.raises(ValueError, match="unsupported executor"):
        CliCodeOptRolloutAgent.from_config(
            name="codeopt",
            config={"executor": "shell"},
            models={},
            run_dir=tmp_path,
            base_dir=tmp_path,
        )


def test_unknown_config_and_agent_kwargs_fail_closed(tmp_path) -> None:
    with pytest.raises(ValueError, match="rollout config keys"):
        CliCodeOptRolloutAgent.from_config(
            name="codeopt",
            config={"executor": "codex_exec", "reasoning_efort": "high"},
            models={},
            run_dir=tmp_path,
            base_dir=tmp_path,
        )
    with pytest.raises(ValueError, match="Harbor agent kwargs"):
        CliCodeOptRolloutAgent.from_config(
            name="codeopt",
            config={"executor": "codex_exec", "kwargs": {"max_turns": 3}},
            models={},
            run_dir=tmp_path,
            base_dir=tmp_path,
        )


def test_executor_model_and_credential_are_validated(tmp_path, monkeypatch) -> None:
    missing_env = tmp_path / "missing.env"
    monkeypatch.delenv("CODEOPT_TEST_KEY", raising=False)
    with pytest.raises(ValueError, match="missing codex_exec target credential"):
        CliCodeOptRolloutAgent.from_config(
            name="codeopt",
            config={"executor": "codex_exec", "env_file": str(missing_env)},
            models={
                "rollout_model": {
                    "model": "gpt-test",
                    "api_key_env": "CODEOPT_TEST_KEY",
                }
            },
            run_dir=tmp_path,
            base_dir=tmp_path,
        )
    with pytest.raises(ValueError, match="incompatible with Codex"):
        CliCodeOptRolloutAgent.from_config(
            name="codeopt",
            config={"executor": "codex_exec", "env_file": str(missing_env)},
            models={"rollout_model": {"model": "anthropic/claude-sonnet"}},
            run_dir=tmp_path,
            base_dir=tmp_path,
        )


def test_reasoning_controls_are_mapped_and_recorded(tmp_path) -> None:
    agent = CliCodeOptRolloutAgent.from_config(
        name="codeopt",
        config={
            "executor": "codex_exec",
            "reasoning_effort": "medium",
            "reasoning_summary": "concise",
        },
        models={"rollout_model": {"model": "gpt-test"}},
        run_dir=tmp_path,
        base_dir=tmp_path,
    )

    assert agent.agent_kwargs == {
        "reasoning_effort": "medium",
        "reasoning_summary": "concise",
    }
    assert agent.initialize(tmp_path).metadata["executor_controls"] == agent.agent_kwargs


def test_rollout_attaches_normalized_evidence_for_reporting_and_reflection(tmp_path) -> None:
    class FakeEnvironment:
        def run_tasks(self, tasks, *, view_name, mode, agent_id):
            assert [task.task_id for task in tasks] == ["task-1"]
            assert agent_id == "codex"
            return [
                TaskRunResult(
                    task_id="task-1",
                    view_name=view_name,
                    mode=mode,
                    rewards={"reward": 1.0},
                    score=1.0,
                    success=True,
                    refs={"trial_name": "attempt-1"},
                )
            ]

    agent = CliCodeOptRolloutAgent.from_config(
        name="codeopt",
        config={"executor": "codex_exec", "reasoning_effort": "medium"},
        models={"rollout_model": {"model": "gpt-test"}},
        run_dir=tmp_path,
        base_dir=tmp_path,
    )
    task_index = TaskIndex.from_dict(
        {
            "version": "test",
            "tasks": [
                {
                    "task_id": "task-1",
                    "source": {"type": "fixture"},
                    "attributes": {},
                    "scoring": {},
                }
            ],
        }
    )
    batch = TaskBatch(task_ids=["task-1"], view_name="train", mode="train")

    result = agent.rollout(
        batch,
        env=FakeEnvironment(),
        task_index=task_index,
        baseline_state=BaselineState(tmp_path, {}),
    )

    evidence = result.trajectories[0].refs["extra"]["holoskill_gym"]["normalized_evidence"]
    assert evidence["task_id"] == "task-1"
    assert evidence["attempt_id"] == "attempt-1"
    assert evidence["executor"] == "codex_exec"
    assert evidence["model"] == "gpt-test"
    assert evidence["extra"]["holoskill_gym"]["executor_controls"] == {
        "reasoning_effort": "medium"
    }
    reported = result.to_task_results()[0]
    assert reported.refs["extra"]["holoskill_gym"]["normalized_evidence"] == evidence
