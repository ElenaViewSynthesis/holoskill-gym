"""Thin SEAGym-to-Harbor binding for Codex CLI and Claude Code rollouts.

This agent executes nothing itself. Harbor owns checkout, sandboxing, CLI
invocation and timeouts; this class only chooses which built-in Harbor agent
runs and constrains how it is allowed to run.

Two distinct control layers arrive through ``rollout_agent.config``:

``_EXECUTOR_CONTROL_KEYS`` -- executor controls
    Forwarded to the Harbor built-in agent as ``kwargs``. They shape the model's
    own behaviour (reasoning effort, tool allowlists, thinking budget) and differ
    per executor, because Codex and Claude Code expose different knobs.

``_EXECUTION_CONFIG_KEYS`` -- execution controls
    Never forwarded to the agent. They are applied to the SEAGym ``TaskEnv`` or
    asserted against the task package before the rollout starts, and they govern
    the sandbox rather than the model: phase timeouts, step budget, per-phase
    network policy, and raw-log retention.

The split matters because the second layer is the containment boundary. A wrong
executor control costs tokens; a wrong execution control lets an agent reach the
network during grading, or lets raw provider logs land in a run directory. Every
execution control is therefore validated at configuration time and re-checked
against the task package at rollout time.

See ``_validate_task_network_policy`` for the Harbor network policies this
binding refuses to run.
"""

from __future__ import annotations

import tomllib
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
# Optimizer credentials must never reach a target rollout. SkillOpt drives the
# optimizer on the host; the target agent runs in Harbor's sandbox and is given
# only its own provider key. Leakage here would let the target read or bill the
# optimizer role, so ``from_config`` treats any overlap as fatal.
_OPTIMIZER_ONLY_ENV = {"HAI_API_KEY", "HOLO_BASE_URL", "HOLO_OPTIMIZER_MODEL"}

