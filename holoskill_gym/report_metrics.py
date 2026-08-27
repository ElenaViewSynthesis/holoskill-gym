"""SEAGym report metrics computed from persisted HoloSkill evidence."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .metrics import geometric_mean_speedup


@dataclass(frozen=True)
class CorrectSpeedupGeomeanMetric:
    name: str = "correct_speedup_geomean"

    def compute(self, records: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
        del config
        grouped: dict[str, list[float]] = defaultdict(list)
        for row, evidence in _task_evidence(records):
            if not _correct_and_valid(evidence):
                continue
            speedup = _finite_positive((evidence.get("benchmark") or {}).get("speedup"))
            if speedup is not None:
                grouped[_view_key(row)].append(speedup)
        all_values = [value for values in grouped.values() for value in values]
        return {
            "value": geometric_mean_speedup(all_values),
            "num_correct_runs": len(all_values),
            "by_view": {
                view: {
                    "value": geometric_mean_speedup(values),
                    "num_correct_runs": len(values),
                }
                for view, values in sorted(grouped.items())
            },
        }


@dataclass(frozen=True)
class CandidateAcceptanceRateMetric:
    name: str = "candidate_acceptance_rate"

    def compute(self, records: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
        del config
        statuses = _update_statuses(records)
        accepted = statuses.count("accepted_by_skillopt_gate")
        rejected = statuses.count("rejected_by_skillopt_gate")
        decisions = accepted + rejected
        return {
            "value": accepted / decisions if decisions else None,
            "accepted_by_private_gate": accepted,
            "rejected_by_private_gate": rejected,
            "private_gate_decisions": decisions,
        }


@dataclass(frozen=True)
class GateOffApplicationRateMetric:
    name: str = "gate_off_application_rate"

    def compute(self, records: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
        del config
        statuses = _update_statuses(records)
        applied = statuses.count("applied_gate_off_ablation")
        return {
            "value": applied / len(statuses) if statuses else None,
            "applications": applied,
            "num_updates": len(statuses),
            "private_gate_acceptance": False,
        }


@dataclass(frozen=True)
class ForbiddenEditRateMetric:
    name: str = "forbidden_edit_rate"

    def compute(self, records: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
        del config
        grouped: dict[str, list[bool]] = defaultdict(list)
        for row, evidence in _task_evidence(records):
            policy = evidence.get("policy") if isinstance(evidence.get("policy"), Mapping) else {}
            grouped[_view_key(row)].append(bool(policy.get("forbidden_edit", False)))
        values = [value for group in grouped.values() for value in group]
        return {
            "value": _rate(values),
            "forbidden_edits": sum(values),
            "num_runs": len(values),
            "by_view": {
                view: {"value": _rate(group), "forbidden_edits": sum(group), "num_runs": len(group)}
                for view, group in sorted(grouped.items())
            },
        }


@dataclass(frozen=True)
class ReliabilityRatesMetric:
    name: str = "reliability_rates"

    def compute(self, records: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
        del config
        rows = list(_task_evidence(records))
        timeout_flags = [
            evidence.get("terminal_status") == "timeout"
            or bool((evidence.get("rewards") or {}).get("timeout", False))
            for _, evidence in rows
        ]
        infra_flags = [not _infra_valid(evidence) for _, evidence in rows]
        combined = [
            timeout or infra for timeout, infra in zip(timeout_flags, infra_flags, strict=True)
        ]
        return {
            "timeout_rate": _rate(timeout_flags),
            "infra_failure_rate": _rate(infra_flags),
            "timeout_or_infra_failure_rate": _rate(combined),
            "timeouts": sum(timeout_flags),
            "infra_failures": sum(infra_flags),
            "num_runs": len(rows),
        }


@dataclass(frozen=True)
class P95PerformanceChangeMetric:
    name: str = "p95_performance_change"

    def compute(self, records: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
        del config
        latency: list[float] = []
        memory: list[float] = []
        for _, evidence in _task_evidence(records):
            performance = evidence.get("performance")
            if not isinstance(performance, Mapping):
                continue
            latency_value = _finite_number(performance.get("latency_delta_pct"))
            memory_value = _finite_number(performance.get("peak_memory_delta_pct"))
            if latency_value is not None:
                latency.append(latency_value)
            if memory_value is not None:
                memory.append(memory_value)
        return {
            "latency_delta_pct": _percentile(latency, 0.95),
            "peak_memory_delta_pct": _percentile(memory, 0.95),
            "latency_samples": len(latency),
            "peak_memory_samples": len(memory),
        }


@dataclass(frozen=True)
class CrossHarnessTransferDeltaMetric:
    name: str = "cross_harness_transfer_delta"

    def compute(self, records: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
        transfer = config.get("cross_harness_transfer") or {}
        source = str(transfer.get("source_executor") or "")
        evaluation = str(transfer.get("evaluation_executor") or "")
        if not source or not evaluation or source == evaluation:
            return {
                "applicable": False,
                "source_executor": source or None,
                "evaluation_executor": evaluation or None,
                "by_view": {},
                "reason": "distinct source and evaluation executors are required",
            }
        reference_path_value = transfer.get("reference_metric_inputs_path")
        if reference_path_value:
            return _external_transfer_delta(
                records,
                source=source,
                evaluation=evaluation,
                reference_path=Path(str(reference_path_value)).resolve(),
            )
        grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for row, _ in _task_evidence(records):
            role = row.get("baseline_role")
            score = _finite_number(row.get("score"))
            if role in {"A_T", "A_0"} and score is not None:
                grouped[str(row.get("view_name") or "unknown")][str(role)].append(score)
        deltas = {
            view: _mean(by_role["A_T"]) - _mean(by_role["A_0"])
            for view, by_role in sorted(grouped.items())
            if by_role.get("A_T") and by_role.get("A_0")
        }
        return {
            "applicable": bool(deltas),
            "source_executor": source,
            "evaluation_executor": evaluation,
            "by_view": deltas,
            "reason": None if deltas else "paired A_T and A_0 final-view records are absent",
        }


def _external_transfer_delta(
    records: Sequence[Mapping[str, Any]],
    *,
    source: str,
    evaluation: str,
    reference_path: Path,
) -> dict[str, Any]:
    if not reference_path.exists():
        return {
            "applicable": False,
            "source_executor": source,
            "evaluation_executor": evaluation,
            "by_view": {},
            "reference_metric_inputs_path": str(reference_path),
            "reference_sha256": None,
            "reason": "source-harness metric inputs are absent",
        }
    payload = reference_path.read_bytes()
    try:
        reference_records = [
            item
            for line in payload.decode("utf-8").splitlines()
            if line.strip() and isinstance((item := json.loads(line)), dict)
        ]
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {
            "applicable": False,
            "source_executor": source,
            "evaluation_executor": evaluation,
            "by_view": {},
            "reference_metric_inputs_path": str(reference_path),
            "reference_sha256": hashlib.sha256(payload).hexdigest(),
            "reason": f"source-harness metric inputs are invalid: {type(exc).__name__}",
        }
    source_scores = _scores_by_view(reference_records, roles={"A_T"})
    target_scores = _scores_by_view(records, roles={"checkpoint", "A_T"})
    deltas = {
        view: _mean(target_scores[view]) - _mean(source_scores[view])
        for view in sorted(source_scores.keys() & target_scores.keys())
    }
    return {
        "applicable": bool(deltas),
        "source_executor": source,
        "evaluation_executor": evaluation,
        "by_view": deltas,
        "reference_metric_inputs_path": str(reference_path),
        "reference_sha256": hashlib.sha256(payload).hexdigest(),
        "reason": None if deltas else "source A_T and target checkpoint views do not overlap",
    }


def _scores_by_view(
    records: Sequence[Mapping[str, Any]],
    *,
    roles: set[str],
) -> dict[str, list[float]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row, _ in _task_evidence(records):
        score = _finite_number(row.get("score"))
        if row.get("baseline_role") in roles and score is not None:
            grouped[str(row.get("view_name") or "unknown")].append(score)
    return grouped


def _task_evidence(
    records: Sequence[Mapping[str, Any]],
) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    result: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    for row in records:
        if row.get("mode") == "update":
            continue
        refs = row.get("refs")
        extra = refs.get("extra") if isinstance(refs, Mapping) else None
        project = extra.get("holoskill_gym") if isinstance(extra, Mapping) else None
        evidence = project.get("normalized_evidence") if isinstance(project, Mapping) else None
        if isinstance(evidence, Mapping):
            result.append((row, evidence))
    return result


def _correct_and_valid(evidence: Mapping[str, Any]) -> bool:
    correctness = evidence.get("correctness")
    policy = evidence.get("policy")
    return (
        isinstance(correctness, Mapping)
        and correctness.get("after_pass") is True
        and isinstance(policy, Mapping)
        and policy.get("edit_policy_pass") is True
        and _infra_valid(evidence)
    )


def _infra_valid(evidence: Mapping[str, Any]) -> bool:
    rewards = evidence.get("rewards")
    if isinstance(rewards, Mapping) and "infra_valid" in rewards:
        value = rewards.get("infra_valid")
        return value is True or (
            isinstance(value, int | float) and not isinstance(value, bool) and float(value) == 1.0
        )
    extra = evidence.get("extra")
    project = extra.get("holoskill_gym") if isinstance(extra, Mapping) else None
    verifier = project.get("verifier_result") if isinstance(project, Mapping) else None
    return isinstance(verifier, Mapping) and verifier.get("infra_valid") is True


def _update_statuses(records: Sequence[Mapping[str, Any]]) -> list[str]:
    statuses: list[str] = []
    for row in records:
        if row.get("mode") != "update":
            continue
        summary = row.get("update_summary")
        if not isinstance(summary, Mapping):
            continue
        status = summary.get("status")
        if isinstance(status, str) and status:
            statuses.append(status)
    return statuses


def _view_key(row: Mapping[str, Any]) -> str:
    view = str(row.get("view_name") or "unknown")
    role = row.get("baseline_role")
    return f"{view}.{role}" if role else view


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _finite_positive(value: Any) -> float | None:
    number = _finite_number(value)
    return number if number is not None and number > 0 else None


def _rate(values: Sequence[bool]) -> float | None:
    return sum(values) / len(values) if values else None


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _percentile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight
