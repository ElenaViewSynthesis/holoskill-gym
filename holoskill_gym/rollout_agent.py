"""Thin SEAGym-to-Harbor binding for Codex CLI and Claude Code rollouts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from seagym.baselines import BaselineState, TrajectoryBatch
from seagym.baselines.data import TaskBatch
from seagym.data.types import TaskIndex
from seagym.envs.base import TaskEnv
from seagym.rollout_agents.harbor import HarborRolloutAgent

from .configuration import load_project_environment, require_credential
from .trajectory import NormalizationContext, normalize_trajectory_records

EXECUTOR_TO_HARBOR_AGENT = {
    "codex_exec": "codex",
    "claude_code_exec": "claude-code",
}
_OPTIMIZER_ONLY_ENV = {"HAI_API_KEY", "HOLO_BASE_URL", "HOLO_OPTIMIZER_MODEL"}
_COMMON_CONFIG_KEYS = {
    "executor",
    "model_ref",
    "n_attempts",
    "attempt_modes",
    "kwargs",
    "env_file",
    "reasoning_effort",
    "version",
}
_EXECUTOR_CONTROL_KEYS = {
    "codex_exec": {"reasoning_effort", "reasoning_summary", "version"},
    "claude_code_exec": {
        "allowed_tools",
        "append_system_prompt",
        "disallowed_tools",
        "fallback_model",
        "max_budget_usd",
        "max_thinking_tokens",
        "max_turns",
        "memory_dir",
        "permission_mode",
        "reasoning_effort",
        "thinking",
        "thinking_display",
        "version",
    },
}


@dataclass
class CliCodeOptRolloutAgent(HarborRolloutAgent):
    """Select a built-in Harbor agent while reusing its isolation and execution."""

    executor: str = "codex_exec"
    target_model: str | None = None
    executor_controls: dict[str, Any] | None = None

    @classmethod
    def from_config(
        cls,
        *,
        name: str,
        config: dict[str, Any],
        models: dict[str, Any],
        run_dir: Path,
        base_dir: Path | None,
    ) -> CliCodeOptRolloutAgent:
        load_project_environment(config.get("env_file"))
        executor = str(config.get("executor", "codex_exec"))
        try:
            harbor_agent = EXECUTOR_TO_HARBOR_AGENT[executor]
        except KeyError as exc:
            supported = ", ".join(sorted(EXECUTOR_TO_HARBOR_AGENT))
            raise ValueError(
                f"unsupported executor {executor!r}; expected one of {supported}"
            ) from exc
        allowed_keys = _COMMON_CONFIG_KEYS | _EXECUTOR_CONTROL_KEYS[executor]
        unknown = sorted(set(config) - allowed_keys)
        if unknown:
            raise ValueError(
                f"unsupported {executor} rollout config keys: {unknown}; "
                f"supported keys are {sorted(allowed_keys)}"
            )

        raw_kwargs = config.get("kwargs") or {}
        if not isinstance(raw_kwargs, dict):
            raise TypeError("rollout_agent.config.kwargs must be an object")
        unsupported_kwargs = sorted(set(raw_kwargs) - _EXECUTOR_CONTROL_KEYS[executor])
        if unsupported_kwargs:
            raise ValueError(
                f"unsupported {executor} Harbor agent kwargs: {unsupported_kwargs}"
            )
        executor_controls = dict(raw_kwargs)
        for key in _EXECUTOR_CONTROL_KEYS[executor]:
            if key in config:
                if key in executor_controls and executor_controls[key] != config[key]:
                    raise ValueError(f"conflicting {key!r} values in config and kwargs")
                executor_controls[key] = config[key]
        _validate_executor_controls(executor, executor_controls)

        delegated_config = dict(config)
        delegated_config["agent"] = harbor_agent
        delegated_config["kwargs"] = executor_controls
        delegated = HarborRolloutAgent.from_config(
            name=name,
            config=delegated_config,
            models=models,
            run_dir=run_dir,
            base_dir=base_dir,
        )
        leaked = _OPTIMIZER_ONLY_ENV & delegated.agent_env.keys()
        if leaked:
            raise ValueError(
                "optimizer-only environment variables cannot be exported to target rollouts: "
                + ", ".join(sorted(leaked))
            )
        model_ref = str(config.get("model_ref", "rollout_model"))
        model_config = models.get(model_ref)
        target_model = None
        if isinstance(model_config, dict) and model_config.get("model"):
            target_model = str(model_config["model"])
            _validate_executor_model(executor, target_model)
            credential_variable = model_config.get("api_key_env")
            if credential_variable:
                require_credential(str(credential_variable), role=f"{executor} target")
        return cls(
            agent_id=delegated.agent_id,
            agent_import_path=delegated.agent_import_path,
            agent_kwargs=delegated.agent_kwargs,
            agent_env=delegated.agent_env,
            n_attempts=delegated.n_attempts,
            attempt_modes=delegated.attempt_modes,
            executor=executor,
            target_model=target_model,
            executor_controls=executor_controls,
        )

    def initialize(self, run_dir: Path):
        state = super().initialize(run_dir)
        state.metadata.update(
            {
                "executor": self.executor,
                "execution_owner": "Harbor",
                "skill_injection": "prompt_template_path",
                "target_model": self.target_model,
                "executor_controls": dict(self.executor_controls or {}),
            }
        )
        return state

    def rollout(
        self,
        batch: TaskBatch,
        *,
        env: TaskEnv,
        task_index: TaskIndex,
        baseline_state: BaselineState,
    ) -> TrajectoryBatch:
        """Attach the normalized contract before SEAGym persists or reflects on it."""

        trajectories = super().rollout(
            batch,
            env=env,
            task_index=task_index,
            baseline_state=baseline_state,
        )
        context = NormalizationContext.from_metadata(
            baseline_state.metadata,
            batch_metadata=batch.metadata,
            executor=self.executor,
            model=self.target_model,
            executor_controls=self.executor_controls,
        )
        normalized = normalize_trajectory_records(
            [trajectory.to_dict() for trajectory in trajectories.trajectories],
            context=context,
        )
        enriched = []
        for trajectory, evidence in zip(
            trajectories.trajectories,
            normalized,
            strict=True,
        ):
            refs = dict(trajectory.refs)
            extra = dict(refs.get("extra") or {})
            project = dict(extra.get("holoskill_gym") or {})
            project["normalized_evidence"] = evidence.model_dump(mode="json")
            extra["holoskill_gym"] = project
            refs["extra"] = extra
            task_result = (
                None
                if trajectory.task_result is None
                else replace(trajectory.task_result, refs=refs)
            )
            enriched.append(replace(trajectory, refs=refs, task_result=task_result))
        return replace(trajectories, trajectories=enriched)


def _validate_executor_model(executor: str, model: str) -> None:
    lowered = model.lower()
    if executor == "codex_exec" and ("claude" in lowered or lowered.startswith("anthropic/")):
        raise ValueError(f"model {model!r} is incompatible with Codex")
    if executor == "claude_code_exec" and not (
        "claude" in lowered or lowered.startswith("anthropic/")
    ):
        raise ValueError(f"model {model!r} is incompatible with Claude Code")


def _validate_executor_controls(executor: str, controls: dict[str, Any]) -> None:
    effort = controls.get("reasoning_effort")
    if effort is not None and str(effort) not in {"low", "medium", "high", "xhigh", "max"}:
        raise ValueError("reasoning_effort must be low, medium, high, xhigh, or max")
    for key in ("max_turns", "max_thinking_tokens"):
        if key in controls and int(controls[key]) <= 0:
            raise ValueError(f"{key} must be positive")
    if (
        executor == "codex_exec"
        and "reasoning_summary" in controls
        and controls["reasoning_summary"] not in {"auto", "concise", "detailed", "none"}
    ):
        raise ValueError("reasoning_summary must be auto, concise, detailed, or none")
