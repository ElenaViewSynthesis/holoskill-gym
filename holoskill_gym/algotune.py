"""AlgoTune bridge: run AlgoTune tasks through the SkillOpt-gated loop.

AlgoTune tasks carry their own verifier. They emit a single scalar into
``reward.txt`` -- the raw speedup over the reference implementation -- and print
a performance summary to the verifier's stdout. This project's gate instead
consumes a strict :class:`~holoskill_gym.verifier.VerifierResult`, and
``engine._aggregate_correctness_gated_performance`` raises ``GateExecutionError``
when a gate task arrives without a raw speedup. Nothing connects the two, so a
gated run over AlgoTune fails at the gate *after* paying for the rollouts.

This module is that connection, in two halves.

**The evidence bridge.** :class:`AlgoTuneRolloutAgent` runs the Harbor rollout
exactly as :class:`~holoskill_gym.rollout_agent.CliCodeOptRolloutAgent` does,
then synthesises a ``VerifierResult`` from AlgoTune's own output before the
trajectory is normalised. AlgoTune's reward *is* a speedup and its
``Validity: True`` *is* a correctness pass, so the mapping is faithful -- but it
is a translation, not a measurement, and its limits are recorded in
``LIMITATIONS`` below and stamped into every result it produces.

**The dataset builder.** :func:`build_dataset` writes the task index, split
manifest and private gate manifest over the vendored AlgoTune tasks, which
otherwise do not exist for this dataset.

Network policy is deliberately absent. AlgoTune tasks declare no
``[agent].network_mode`` or ``[verifier].network_mode``, and
``_validate_task_network_policy`` rejects an undeclared phase whenever a config
requests one. Configs generated here therefore omit both keys, which makes that
check return early. The cost is real: the tasks run under Harbor's environment
baseline, whose effective default is ``public``. Do not treat a run produced
this way as network-contained.
"""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from seagym.baselines import BaselineState, TrajectoryBatch
from seagym.baselines.data import TaskBatch
from seagym.data.types import TaskIndex
from seagym.envs.base import TaskEnv

from .rollout_agent import CliCodeOptRolloutAgent, _apply_execution_controls
from .trajectory import NormalizationContext, normalize_trajectory_records
from .verifier import VerifierResult

#: Why a score produced by this bridge is weaker than one from the strict
#: verifier. Stamped onto every synthesised result so a later reader cannot
#: mistake a translated score for a measured one.
LIMITATIONS = (
    (
        "algotune-bridge: reward translated from AlgoTune's own verifier, "
        "not measured by verify_code_optimization"
    ),
    (
        "algotune-bridge: no edit-policy enforcement -- AlgoTune declares no "
        "forbidden globs and no changed-file cap, so edit_policy_pass is asserted"
    ),
    (
        "algotune-bridge: no before/after benchmark samples, so "
        "coefficient_of_variation is unavailable and stability cannot be judged"
    ),
    "algotune-bridge: tasks run without a declared network policy",
)

#: AlgoTune's floor for a solution that fails validation or is slower than the
#: reference. A reward of exactly this value is ambiguous -- see `_correctness`.
MERCY_SCORE = 1.0

_SUMMARY = {
    "validity": re.compile(r"^Validity:\s*(\w+)", re.MULTILINE),
    "baseline_time_s": re.compile(r"^Total Baseline Time:\s*([0-9.]+)s", re.MULTILINE),
    "solver_time_s": re.compile(r"^Total Solver Time:\s*([0-9.]+)s", re.MULTILINE),
    "raw_speedup": re.compile(r"^Raw Speedup:\s*([0-9.]+)\s*x", re.MULTILINE),
}


