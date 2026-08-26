"""Credential-free deterministic components for tests and the smoke experiment."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from seagym.baselines import BaselineState, TrajectoryBatch
from seagym.baselines.data import TaskBatch
from seagym.data.scoring import score_from_reward
from seagym.data.types import TaskIndex, TaskRecord
from seagym.envs import TaskEnv, TaskRunResult
from seagym.rollout_agents import RolloutAgentState

from .schemas import (
    GateTaskScore,
    OptimizerCallRecord,
    OptimizerUsage,
    ProposalResponse,
    SkillUpdateProposal,
)
from .tasks import CodeOptTask
from .trajectory import NormalizationContext, normalize_trajectory_records
from .verifier import VerifierConfig, verify_code_optimization


@dataclass(frozen=True)
class DeterministicBackendConfig:
    model: str = "deterministic-holo"


class DeterministicHoloBackend:
    """Return the same evidence-linked improvement for identical input bytes."""

    def __init__(self) -> None:
        self.config = DeterministicBackendConfig()
        self.records: list[OptimizerCallRecord] = []

    def propose(self, *, system: str, user: str) -> ProposalResponse:
        del system
        match = re.search(r'"task_id"\s*:\s*"([^"]+)"', user)
        evidence_id = match.group(1) if match else "missing-evidence"
        if "Run three times and compare the median." in user:
            edits: list[dict[str, object]] = []
        else:
            edits = [
                {
                    "operation": "replace",
                    "section": "Measure",
                    "old_text": "Run once.",
                    "new_text": "Run three times and compare the median.",
                    "rationale": "A robust aggregate reduces measurement noise.",
                    "evidence_ids": [evidence_id],
                }
            ]
        proposal = SkillUpdateProposal.model_validate(
            {
                "diagnosis": ["Single measurements are noisy."],
                "edits": edits,
                "expected_effects": ["More stable performance comparisons."],
                "risks": ["The measurement stage takes longer."],
            }
        )
        record = OptimizerCallRecord(
            provider="deterministic",
            model=self.config.model,
            latency_ms=0,
            attempts=1,
            response_id="deterministic-proposal",
            finish_reason="stop",
            usage=OptimizerUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
        )
        self.records.append(record)
        return ProposalResponse(proposal=proposal, call=record)


def deterministic_reflection(**_: object) -> tuple[str, dict[str, int]]:
    return "Use repeated measurements and a robust aggregate.", {
        "prompt_tokens": 5,
        "completion_tokens": 5,
        "total_tokens": 10,
    }


def deterministic_gate(*, skill: str, task_ids: list[str]) -> list[GateTaskScore]:
    value = 0.75 if "compare the median" in skill else 0.5
    return [
        GateTaskScore(
            task_id=task_id,
            hard_score=1,
            soft_score=value,
            correctness_pass=True,
            edit_policy_pass=True,
            infra_valid=True,
        )
        for task_id in task_ids
    ]


def deterministic_client() -> SimpleNamespace:
    """Compatibility marker for callers that expect an object-like fake client."""

    return SimpleNamespace(provider="deterministic")


@dataclass
class DeterministicCodeOptRolloutAgent:
    """Credential-free fake agent that still executes the production verifier."""

    agent_id: str = "deterministic-codeopt-fixture"
    model_name: str = "deterministic-fixture-model"
    fixture_root: Path = Path("fixtures")
    _run_dir: Path | None = field(default=None, init=False, repr=False)
    _trial_index: int = field(default=0, init=False, repr=False)

    @classmethod
    def from_config(
        cls,
        *,
        name: str,
        config: dict[str, Any],
        models: dict[str, Any],
        run_dir: Path,
        base_dir: Path | None,
    ) -> DeterministicCodeOptRolloutAgent:
        del models, run_dir
        root = Path(str(config.get("fixture_root", "../../fixtures")))
        if not root.is_absolute() and base_dir is not None:
            root = base_dir / root
        return cls(
            agent_id=str(config.get("fake_agent_id") or name),
            model_name=str(config.get("model") or "deterministic-fixture-model"),
            fixture_root=root.resolve(),
        )

    def initialize(self, run_dir: Path) -> RolloutAgentState:
        self._run_dir = run_dir.resolve()
        return RolloutAgentState(
            {
                "agent_id": self.agent_id,
                "model": self.model_name,
                "fake": True,
                "executes_verifier": True,
            }
        )

    def rollout(
        self,
        batch: TaskBatch,
        *,
        env: TaskEnv,
        task_index: TaskIndex,
        baseline_state: BaselineState,
    ) -> TrajectoryBatch:
        del env
        if self._run_dir is None:
            raise RuntimeError("deterministic fixture rollout agent is not initialized")
        results = [
            self._run_task(
                task_index.require(task_id),
                view_name=batch.view_name,
                mode=batch.mode,
            )
            for task_id in batch.task_ids
        ]
        trajectories = TrajectoryBatch.from_task_results(
            results,
            task_ids=batch.task_ids,
            view_name=batch.view_name,
            mode=batch.mode,
            batch_index=batch.batch_index,
            epoch=batch.epoch,
            refs={"agent_id": self.agent_id, "fake": True},
        )
        context = NormalizationContext.from_metadata(
            baseline_state.metadata,
            batch_metadata=batch.metadata,
            executor=self.agent_id,
            model=self.model_name,
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
            refs["extra"] = {
                "holoskill_gym": {"normalized_evidence": evidence.model_dump(mode="json")}
            }
            task_result = (
                None
                if trajectory.task_result is None
                else replace(trajectory.task_result, refs=refs)
            )
            enriched.append(replace(trajectory, refs=refs, task_result=task_result))
        return replace(trajectories, trajectories=enriched)

    def _run_task(self, task: TaskRecord, *, view_name: str, mode: str) -> TaskRunResult:
        fixture = task.fixtures.get("codeopt")
        if not isinstance(fixture, dict):
            raise TypeError(f"task {task.task_id} requires fixtures.codeopt")
        self._trial_index += 1
        safe_task_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", task.task_id)
        trial_name = f"{safe_task_id}__fixture{self._trial_index:06d}"
        trial_dir = self._run_dir / "fixture_trials" / trial_name
        repo_path = trial_dir / "worktree"
        source_repo = (self.fixture_root / str(fixture["repository"])).resolve()
        solution = (self.fixture_root / str(fixture["solution"])).resolve()
        shutil.copytree(source_repo, repo_path)
        commit = _initialize_fixture_repository(repo_path)
        codeopt_task = _fixture_codeopt_task(task, fixture, repo_path=repo_path, commit=commit)
        target = repo_path / str(fixture.get("solution_target", "src/workload.py"))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(solution, target)

        verifier_dir = trial_dir / "verifier"
        verifier_result = verify_code_optimization(
            codeopt_task,
            repo_path=repo_path,
            artifact_dir=verifier_dir,
            config=VerifierConfig(benchmark_warmups=0, benchmark_samples=3),
        )
        _write_fixture_atif(
            trial_dir,
            agent_id=self.agent_id,
            model_name=self.model_name,
            instruction=codeopt_task.objective,
        )
        rewards = verifier_result.reward_metrics()
        reward = rewards[task.scoring.main_reward_key]
        score = score_from_reward(reward, task.scoring)
        result_path = trial_dir / "result.json"
        result_path.write_text(
            json.dumps(
                {
                    "trial_name": trial_name,
                    "task_name": task.task_id,
                    "verifier_result": {"rewards": rewards},
                    "agent_result": {
                        "n_input_tokens": 0,
                        "n_output_tokens": 0,
                        "total_tokens": 0,
                        "cost_usd": 0,
                    },
                    "exception_info": None,
                    "source": "holoskill_deterministic_fixture",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return TaskRunResult(
            task_id=task.task_id,
            view_name=view_name,
            mode=mode,
            rewards=rewards,
            score=score,
            success=verifier_result.reward >= task.scoring.success_threshold,
            cost={
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "tool_calls": 0,
                "cost_usd": 0,
                "wall_time": verifier_result.wall_time_seconds,
            },
            runtime_seconds=verifier_result.wall_time_seconds,
            error=None if verifier_result.infra_valid else "; ".join(verifier_result.errors),
            refs={
                "env": "deterministic-codeopt-fixture",
                "agent_id": self.agent_id,
                "model": self.model_name,
                "fake_agent": True,
                "result_path": str(result_path),
                "trial_name": trial_name,
                "attempt_id": trial_name,
                "repository_commit": commit,
            },
        )


def _initialize_fixture_repository(repo_path: Path) -> str:
    commands = (
        ("init", "--quiet"),
        ("config", "user.name", "HoloSkill Fixture"),
        ("config", "user.email", "fixture@example.invalid"),
        ("add", "."),
        ("commit", "--quiet", "-m", "fixture baseline"),
    )
    for args in commands:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo_path,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"fixture git {' '.join(args)} failed")
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def _fixture_codeopt_task(
    task: TaskRecord,
    fixture: dict[str, Any],
    *,
    repo_path: Path,
    commit: str,
) -> CodeOptTask:
    return CodeOptTask(
        task_id=task.task_id,
        repo_url=str(repo_path),
        commit=commit,
        objective=str(fixture["objective"]),
        language="python",
        runtime="python",
        setup_argv=[],
        test_argv=[sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        benchmark_argv=[sys.executable, "benchmark.py"],
        benchmark_metric=str(fixture["benchmark_metric"]),
        optimization_direction=str(fixture["optimization_direction"]),  # type: ignore[arg-type]
        timeout_seconds=int(fixture.get("timeout_seconds", 30)),
        forbidden_globs=["tests/**", "benchmark.py", ".git/**"],
        max_changed_files=2,
        tags=["deterministic", "fixture"],
    )


def _write_fixture_atif(
    trial_dir: Path,
    *,
    agent_id: str,
    model_name: str,
    instruction: str,
) -> None:
    agent_dir = trial_dir / "agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "trajectory.json").write_text(
        json.dumps(
            {
                "schema_version": "ATIF-v1.7",
                "session_id": trial_dir.name,
                "agent": {
                    "name": agent_id,
                    "version": "1",
                    "model_name": model_name,
                    "extra": {"fake": True},
                },
                "steps": [
                    {"step_id": 1, "source": "user", "message": instruction},
                    {
                        "step_id": 2,
                        "source": "agent",
                        "message": "Applied the checked-in deterministic fixture solution.",
                        "llm_call_count": 0,
                    },
                ],
                "final_metrics": {
                    "total_prompt_tokens": 0,
                    "total_completion_tokens": 0,
                    "total_cost_usd": 0,
                    "total_steps": 2,
                },
                "extra": {"holoskill_gym": {"fake_agent": True}},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
