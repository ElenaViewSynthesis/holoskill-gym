"""Thin SEAGym-to-Harbor binding for Codex CLI and Claude Code rollouts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from seagym.rollout_agents.harbor import HarborRolloutAgent

EXECUTOR_TO_HARBOR_AGENT = {
    "codex_exec": "codex",
    "claude_code_exec": "claude-code",
}
_OPTIMIZER_ONLY_ENV = {"HAI_API_KEY", "HOLO_BASE_URL", "HOLO_OPTIMIZER_MODEL"}


@dataclass
class CliCodeOptRolloutAgent(HarborRolloutAgent):
    """Select a built-in Harbor agent while reusing its isolation and execution."""

    executor: str = "codex_exec"

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
        return cls(
            agent_id=delegated.agent_id,
            agent_import_path=delegated.agent_import_path,
            agent_kwargs=delegated.agent_kwargs,
            agent_env=delegated.agent_env,
            n_attempts=delegated.n_attempts,
            attempt_modes=delegated.attempt_modes,
            executor=executor,
        )

    def initialize(self, run_dir: Path):
        state = super().initialize(run_dir)
        state.metadata.update(
            {
                "executor": self.executor,
                "execution_owner": "Harbor",
                "skill_injection": "prompt_template_path",
            }
        )
        return state