@dataclass(frozen=True)
class AlgoTuneOutcome:
    """What AlgoTune's verifier actually reported for one trial."""

    speedup: float | None
    validity: bool | None
    baseline_time_s: float | None
    solver_time_s: float | None
    source: str

    @property
    def correctness_pass(self) -> bool:
        """Whether the solution validated.

        ``Validity`` from the performance summary is authoritative when present.
        Falling back to the reward alone is lossy: AlgoTune awards the mercy
        score to an *invalid* solution and to a valid one that merely failed to
        improve, so a bare ``1.0`` cannot distinguish them. The fallback treats
        the ambiguous case as a failure, which is the safe direction for a gate.
        """

        if self.validity is not None:
            return self.validity
        if self.speedup is None:
            return False
        return self.speedup > MERCY_SCORE


def read_algotune_outcome(result_path: str | None, rewards: dict[str, float]) -> AlgoTuneOutcome:
    """Recover AlgoTune's verdict from a trial directory, falling back to rewards."""

    reward = rewards.get("reward")
    speedup = float(reward) if isinstance(reward, int | float) and reward > 0 else None
    validity: bool | None = None
    baseline_time = solver_time = None
    source = "rewards"

    if result_path and "://" not in result_path:
        stdout = Path(result_path).resolve().parent / "verifier" / "test-stdout.txt"
        if stdout.is_file():
            text = stdout.read_text(encoding="utf-8", errors="replace")
            parsed: dict[str, Any] = {}
            for name, pattern in _SUMMARY.items():
                found = pattern.search(text)
                if found:
                    parsed[name] = found.group(1)
            if parsed:
                source = "verifier-stdout"
            if "validity" in parsed:
                validity = parsed["validity"].strip().lower() == "true"
            if "raw_speedup" in parsed:
                speedup = float(parsed["raw_speedup"])
            baseline_time = (
                float(parsed["baseline_time_s"]) if "baseline_time_s" in parsed else None
            )
            solver_time = float(parsed["solver_time_s"]) if "solver_time_s" in parsed else None

    return AlgoTuneOutcome(
        speedup=speedup,
        validity=validity,
        baseline_time_s=baseline_time,
        solver_time_s=solver_time,
        source=source,
    )


def verifier_result_from_algotune(task_id: str, outcome: AlgoTuneOutcome) -> VerifierResult:
    """Translate an AlgoTune outcome into the strict result the gate consumes.

    ``infra_valid`` is False when no speedup could be recovered at all. That case
    matters: an OOM-killed AlgoTune verifier leaves a pre-seeded ``0`` in
    ``reward.txt`` and exits cleanly, so without this distinction an
    infrastructure failure would enter the gate as a legitimate zero and, under a
    harmonic aggregate, sink the whole update.
    """

    infra_valid = outcome.speedup is not None
    correctness_pass = infra_valid and outcome.correctness_pass
    errors = list(LIMITATIONS)
    if not infra_valid:
        errors.insert(0, "algotune verifier reported no usable speedup")

    return VerifierResult(
        task_id=task_id,
        correctness_before_pass=True,  # AlgoTune ships a validated reference
        correctness_pass=correctness_pass,
        edit_policy_pass=True,  # asserted, not checked -- see LIMITATIONS
        infra_valid=infra_valid,
        benchmark={
            "metric": "algotune_speedup",
            "direction": "maximize",
            "before_aggregate": outcome.baseline_time_s,
            "after_aggregate": outcome.solver_time_s,
            "speedup": outcome.speedup if correctness_pass else None,
        },
        terminal_status="success" if correctness_pass else "test_failure",
        errors=errors,
    )


