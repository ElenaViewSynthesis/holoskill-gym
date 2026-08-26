"""SEAGym baseline adapter for SkillOpt proposals and its private gate."""

from __future__ import annotations

import difflib
import importlib
import importlib.metadata
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from dotenv import load_dotenv
from seagym.baselines import (
    BaseBaseline,
    BaselineState,
    Checkpoint,
    EvalBatch,
    TrajectoryBatch,
    UpdateResult,
)
from seagym.data.types import TaskIndex

from .engine import (
    GateExecutionError,
    SkillOptEngineConfig,
    SkillOptHoloEngine,
    SkillOptReflectionError,
    normalize_training_evidence,
)
from .holo_backend import HoloBackend, HoloBackendError
from .leakage import LeakageGuard
from .schemas import GateDecision, GateTaskScore, OptimizerUsage
from .state import StateIntegrityError, StateStore, prompt_sha256, skill_sha256
from .validation import ProposalPolicy, ProposalValidationError
from .verifier import verifier_result_from_trajectory


class GateEvaluator(Protocol):
    """Execute the method-private task set for one immutable skill."""

    def __call__(self, *, skill: str, task_ids: list[str]) -> Sequence[GateTaskScore]: ...


@dataclass
class _GateRuntime:
    env: Any
    rollout_agent: Any