# Keys accepted by every executor. Anything outside the union of this set and the
# selected executor's control keys is rejected, so a typo cannot silently become
# a no-op setting.
_COMMON_CONFIG_KEYS = {
    "executor",
    "model_ref",
    "n_attempts",
    "attempt_modes",
    "kwargs",
    "env_file",
    "reasoning_effort",
    "version",
    "agent_timeout_seconds",
    "verifier_timeout_seconds",
    "max_steps",
    "agent_network_mode",
    "verifier_network_mode",
    "raw_log_retention",
}
# Execution controls: enforced against the environment or the task package, not
# passed to the model. These are the sandbox knobs, and the reason this binding
# exists rather than using ``HarborRolloutAgent`` directly.
_EXECUTION_CONFIG_KEYS = {
    "agent_timeout_seconds",
    "verifier_timeout_seconds",
    "max_steps",
    "agent_network_mode",
    "verifier_network_mode",
    "raw_log_retention",
}
# Executor controls: forwarded verbatim to the Harbor built-in agent as kwargs.
# The sets are deliberately asymmetric -- Codex exposes reasoning knobs only,
# while Claude Code additionally accepts tool policy, budget and turn limits.
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
    """Select a built-in Harbor agent while reusing its isolation and execution.

    Attributes:
        executor: Logical executor name (``codex_exec`` or ``claude_code_exec``),
            mapped to a Harbor built-in agent by ``EXECUTOR_TO_HARBOR_AGENT``.
        target_model: Resolved target model id, recorded on the trajectory so a
            run manifest attributes spend to the target rather than the optimizer.
            ``None`` when the config names no model.
        executor_controls: Kwargs handed to the Harbor agent. Model-facing.
        execution_controls: Sandbox constraints applied to the ``TaskEnv`` or
            asserted against ``task.toml``. Never handed to the agent.
    """

    executor: str = "codex_exec"
    target_model: str | None = None
    executor_controls: dict[str, Any] | None = None
    execution_controls: dict[str, Any] | None = None

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
        """Validate the rollout config and bind it to a built-in Harbor agent.

        Every check here runs before a container starts, so a misconfigured run
        fails at load time rather than after spending tokens.

        Args:
            name: Rollout agent name from the experiment config, used as the
                Harbor ``agent_id`` fallback.
            config: The ``rollout_agent.config`` block. Split into executor
                controls and execution controls; unknown keys are rejected.
            models: The ``rollout_agent.models`` block. ``model_ref`` selects the
                entry supplying the target model, its endpoint and its
                credential variable.
            run_dir: Run directory, forwarded to the delegate unchanged.
            base_dir: Config-relative base directory, forwarded unchanged.

        Returns:
            A configured agent carrying both control layers.

        Raises:
            ValueError: Unsupported executor, unknown config key, conflicting
                ``max_steps``/``max_turns``, out-of-range control value,
                executor/model mismatch, or an optimizer-only environment
                variable exported to the target.
            TypeError: ``kwargs`` is not an object.
        """

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

        execution_controls = {key: config[key] for key in _EXECUTION_CONFIG_KEYS if key in config}
        _validate_execution_controls(executor, execution_controls)

        raw_kwargs = config.get("kwargs") or {}
        if not isinstance(raw_kwargs, dict):
            raise TypeError("rollout_agent.config.kwargs must be an object")
        unsupported_kwargs = sorted(set(raw_kwargs) - _EXECUTOR_CONTROL_KEYS[executor])
        if unsupported_kwargs:
            raise ValueError(f"unsupported {executor} Harbor agent kwargs: {unsupported_kwargs}")
        executor_controls = dict(raw_kwargs)
        for key in _EXECUTOR_CONTROL_KEYS[executor]:
            if key in config:
                if key in executor_controls and executor_controls[key] != config[key]:
                    raise ValueError(f"conflicting {key!r} values in config and kwargs")
                executor_controls[key] = config[key]
        # ``max_steps`` is this project's executor-neutral name for the agent step
        # budget; Claude Code's Harbor agent spells the same limit ``max_turns``.
        # Bridge the two so configs stay portable across executors, and refuse a
        # config that sets both to different values rather than silently picking
        # a winner. ``_validate_execution_controls`` has already rejected
        # ``max_steps`` for Codex, which has no equivalent knob at this pin.
        if "max_steps" in execution_controls:
            if "max_turns" in executor_controls and int(executor_controls["max_turns"]) != int(
                execution_controls["max_steps"]
            ):
                raise ValueError("conflicting max_steps and max_turns values")
            executor_controls["max_turns"] = execution_controls["max_steps"]
        _validate_executor_controls(executor, executor_controls)

        n_attempts = int(config.get("n_attempts", 1))
        if n_attempts <= 0:
            raise ValueError("n_attempts must be positive")
        attempt_modes = config.get("attempt_modes", ["train"])
        if isinstance(attempt_modes, str):
            attempt_modes = [attempt_modes]
        if (
            not isinstance(attempt_modes, list | tuple)
            or not attempt_modes
            or any(not str(mode).strip() for mode in attempt_modes)
        ):
            raise ValueError("attempt_modes must contain at least one non-empty mode")

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
            execution_controls=execution_controls,
        )

    def initialize(self, run_dir: Path):
        """Record both control layers in rollout state so runs stay auditable.

        The metadata written here is what lets a later reader tell which executor
        produced a trajectory and under which sandbox constraints, without
        re-reading the experiment config.
        """

        state = super().initialize(run_dir)
        state.metadata.update(
            {
                "executor": self.executor,
                "execution_owner": "Harbor",
                "skill_injection": "prompt_template_path",
                "target_model": self.target_model,
                "executor_controls": dict(self.executor_controls or {}),
                "execution_controls": dict(self.execution_controls or {}),
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
        """Attach the normalized contract before SEAGym persists or reflects on it.

        Execution controls are applied first, so a task whose declared network
        policy disagrees with the config raises before Harbor is invoked.

        Args:
            batch: Task batch to roll out.
            env: SEAGym task environment; mutated in place by the timeout and
                log-retention controls.
            task_index: Resolves task ids to task records carrying the Harbor
                source paths that network-policy validation inspects.
            baseline_state: Current baseline state, supplying the skill and the
                metadata that seeds the normalization context.

        Returns:
            The delegate's batch with ``extra.holoskill_gym.normalized_evidence``
            attached to every trajectory.
        """

        tasks = [task_index.require(task_id) for task_id in batch.task_ids]
        _apply_execution_controls(env, tasks=tasks, controls=self.execution_controls or {})
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
            executor_controls={
                **(self.executor_controls or {}),
                **({"execution": dict(self.execution_controls)} if self.execution_controls else {}),
            },
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
    """Reject a target model the selected CLI cannot drive.

    Codex and Claude Code are not interchangeable harnesses: pointing one at the
    other's model family fails inside the container, after the image has built
    and the credential has been spent. Catching it here keeps a cross-harness
    transfer config from burning a run on a typo.

    Args:
        executor: ``codex_exec`` or ``claude_code_exec``.
        model: Resolved target model id.

    Raises:
        ValueError: The model family does not match the executor.
    """

    lowered = model.lower()
    if executor == "codex_exec" and ("claude" in lowered or lowered.startswith("anthropic/")):
        raise ValueError(f"model {model!r} is incompatible with Codex")
    if executor == "claude_code_exec" and not (
        "claude" in lowered or lowered.startswith("anthropic/")
    ):
        raise ValueError(f"model {model!r} is incompatible with Claude Code")


def _validate_executor_controls(executor: str, controls: dict[str, Any]) -> None:
    """Bound the model-facing kwargs before they reach the Harbor agent.

    Only the values with a fixed domain or a sign constraint are checked. Harbor
    validates the rest at agent construction; the point here is to fail at config
    load rather than mid-run.

    Args:
        executor: Selected executor, which decides whether Codex-only keys apply.
        controls: Merged executor controls from ``config`` and ``config.kwargs``.

    Raises:
        ValueError: Unknown ``reasoning_effort`` or ``reasoning_summary`` value,
            or a non-positive ``max_turns`` / ``max_thinking_tokens``.
    """

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


def _validate_execution_controls(executor: str, controls: dict[str, Any]) -> None:
    """Bound the sandbox controls at configuration time.

    ``max_steps`` is rejected outright for Codex: at the Harbor revision pinned
    through SEAGym the Codex agent exposes no step or turn cap, so accepting the
    key would advertise a budget that nothing enforces. Failing loudly is
    preferable to a config that reads as bounded but is not.

    Network modes are only checked for membership here; whether a task actually
    declares them is settled later, at rollout time, by
    ``_validate_task_network_policy``.

    Args:
        executor: Selected executor, which decides whether ``max_steps`` applies.
        controls: Execution controls lifted from the rollout config.

    Raises:
        ValueError: Non-positive timeout or step budget, ``max_steps`` on an
            executor that cannot enforce it, an unknown network mode, or an
            unknown ``raw_log_retention`` value.
    """

    for key in ("agent_timeout_seconds", "verifier_timeout_seconds", "max_steps"):
        if key in controls and int(controls[key]) <= 0:
            raise ValueError(f"{key} must be positive")
    if "max_steps" in controls and executor != "claude_code_exec":
        raise ValueError("max_steps is enforceable only for claude_code_exec at this Harbor pin")
    for key in ("agent_network_mode", "verifier_network_mode"):
        if key in controls and controls[key] not in {"no-network", "allowlist", "public"}:
            raise ValueError(f"{key} must be no-network, allowlist, or public")
    if controls.get("raw_log_retention") not in {None, "none", "all"}:
        raise ValueError("raw_log_retention must be none or all")


def _apply_execution_controls(env: TaskEnv, *, tasks: list[Any], controls: dict[str, Any]) -> None:
    """Impose the sandbox controls on the environment for this rollout.

    Timeouts and log retention are *applied* -- they overwrite the environment's
    per-run attributes, taking precedence over the ``backend`` defaults in the
    experiment config. Network policy is *asserted* instead; see
    ``_validate_task_network_policy``.

    ``raw_log_retention: "none"`` appends Harbor exclude-log flags for both
    phases, which keeps raw provider transcripts out of the run directory. The
    flags are added idempotently so a repeated rollout cannot grow ``extra_args``
    without bound.

    Args:
        env: Task environment, mutated in place.
        tasks: Resolved task records for this batch, inspected for policy.
        controls: Validated execution controls; an empty mapping is a no-op.

    Raises:
        TypeError: The environment exposes no attribute for a requested control.
        ValueError: A task's declared network policy does not match the config.
    """

    if not controls:
        return
    for control, attribute in (
        ("agent_timeout_seconds", "agent_override_timeout_sec"),
        ("verifier_timeout_seconds", "verifier_override_timeout_sec"),
    ):
        if control not in controls:
            continue
        if not hasattr(env, attribute):
            raise TypeError(f"environment cannot enforce {control}")
        setattr(env, attribute, int(controls[control]))

    _validate_task_network_policy(tasks, controls)

    if controls.get("raw_log_retention") == "none":
        if not hasattr(env, "extra_args"):
            raise TypeError("environment cannot enforce raw_log_retention")
        extra_args = env.extra_args  # type: ignore[attr-defined]
        for flag, pattern in (
            ("--agent-exclude-logs", "*.log"),
            ("--agent-exclude-logs", "*.txt"),
            ("--agent-exclude-logs", "**/stdout.txt"),
            ("--agent-exclude-logs", "**/stderr.txt"),
            ("--verifier-exclude-logs", "*.log"),
            ("--verifier-exclude-logs", "*.txt"),
            ("--verifier-exclude-logs", "**/stdout.txt"),
            ("--verifier-exclude-logs", "**/stderr.txt"),
        ):
            pair = [flag, pattern]
            if not any(extra_args[index : index + 2] == pair for index in range(len(extra_args))):
                extra_args.extend(pair)


# ---------------------------------------------------------------------------
# Harbor network policies this binding refuses to run
#
# `agent_network_mode` and `verifier_network_mode` are ASSERTIONS, not settings.
# Nothing in this module writes a policy into Harbor. The task package's
# `task.toml` is the single source of truth, and this function only refuses to
# start when the task does not already declare what the experiment config claims.
# A SEAGym config therefore cannot widen a task's egress; the only thing it can
# do is fail closed.
#
# Rejected before any container starts:
#
#   1. An unknown mode. `_validate_execution_controls` admits only `no-network`,
#      `allowlist` and `public`. Anything else is a configuration error.
#   2. A declared/actual mismatch. Config asks for `no-network` on the verifier
#      but `[verifier].network_mode` says `allowlist` -> rejected. The converse
#      is rejected too: a task stricter than the config asked for still means the
#      run manifest would misdescribe the conditions, and silent divergence in
#      either direction invalidates the result.
#   3. A missing declaration. A task omitting `[agent].network_mode` or
#      `[verifier].network_mode` reads back as None, which never equals a
#      requested mode. An undeclared phase is rejected rather than inheriting the
#      `[environment]` baseline, whose effective default is `public` -- the exact
#      case where a silent inherit would be most damaging.
#   4. An uninspectable task. No `local_path`, and no `dataset_path` +
#      `task_name` pair, means the policy cannot be read at all -> rejected. An
#      unreadable or malformed `task.toml` is rejected for the same reason: an
#      unverifiable policy is treated as a failed policy.
#
# Deliberately NOT checked here: `[environment].network_mode`, which governs
# image build and container start rather than agent or verifier execution. Task
# builds legitimately need `apt-get` and `pip` egress. What this guard protects
# is grading containment -- that the verifier phase cannot reach the network, and
# that the agent phase reaches only what the task declared.
# ---------------------------------------------------------------------------
def _validate_task_network_policy(tasks: list[Any], controls: dict[str, Any]) -> None:
    """Assert each task declares the per-phase network policy the config claims.

    Args:
        tasks: Resolved task records; each must expose a readable Harbor path.
        controls: Execution controls supplying the expected per-phase modes. When
            neither mode is set the check is skipped entirely.

    Raises:
        ValueError: A task path cannot be resolved or read, or a phase's declared
            `network_mode` differs from the requested one.
    """

    expected = {
        "agent": controls.get("agent_network_mode"),
        "verifier": controls.get("verifier_network_mode"),
    }
    if not any(expected.values()):
        return
    for task in tasks:
        source = task.source
        task_path: Path | None = None
        if source.get("local_path"):
            task_path = Path(str(source["local_path"]))
        elif source.get("dataset_path") and source.get("task_name"):
            task_path = (
                Path(str(source["dataset_path"])) / str(source["task_name"]).rsplit("/", 1)[-1]
            )
        if task_path is None:
            raise ValueError(
                f"task {task.task_id} has no inspectable Harbor path for network policy"
            )
        config_path = task_path / "task.toml" if task_path.is_dir() else task_path
        try:
            task_config = tomllib.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ValueError(f"cannot inspect network policy for task {task.task_id}") from exc
        for phase, required in expected.items():
            if required is None:
                continue
            actual = (task_config.get(phase) or {}).get("network_mode")
            if actual != required:
                raise ValueError(
                    f"task {task.task_id} {phase} network_mode is {actual!r}; expected {required!r}"
                )