@dataclass
class AlgoTuneRolloutAgent(CliCodeOptRolloutAgent):
    """Rollout agent that synthesises strict evidence from AlgoTune's verifier.

    Identical to its parent except that AlgoTune's outcome is injected into each
    trajectory before normalisation, so the gate and the report metrics receive a
    speedup and a correctness verdict they would otherwise never see.
    """

    def rollout(
        self,
        batch: TaskBatch,
        *,
        env: TaskEnv,
        task_index: TaskIndex,
        baseline_state: BaselineState,
    ) -> TrajectoryBatch:
        from dataclasses import replace

        tasks = [task_index.require(task_id) for task_id in batch.task_ids]
        _apply_execution_controls(env, tasks=tasks, controls=self.execution_controls or {})
        trajectories = super(CliCodeOptRolloutAgent, self).rollout(
            batch,
            env=env,
            task_index=task_index,
            baseline_state=baseline_state,
        )

        raw_records: list[dict[str, Any]] = []
        staged: list[Any] = []
        for trajectory in trajectories.trajectories:
            record = trajectory.to_dict()
            refs = dict(record.get("refs") or {})
            rewards = {
                key: float(value)
                for key, value in (record.get("rewards") or {}).items()
                if isinstance(value, int | float)
            }
            outcome = read_algotune_outcome(refs.get("result_path"), rewards)
            result = verifier_result_from_algotune(str(trajectory.task_id), outcome)

            extra = dict(refs.get("extra") or {})
            project = dict(extra.get("holoskill_gym") or {})
            project["verifier_result"] = result.model_dump(mode="json")
            project["benchmark"] = result.benchmark.model_dump(mode="json")
            project["correctness"] = {
                "before_pass": result.correctness_before_pass,
                "after_pass": result.correctness_pass,
            }
            project["terminal_status"] = result.terminal_status
            project["algotune_outcome_source"] = outcome.source
            extra["holoskill_gym"] = project
            refs["extra"] = extra
            record["refs"] = refs
            raw_records.append(record)
            staged.append((trajectory, refs, project))

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
        normalized = normalize_trajectory_records(raw_records, context=context)

        enriched = []
        for (trajectory, refs, project), evidence in zip(staged, normalized, strict=True):
            project = dict(project)
            project["normalized_evidence"] = evidence.model_dump(mode="json")
            refs = dict(refs)
            extra = dict(refs.get("extra") or {})
            extra["holoskill_gym"] = project
            refs["extra"] = extra
            task_result = (
                None
                if trajectory.task_result is None
                else replace(trajectory.task_result, refs=refs)
            )
            enriched.append(replace(trajectory, refs=refs, task_result=task_result))
        return replace(trajectories, trajectories=enriched)


# --------------------------------------------------------------------------
# Dataset builder
# --------------------------------------------------------------------------


def discover_tasks(root: Path, *, max_problem_size: int | None) -> list[dict[str, Any]]:
    """Read vendored AlgoTune task packages, optionally filtered by problem size.

    The filter is a memory guard, not a difficulty knob. Problem sizes span 1 to
    6,291,456 and are calibrated against the 16 GB the tasks declare; on a
    smaller Docker VM the large end is OOM-killed during verification, which
    surfaces as a silent zero rather than an error.
    """

    tasks: list[dict[str, Any]] = []
    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        config = directory / "task.toml"
        if not config.is_file():
            continue
        parsed = tomllib.loads(config.read_text(encoding="utf-8"))
        metadata = parsed.get("metadata") or {}
        size = metadata.get("algotune_problem_size")
        if max_problem_size is not None and isinstance(size, int) and size > max_problem_size:
            continue
        tasks.append(
            {
                "task_id": directory.name,
                "problem_size": size,
                "difficulty": metadata.get("difficulty", "medium"),
            }
        )
    return tasks