@dataclass
class SkillOptHoloBaseline(BaseBaseline):
    """Keep SkillOpt acceptance inside the method and SEAGym observational."""

    initial_skill_path: Path | None = None
    leakage_guard: LeakageGuard | None = None
    engine: SkillOptHoloEngine | None = None
    gate_evaluator: GateEvaluator | None = field(default=None, repr=False)
    gate_task_index: TaskIndex | None = field(default=None, repr=False)
    target_executor: str = "codex_exec"
    max_update_records: int | None = None
    _runtime: _GateRuntime | None = field(default=None, init=False, repr=False)

    @classmethod
    def from_config(
        cls,
        *,
        name: str,
        config: dict[str, Any],
        models: dict[str, Any],
        state_dir: Path,
        run_dir: Path,
        base_dir: Path | None,
    ) -> SkillOptHoloBaseline:
        del models, run_dir
        load_dotenv(_resolve_path(config.get("env_file", ".env"), base_dir), override=False)
        initial_skill_path = _resolve_path(_required(config, "initial_skill_path"), base_dir)
        gate_path = _resolve_path(_required(config, "skillopt_gate_path"), base_dir)
        split_path = _resolve_path(_required(config, "split_manifest_path"), base_dir)
        guard = LeakageGuard.from_files(split_manifest_path=split_path, gate_path=gate_path)
        gate_mode = str(config.get("gate_mode", "on"))
        if gate_mode not in {"on", "off"}:
            raise ValueError("gate_mode must be 'on' or 'off'")
        optimizer_backend = str(config.get("optimizer_backend", "holo_openai_compatible"))
        reflection_fn = None
        if optimizer_backend == "deterministic_fake":
            from .fakes import DeterministicHoloBackend, deterministic_reflection

            backend = DeterministicHoloBackend()
            reflection_fn = deterministic_reflection
        elif optimizer_backend == "holo_openai_compatible":
            backend = HoloBackend.from_env(
                model=str(config.get("optimizer_model") or "holo3-1-35b-a3b"),
                max_completion_tokens=int(config.get("max_completion_tokens", 3_000)),
                timeout_seconds=float(config.get("optimizer_timeout_seconds", 120)),
                max_attempts=int(config.get("optimizer_max_attempts", 3)),
            )
        else:
            raise ValueError(f"unsupported optimizer_backend: {optimizer_backend}")
        gate_metric = str(config.get("gate_metric", "soft"))
        if gate_metric not in {
            "hard",
            "soft",
            "mixed",
            "correctness_gated_performance",
        }:
            raise ValueError(
                "gate_metric must be hard, soft, mixed, or correctness_gated_performance"
            )
        engine = SkillOptHoloEngine(
            backend,
            config=SkillOptEngineConfig(
                gate_mode=gate_mode,  # type: ignore[arg-type]
                gate_metric=gate_metric,  # type: ignore[arg-type]
                gate_mixed_weight=float(config.get("gate_mixed_weight", 0.5)),
                gate_no_regression=bool(config.get("gate_no_regression", True)),
                strict_improvement_epsilon=float(config.get("strict_improvement_epsilon", 0.001)),
                evidence_max_records=int(config.get("max_update_records") or 32),
                evidence_max_string_chars=int(config.get("evidence_max_string_chars", 1_200)),
                evidence_max_list_items=int(config.get("evidence_max_list_items", 32)),
                evidence_max_mapping_items=int(config.get("evidence_max_mapping_items", 64)),
            ),
            proposal_policy=ProposalPolicy(
                max_edit_operations=int(config.get("max_edit_operations", 3)),
                max_skill_tokens=int(config.get("max_skill_tokens", 2_000)),
                max_skill_chars=int(config.get("max_skill_chars", 12_000)),
            ),
            reflection_fn=reflection_fn,
        )
        evaluator_path = config.get("gate_evaluator_path")
        evaluator = _load_object(str(evaluator_path)) if evaluator_path else None
        gate_task_index = _load_gate_task_index(gate_path)
        return cls(
            baseline_id=name,
            state_dir=state_dir,
            initial_skill_path=initial_skill_path,
            leakage_guard=guard,
            engine=engine,
            gate_evaluator=evaluator,
            gate_task_index=gate_task_index,
            target_executor=str(config.get("target_executor", "codex_exec")),
            max_update_records=(
                None
                if config.get("max_update_records") in (None, "")
                else int(config["max_update_records"])
            ),
        )

    @property
    def store(self) -> StateStore:
        return StateStore(self.state_dir)

    def initialize(self, run_dir: Path) -> BaselineState:
        del run_dir
        engine, guard = self._requirements()
        if self.initial_skill_path is None:
            raise ValueError("initial_skill_path is required")
        initial_skill = self.initial_skill_path.read_text(encoding="utf-8")
        optimizer_prompt_hash = prompt_sha256(engine.proposal_system_prompt())
        method_state = self.store.initialize(
            initial_skill=initial_skill,
            metadata={
                "skillopt_version": _package_version("skillopt"),
                "skillopt_commit": "e4ea6a6",
                "seagym_version": _package_version("seagym"),
                "seagym_commit": "9e61e14",
                "holo_model_id": engine.backend.config.model,
                "optimizer_prompt_hash": optimizer_prompt_hash,
                "target_executor": self.target_executor,
                "gate_mode": engine.config.gate_mode,
                "task_split_hashes": guard.split_hashes(),
            },
        )
        self.update_index = method_state.last_committed_update
        metadata = self._baseline_metadata(method_state.model_dump(mode="json"))
        self._write_baseline_metadata(metadata)
        return BaselineState(self.state_dir, metadata)

    def update(self, trajectories: TrajectoryBatch, state: BaselineState) -> UpdateResult:
        engine, guard = self._requirements()
        guard.assert_training_batch(
            task_ids=trajectories.task_ids,
            view_name=trajectories.view_name,
            mode=trajectories.mode,
        )
        update_dir = self.next_update_dir(state, "update")
        prior = self.store.load()
        if self.update_index <= prior.last_committed_update:
            raise StateIntegrityError(f"update {self.update_index} was already committed")
        current_skill = self.store.read_skill()
        raw_records = [item.to_dict() for item in trajectories.trajectories]
        evidence = normalize_training_evidence(raw_records)
        _write_jsonl(update_dir / "trajectories.jsonl", evidence)
        (update_dir / "skill_before.md").write_text(current_skill, encoding="utf-8")

        usage = OptimizerUsage()
        proposal_record: dict[str, Any] | None = None
        gate_decision: GateDecision | None = None
        try:
            proposal = engine.propose(
                current_skill=current_skill,
                training_trajectories=evidence,
                rejected_edit_buffer=_read_jsonl(self.store.rejected_path)[-20:],
                held_out_ids=guard.gate_ids | _all_observer_ids(guard),
            )
            proposal_record = proposal.response.proposal.model_dump(mode="json")
            usage = _add_usage(proposal.reflection.usage, proposal.response.call.usage)
            _write_json(update_dir / "proposal.json", proposal_record)
            _write_json(update_dir / "usage.json", usage.model_dump())
            (update_dir / "candidate_skill.md").write_text(
                proposal.candidate_skill, encoding="utf-8"
            )
            if not proposal.changed:
                status = "no_op_proposal"
                deployed_skill = current_skill
            elif engine.config.gate_mode == "off":
                gate_decision = engine.evaluate_gate(
                    current_skill=current_skill,
                    candidate_skill=proposal.candidate_skill,
                    baseline_results=[],
                    candidate_results=[],
                    global_step=self.update_index,
                )
                status = "applied_gate_off_ablation"
                deployed_skill = gate_decision.deployed_skill
            else:
                baseline_results, candidate_results = self._run_private_gate(
                    current_skill=current_skill,
                    candidate_skill=proposal.candidate_skill,
                    guard=guard,
                )
                _write_json(
                    update_dir / "gate_results_current.json",
                    [item.model_dump() for item in baseline_results],
                )
                _write_json(
                    update_dir / "gate_results_candidate.json",
                    [item.model_dump() for item in candidate_results],
                )
                gate_decision = engine.evaluate_gate(
                    current_skill=current_skill,
                    candidate_skill=proposal.candidate_skill,
                    baseline_results=baseline_results,
                    candidate_results=candidate_results,
                    global_step=self.update_index,
                    best_skill=current_skill,
                    best_score=prior.best_score,
                    best_step=prior.best_step,
                )
                status = (
                    "accepted_by_skillopt_gate"
                    if gate_decision.accepted
                    else "rejected_by_skillopt_gate"
                )
                deployed_skill = gate_decision.deployed_skill
                _write_json(update_dir / "gate_decision.json", gate_decision.model_dump())
        except ProposalValidationError as exc:
            status = "invalid_proposal"
            deployed_skill = current_skill
            _write_json(update_dir / "diagnostics.json", _safe_error(exc))
        except (HoloBackendError, SkillOptReflectionError) as exc:
            status = "optimizer_error"
            deployed_skill = current_skill
            details = exc.to_safe_dict() if isinstance(exc, HoloBackendError) else _safe_error(exc)
            _write_json(update_dir / "diagnostics.json", details)
        except GateExecutionError as exc:
            status = "gate_execution_error"
            deployed_skill = current_skill
            _write_json(update_dir / "diagnostics.json", _safe_error(exc))

        next_state = self.store.commit(
            prior=prior,
            update_index=self.update_index,
            deployed_skill=deployed_skill,
            status=status,
            optimizer_usage=usage,
            gate_decision=gate_decision,
            proposal_record=proposal_record,
        )
        changed = deployed_skill != current_skill
        (update_dir / "deployed_skill_after.md").write_text(deployed_skill, encoding="utf-8")
        (update_dir / "diff.patch").write_text(
            "".join(
                difflib.unified_diff(
                    current_skill.splitlines(keepends=True),
                    deployed_skill.splitlines(keepends=True),
                    fromfile="skill_before.md",
                    tofile="deployed_skill_after.md",
                )
            ),
            encoding="utf-8",
        )
        state.metadata.update(self._baseline_metadata(next_state.model_dump(mode="json")))
        self._write_baseline_metadata(state.metadata)
        return UpdateResult(
            update_index=self.update_index,
            changed=changed,
            status=status,
            metrics={
                "accepted_count": next_state.accepted_count,
                "rejected_count": next_state.rejected_count,
                "skill_version": next_state.skill_version,
            },
            logs={
                "optimizer_usage": usage.model_dump(),
                "cost": {
                    "input_tokens": usage.prompt_tokens,
                    "output_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                },
                "cost_role": "optimizer",
            },
            artifacts={
                "update_dir": str(update_dir),
                "prompt_template_path": str(self.store.skill_path),
            },
        )

    def bind_runtime(
        self,
        *,
        env: Any,
        task_index: Any,
        rollout_agent: Any,
        run_dir: Path,
        batch_plan: Any | None = None,
    ) -> None:
        """Bind Harbor execution without exposing observer task data to the method."""

        del task_index, run_dir, batch_plan
        self._runtime = _GateRuntime(env=env, rollout_agent=rollout_agent)

    def load_checkpoint(self, checkpoint: Checkpoint) -> BaselineState:
        state = super().load_checkpoint(checkpoint)
        method_state = self.store.load()
        self.update_index = method_state.last_committed_update
        state.metadata.update(self._baseline_metadata(method_state.model_dump(mode="json")))
        self._write_baseline_metadata(state.metadata)
        return state

    def report(self, state: BaselineState) -> dict[str, Any]:
        method_state = self.store.load()
        return {
            **super().report(state),
            "method": "SkillOpt/Holo",
            "skill_version": method_state.skill_version,
            "accepted_count": method_state.accepted_count,
            "rejected_count": method_state.rejected_count,
            "optimizer_usage": method_state.cumulative_optimizer_usage.model_dump(),
            "latest_update_status": method_state.latest_update_status,
        }

    def _run_private_gate(
        self,
        *,
        current_skill: str,
        candidate_skill: str,
        guard: LeakageGuard,
    ) -> tuple[list[GateTaskScore], list[GateTaskScore]]:
        task_ids = sorted(guard.gate_ids)
        if self.gate_evaluator is not None:
            try:
                baseline = list(self.gate_evaluator(skill=current_skill, task_ids=task_ids))
                candidate = list(self.gate_evaluator(skill=candidate_skill, task_ids=task_ids))
            except GateExecutionError:
                raise
            except Exception as exc:
                raise GateExecutionError(
                    f"private gate evaluator failed: {type(exc).__name__}"
                ) from exc
        else:
            baseline = self._run_runtime_gate(skill=current_skill, task_ids=task_ids)
            candidate = self._run_runtime_gate(skill=candidate_skill, task_ids=task_ids)
        guard.assert_gate_ids([item.task_id for item in baseline])
        guard.assert_gate_ids([item.task_id for item in candidate])
        return baseline, candidate

    def _run_runtime_gate(self, *, skill: str, task_ids: list[str]) -> list[GateTaskScore]:
        if self._runtime is None or self.gate_task_index is None:
            raise GateExecutionError(
                "private gate requires a gate_evaluator_path or a bound runtime with full gate tasks"
            )
        skill_dir = self.state_dir / "private_gate_skills"
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path = skill_dir / f"{skill_sha256(skill)}.md"
        if not skill_path.exists():
            skill_path.write_text(skill, encoding="utf-8")
        gate_state = BaselineState(
            self.state_dir,
            {"prompt_template_path": str(skill_path), "method_private": True},
        )
        batch = EvalBatch(task_ids=task_ids, view_name="skillopt_gate", mode="eval")
        trajectories = self._runtime.rollout_agent.rollout(
            batch,
            env=self._runtime.env,
            task_index=self.gate_task_index,
            baseline_state=gate_state,
        )
        scores: list[GateTaskScore] = []
        for trajectory in trajectories.trajectories:
            verifier_result = verifier_result_from_trajectory(trajectory)
            if verifier_result is None:
                scores.append(
                    GateTaskScore(
                        task_id=trajectory.task_id,
                        hard_score=0,
                        soft_score=0,
                        correctness_pass=False,
                        edit_policy_pass=False,
                        infra_valid=False,
                        error="strict HoloSkill verifier result is missing",
                    )
                )
                continue
            if verifier_result.task_id != trajectory.task_id:
                scores.append(
                    GateTaskScore(
                        task_id=trajectory.task_id,
                        hard_score=0,
                        soft_score=0,
                        correctness_pass=False,
                        edit_policy_pass=False,
                        infra_valid=False,
                        error="strict verifier task ID does not match trajectory task ID",
                    )
                )
                continue
            scores.append(verifier_result.to_gate_task_score())
        return scores

    def _requirements(self) -> tuple[SkillOptHoloEngine, LeakageGuard]:
        if self.engine is None or self.leakage_guard is None:
            raise RuntimeError("baseline engine and leakage guard must be configured")
        return self.engine, self.leakage_guard

    def _baseline_metadata(self, method_state: dict[str, Any]) -> dict[str, Any]:
        return {
            "baseline_id": self.baseline_id,
            "type": self.__class__.__name__,
            "prompt_template_path": str(self.store.skill_path),
            "skillopt_state_path": str(self.store.state_path),
            "method_state": method_state,
        }

    def _write_baseline_metadata(self, metadata: dict[str, Any]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        _write_json(self.state_dir / "baseline_state.json", metadata)


def _required(config: dict[str, Any], key: str) -> Any:
    value = config.get(key)
    if value in (None, ""):
        raise ValueError(f"baseline config requires {key}")
    return value


def _resolve_path(value: Any, base_dir: Path | None) -> Path:
    path = Path(str(value))
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    return path.resolve()


def _load_object(import_path: str) -> Any:
    module_name, separator, attribute = import_path.partition(":")
    if not separator:
        module_name, _, attribute = import_path.rpartition(".")
    if not module_name or not attribute:
        raise ValueError(f"invalid import path: {import_path}")
    return getattr(importlib.import_module(module_name), attribute)


def _load_gate_task_index(path: Path) -> TaskIndex | None:
    data = json.loads(path.read_text(encoding="utf-8"))
    tasks = data.get("tasks") if isinstance(data, dict) else None
    if not isinstance(tasks, list) or not tasks:
        return None
    if not all(
        isinstance(task, dict) and {"task_id", "source", "attributes"} <= task.keys()
        for task in tasks
    ):
        return None
    return TaskIndex.from_dict(data, path=path)


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _all_observer_ids(guard: LeakageGuard) -> frozenset[str]:
    return frozenset().union(*guard.observer_ids.values()) if guard.observer_ids else frozenset()


def _add_usage(left: OptimizerUsage, right: OptimizerUsage) -> OptimizerUsage:
    return OptimizerUsage(
        prompt_tokens=left.prompt_tokens + right.prompt_tokens,
        completion_tokens=left.completion_tokens + right.completion_tokens,
        total_tokens=left.total_tokens + right.total_tokens,
    )


def _safe_error(error: Exception) -> dict[str, str]:
    return {"type": type(error).__name__, "message": str(error)[:1_000]}


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: Sequence[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
