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

from .trajectory import NormalizationContext, normalize_trajectory_records

EXECUTOR_TO_HARBOR_AGENT = {
    "codex_exec": "codex",
    "claude_code_exec": "claude-code",
}
_OPTIMIZER_ONLY_ENV = {"HAI_API_KEY", "HOLO_BASE_URL", "HOLO_OPTIMIZER_MODEL"}


@dataclass
class CliCodeOptRolloutAgent(HarborRolloutAgent):
    """Select a built-in Harbor agent while reusing its isolation and execution."""

    executor: str = "codex_exec"
    target_model: str | None = None

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
        executor = str(config.get("executor", "codex_exec"))
        try:
            harbor_agent = EXECUTOR_TO_HARBOR_AGENT[executor]
        except KeyError as exc:
            supported = ", ".join(sorted(EXECUTOR_TO_HARBOR_AGENT))
            raise ValueError(
                f"unsupported executor {executor!r}; expected one of {supported}"
            ) from exc
        delegated_config = dict(config)
        delegated_config["agent"] = harbor_agent
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
        return cls(
            agent_id=delegated.agent_id,
            agent_import_path=delegated.agent_import_path,
            agent_kwargs=delegated.agent_kwargs,
            agent_env=delegated.agent_env,
            n_attempts=delegated.n_attempts,
            attempt_modes=delegated.attempt_modes,
            executor=executor,
            target_model=target_model,
        )

    def initialize(self, run_dir: Path):
        state = super().initialize(run_dir)
        state.metadata.update(
            {
                "executor": self.executor,
                "execution_owner": "Harbor",
                "skill_injection": "prompt_template_path",
                "target_model": self.target_model,
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