def build_dataset(
    *,
    tasks_root: Path,
    output_dir: Path,
    dataset_path: str,
    train: int,
    val: int,
    test: int,
    gate: int,
    max_problem_size: int | None,
) -> dict[str, Any]:
    """Write the task index, split manifest and private gate manifest.

    Splits are cut from the size-sorted task list so the cheapest tasks land in
    train, and the four sets are disjoint by construction -- ``LeakageGuard``
    rejects any overlap between train and gate fail-closed, so an accidental
    intersection would abort the run rather than quietly contaminate the gate.
    """

    discovered = discover_tasks(tasks_root, max_problem_size=max_problem_size)
    needed = train + val + test + gate
    if len(discovered) < needed:
        raise SystemExit(
            f"need {needed} tasks but only {len(discovered)} match "
            f"max_problem_size={max_problem_size}"
        )
    ordered = sorted(discovered, key=lambda t: (t["problem_size"] or 0, t["task_id"]))

    cuts: dict[str, list[dict[str, Any]]] = {}
    offset = 0
    for name, count in (("train", train), ("val", val), ("test", test), ("gate", gate)):
        cuts[name] = ordered[offset : offset + count]
        offset += count

    output_dir.mkdir(parents=True, exist_ok=True)
    index = {
        "version": "holoskill-algotune-v1",
        "tasks": [
            {
                "task_id": task["task_id"],
                "source": {
                    "type": "harbor",
                    "dataset_path": dataset_path,
                    "task_name": task["task_id"],
                },
                "attributes": {
                    "domain": "code",
                    "task_type": "optimization",
                    "difficulty": task["difficulty"],
                    "problem_size": task["problem_size"],
                },
                "scoring": {
                    "main_reward_key": "reward",
                    "success_threshold": 1.0,
                    "score_transform": "binary_threshold",
                },
            }
            for group in cuts.values()
            for task in group
        ],
    }
    _write(output_dir / "task_index.json", index)

    split = {
        "split_id": "holoskill_algotune_canary_v1",
        "split_version": "v1",
        "seed": 42,
        "splits": {name: [t["task_id"] for t in cuts[name]] for name in ("train", "val", "test")},
    }
    _write(output_dir / "split.json", split)

    gate_manifest = {
        "version": "holoskill-algotune-private-gate-v1",
        "tasks": [
            {
                "task_id": task["task_id"],
                "source": {
                    "type": "harbor",
                    "dataset_path": dataset_path,
                    "task_name": task["task_id"],
                },
                "attributes": {"domain": "code", "task_type": "optimization"},
                "scoring": {
                    "main_reward_key": "reward",
                    "success_threshold": 1.0,
                    "score_transform": "binary_threshold",
                },
            }
            for task in cuts["gate"]
        ],
    }
    _write(output_dir / "skillopt_gate.json", gate_manifest)

    return {
        "discovered": len(discovered),
        "written": {name: [t["task_id"] for t in group] for name, group in cuts.items()},
        "output_dir": str(output_dir),
    }


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m holoskill_gym.algotune",
        description="Build the AlgoTune task index, split and private gate manifests.",
    )
    parser.add_argument(
        "--tasks-root",
        type=Path,
        default=Path("results/trusted-tasks/algotune"),
        help="Directory of vendored AlgoTune task packages.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("examples/holo_skillopt_algotune"),
        help="Where to write task_index.json, split.json and skillopt_gate.json.",
    )
    parser.add_argument(
        "--dataset-path",
        default="../../results/trusted-tasks/algotune",
        help="Path to the task packages, as resolved from the manifests.",
    )
    parser.add_argument("--train", type=int, default=8)
    parser.add_argument("--val", type=int, default=4)
    parser.add_argument("--test", type=int, default=4)
    parser.add_argument("--gate", type=int, default=4)
    parser.add_argument(
        "--max-problem-size",
        type=int,
        default=1000,
        help=(
            "Skip tasks above this problem size. A memory guard, not a difficulty "
            "filter: large sizes are calibrated for 16 GB and are OOM-killed on a "
            "smaller Docker VM, which surfaces as a silent zero. Pass 0 for no limit."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit the summary as JSON.")
    args = parser.parse_args(argv)

    if not args.tasks_root.is_dir():
        raise SystemExit(f"no AlgoTune tasks under {args.tasks_root}")

    summary = build_dataset(
        tasks_root=args.tasks_root,
        output_dir=args.output_dir,
        dataset_path=args.dataset_path,
        train=args.train,
        val=args.val,
        test=args.test,
        gate=args.gate,
        max_problem_size=args.max_problem_size or None,
    )

    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    print(f"tasks matching filter : {summary['discovered']}")
    for name, ids in summary["written"].items():
        print(f"  {name:5} ({len(ids)}): {', '.join(ids)}")
    print(f"written to            : {summary['output_dir']}")
    print("\nNote: manifests omit agent_network_mode / verifier_network_mode, so the")
    print("task network-policy assertion is skipped. These runs are not contained.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
