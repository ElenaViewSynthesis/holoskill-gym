"""Lossless normalized evidence for Harbor-backed code-optimization trials."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from harbor.models.trajectories import Trajectory as AtifTrajectory
from pydantic import BaseModel, ConfigDict, Field, field_validator

EVIDENCE_SCHEMA_VERSION = "holoskill-evidence-v1"
PROMPT_MAX_CHARS = 4_000
MAX_ACTION_SUMMARIES = 128
MAX_ARGUMENT_KEYS = 32

TerminalStatus = Literal[
    "success",
    "test_failure",
    "policy_failure",
    "timeout",
    "agent_error",
    "benchmark_error",
]


class EvidenceModel(BaseModel):
    """Strict finite-number base for persisted evidence."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ActionSummary(EvidenceModel):
    step_id: int = Field(ge=1)
    function_name: str = Field(min_length=1, max_length=256)
    argument_keys: list[str] = Field(default_factory=list, max_length=MAX_ARGUMENT_KEYS)
    observation_count: int = Field(default=0, ge=0)


class DiffStatistics(EvidenceModel):
    files_changed: int = Field(default=0, ge=0)
    insertions: int = Field(default=0, ge=0)
    deletions: int = Field(default=0, ge=0)


class CorrectnessEvidence(EvidenceModel):
    before_pass: bool | None = None
    after_pass: bool | None = None


class BenchmarkEvidence(EvidenceModel):
    metric: str | None = None
    direction: Literal["minimize", "maximize"] | None = None
    before_samples: list[float] = Field(default_factory=list)
    after_samples: list[float] = Field(default_factory=list)
    before_aggregate: float | None = None
    after_aggregate: float | None = None
    speedup: float | None = Field(default=None, gt=0)
    coefficient_of_variation: float | None = Field(default=None, ge=0)


class PerformanceAggregates(EvidenceModel):
    latency_before: float | None = Field(default=None, ge=0)
    latency_after: float | None = Field(default=None, ge=0)
    latency_delta_pct: float | None = None
    throughput_before: float | None = Field(default=None, ge=0)
    throughput_after: float | None = Field(default=None, ge=0)
    throughput_delta_pct: float | None = None
    peak_memory_before: float | None = Field(default=None, ge=0)
    peak_memory_after: float | None = Field(default=None, ge=0)
    peak_memory_delta_pct: float | None = None


class PolicyEvidence(EvidenceModel):
    edit_policy_pass: bool | None = None
    forbidden_edit: bool = False
    tampering_detected: bool = False
    forbidden_files: list[str] = Field(default_factory=list)


class UsageEvidence(EvidenceModel):
    input_tokens: int = Field(default=0, ge=0)
    cached_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    wall_time_seconds: float | None = Field(default=None, ge=0)
    cost_usd: float = Field(default=0, ge=0)


class NormalizedTrajectory(EvidenceModel):
    """Provider-neutral, auditable evidence for exactly one task attempt."""

    schema_version: Literal["holoskill-evidence-v1"] = EVIDENCE_SCHEMA_VERSION
    evidence_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    attempt_id: str = Field(min_length=1)
    attempt_index: int = Field(ge=0)
    attempt_count: int = Field(ge=1)
    split: str
    view_name: str = Field(min_length=1)
    mode: str = Field(min_length=1)
    run_id: str | None = None
    checkpoint_id: str | None = None
    update_id: str | None = None
    executor: str | None = None
    model: str | None = None
    skill_version: int | None = Field(default=None, ge=0)
    skill_sha256: str | None = None
    parent_skill_sha256: str | None = None
    repository_commit: str | None = None
    sanitized_prompt: str = Field(default="", max_length=PROMPT_MAX_CHARS)
    action_summaries: list[ActionSummary] = Field(
        default_factory=list,
        max_length=MAX_ACTION_SUMMARIES,
    )
    exit_code: int | None = None
    timeout_reason: str | None = None
    patch_sha256: str | None = None
    changed_files: list[str] = Field(default_factory=list)
    diff: DiffStatistics = Field(default_factory=DiffStatistics)
    correctness: CorrectnessEvidence = Field(default_factory=CorrectnessEvidence)
    benchmark: BenchmarkEvidence = Field(default_factory=BenchmarkEvidence)
    performance: PerformanceAggregates = Field(default_factory=PerformanceAggregates)
    policy: PolicyEvidence = Field(default_factory=PolicyEvidence)
    usage: UsageEvidence = Field(default_factory=UsageEvidence)
    terminal_status: TerminalStatus
    score: float
    success: bool
    rewards: dict[str, float] = Field(default_factory=dict)
    error: str | None = None
    atif_valid: bool | None = None
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=lambda: {"holoskill_gym": {}})

    @field_validator("skill_sha256", "parent_skill_sha256", "patch_sha256")
    @classmethod
    def validate_optional_sha256(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("hash fields must be lowercase SHA-256 values")
        return value

    @field_validator("repository_commit")
    @classmethod
    def validate_optional_commit(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[0-9a-f]{40}", value):
            raise ValueError("repository_commit must be a full lowercase SHA-1")
        return value

    @field_validator("extra")
    @classmethod
    def require_project_namespace(cls, value: dict[str, Any]) -> dict[str, Any]:
        if set(value) - {"holoskill_gym"}:
            raise ValueError("project-specific evidence must live under extra.holoskill_gym")
        if not isinstance(value.get("holoskill_gym", {}), dict):
            raise TypeError("extra.holoskill_gym must be an object")
        return value


@dataclass(frozen=True)
class NormalizationContext:
    run_id: str | None = None
    checkpoint_id: str | None = None
    update_id: str | None = None
    executor: str | None = None
    model: str | None = None
    skill_version: int | None = None
    skill_sha256: str | None = None
    parent_skill_sha256: str | None = None
    repository_commit: str | None = None
    split: str | None = None

    @classmethod
    def from_metadata(
        cls,
        metadata: Mapping[str, Any] | None,
        *,
        batch_metadata: Mapping[str, Any] | None = None,
        executor: str | None = None,
        model: str | None = None,
    ) -> NormalizationContext:
        metadata = metadata or {}
        batch_metadata = batch_metadata or {}
        method_state = metadata.get("method_state")
        if not isinstance(method_state, Mapping):
            method_state = {}
        return cls(
            run_id=_optional_string(batch_metadata.get("run_id") or metadata.get("run_id")),
            checkpoint_id=_optional_string(
                batch_metadata.get("checkpoint_id")
                or metadata.get("checkpoint_id")
                or metadata.get("agent_checkpoint_id")
            ),
            update_id=_optional_string(
                batch_metadata.get("global_update_index") or metadata.get("global_update_index")
            ),
            executor=executor or _optional_string(method_state.get("target_executor")),
            model=model,
            skill_version=_optional_int(method_state.get("skill_version")),
            skill_sha256=_optional_string(method_state.get("current_hash")),
            parent_skill_sha256=_optional_string(method_state.get("parent_hash")),
            repository_commit=_optional_string(batch_metadata.get("repository_commit")),
            split=_optional_string(batch_metadata.get("split")),
        )


@dataclass(frozen=True)
class EvidenceBudget:
    max_records: int = 32
    max_string_chars: int = 1_200
    max_list_items: int = 32
    max_mapping_items: int = 64
    max_depth: int = 8

    def __post_init__(self) -> None:
        for name, value in vars(self).items():
            if value <= 0:
                raise ValueError(f"{name} must be positive")


def normalize_trajectory_records(
    trajectories: Sequence[Mapping[str, Any]],
    *,
    context: NormalizationContext | None = None,
) -> list[NormalizedTrajectory]:
    """Normalize all attempts without rejecting duplicate task IDs."""

    context = context or NormalizationContext()
    task_ids = [_required_task_id(raw) for raw in trajectories]
    counts = Counter(task_ids)
    positions: defaultdict[str, int] = defaultdict(int)
    used_evidence_ids: set[str] = set()
    records: list[NormalizedTrajectory] = []
    for raw, task_id in zip(trajectories, task_ids, strict=True):
        attempt_index = positions[task_id]
        positions[task_id] += 1
        attempt_id = _attempt_id(raw, attempt_index=attempt_index)
        evidence_id = _evidence_id(
            task_id,
            attempt_id=attempt_id,
            attempt_index=attempt_index,
            attempt_count=counts[task_id],
            used=used_evidence_ids,
        )
        records.append(
            normalize_trajectory_record(
                raw,
                context=context,
                evidence_id=evidence_id,
                attempt_id=attempt_id,
                attempt_index=attempt_index,
                attempt_count=counts[task_id],
            )
        )
    return records


def normalize_trajectory_record(
    raw: Mapping[str, Any],
    *,
    context: NormalizationContext | None = None,
    evidence_id: str | None = None,
    attempt_id: str | None = None,
    attempt_index: int = 0,
    attempt_count: int = 1,
) -> NormalizedTrajectory:
    """Normalize one SEAGym trajectory and its Harbor/ATIF artifacts."""

    existing = _existing_normalized_record(raw)
    if existing is not None:
        return existing

    context = context or NormalizationContext()
    task_id = _required_task_id(raw)
    refs = raw.get("refs") if isinstance(raw.get("refs"), Mapping) else {}
    project = _project_data(raw, refs)
    attempt_id = attempt_id or _attempt_id(raw, attempt_index=attempt_index)
    evidence_id = evidence_id or task_id

    result_path = _local_path(refs.get("result_path"))
    verifier_payload = _read_verifier_artifact(result_path)
    if verifier_payload is not None:
        project = _merge_verifier_project(project, verifier_payload)
    atif_path = result_path.parent / "agent" / "trajectory.json" if result_path else None
    atif, atif_error = _read_atif(atif_path)
    action_summaries = _atif_action_summaries(atif) if atif is not None else []
    prompt, prompt_omitted_chars = _sanitized_prompt(raw, atif)
    artifact_paths = _artifact_paths(result_path, refs, project)
    patch_sha = _patch_sha(project, artifact_paths)

    rewards = _finite_float_mapping(raw.get("rewards"))
    success = bool(raw.get("success", False))
    error = _sanitized_optional_string(raw.get("error"))
    timeout_reason = _timeout_reason(error, refs, project)
    policy = _policy_evidence(rewards, project)
    terminal_status = _terminal_status(
        success=success,
        error=error,
        timeout_reason=timeout_reason,
        policy=policy,
        project=project,
        atif_error=atif_error,
    )
    usage = _usage_evidence(raw.get("cost"), atif, raw.get("runtime_seconds"))
    changed_files = _string_list(project.get("changed_files") or raw.get("changed_files"))

    source_fields, omitted_source_fields = _source_fields(raw)
    project_extra: dict[str, Any] = {
        "source_fields": source_fields,
        "omitted_source_fields": omitted_source_fields,
    }
    if verifier_payload is not None:
        project_extra["verifier_result"] = verifier_payload
    if prompt_omitted_chars:
        project_extra["prompt_omitted_chars"] = prompt_omitted_chars
    if atif_error:
        project_extra["atif_validation_error"] = atif_error

    return NormalizedTrajectory(
        evidence_id=evidence_id,
        task_id=task_id,
        attempt_id=attempt_id,
        attempt_index=attempt_index,
        attempt_count=attempt_count,
        split=context.split or str(project.get("split") or raw.get("view_name") or "unknown"),
        view_name=str(raw.get("view_name") or "unknown"),
        mode=str(raw.get("mode") or "unknown"),
        run_id=context.run_id or _optional_string(refs.get("run_id") or refs.get("job_id")),
        checkpoint_id=context.checkpoint_id or _optional_string(refs.get("agent_checkpoint_id")),
        update_id=context.update_id or _optional_string(refs.get("global_update_index")),
        executor=context.executor
        or _optional_string(refs.get("agent_id"))
        or (atif.agent.name if atif else None),
        model=context.model or (atif.agent.model_name if atif else None),
        skill_version=context.skill_version,
        skill_sha256=context.skill_sha256,
        parent_skill_sha256=context.parent_skill_sha256,
        repository_commit=context.repository_commit
        or _optional_string(project.get("repository_commit") or refs.get("repository_commit")),
        sanitized_prompt=prompt,
        action_summaries=action_summaries,
        exit_code=_optional_int(
            project.get("exit_code")
            if project.get("exit_code") is not None
            else refs.get("harbor_returncode")
        ),
        timeout_reason=timeout_reason,
        patch_sha256=patch_sha,
        changed_files=sorted(set(changed_files)),
        diff=_model_from_mapping(DiffStatistics, project.get("diff_statistics")),
        correctness=_correctness_evidence(rewards, project),
        benchmark=_model_from_mapping(BenchmarkEvidence, project.get("benchmark")),
        performance=_model_from_mapping(
            PerformanceAggregates,
            project.get("performance"),
        ),
        policy=policy,
        usage=usage,
        terminal_status=terminal_status,
        score=_finite_float(raw.get("score"), default=0.0),
        success=success,
        rewards=rewards,
        error=error or atif_error,
        atif_valid=None if atif_path is None or not atif_path.exists() else atif is not None,
        artifact_paths=artifact_paths,
        extra={"holoskill_gym": project_extra},
    )


def structured_evidence_payload(
    records: Sequence[Mapping[str, Any] | BaseModel],
    *,
    budget: EvidenceBudget | None = None,
) -> dict[str, Any]:
    """Return valid JSON-shaped evidence with explicit structural elisions."""

    budget = budget or EvidenceBudget()
    total = len(records)
    included = records[: budget.max_records]
    rendered_records: list[dict[str, Any]] = []
    for record in included:
        raw = record.model_dump(mode="json") if isinstance(record, BaseModel) else dict(record)
        elisions: list[dict[str, Any]] = []
        bounded = _budget_value(raw, path="$", depth=0, budget=budget, elisions=elisions)
        rendered_records.append(
            {
                "record": bounded,
                "field_elisions": elisions,
            }
        )
    return {
        "schema_version": "holoskill-evidence-payload-v1",
        "total_records": total,
        "included_records": len(rendered_records),
        "omitted_records": total - len(rendered_records),
        "records": rendered_records,
    }


def render_structured_evidence_json(
    records: Sequence[Mapping[str, Any] | BaseModel],
    *,
    budget: EvidenceBudget | None = None,
) -> str:
    return json.dumps(
        structured_evidence_payload(records, budget=budget),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _read_atif(path: Path | None) -> tuple[AtifTrajectory | None, str | None]:
    if path is None or not path.exists():
        return None, None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return AtifTrajectory.model_validate(payload), None
    except (OSError, ValueError) as exc:
        return None, f"invalid ATIF trajectory: {type(exc).__name__}"


def _atif_action_summaries(atif: AtifTrajectory) -> list[ActionSummary]:
    summaries: list[ActionSummary] = []
    for step in atif.steps:
        observation_count = len(step.observation.results) if step.observation else 0
        for call in step.tool_calls or []:
            summaries.append(
                ActionSummary(
                    step_id=step.step_id,
                    function_name=_sanitize_text(call.function_name, max_chars=256)[0],
                    argument_keys=sorted(str(key)[:128] for key in call.arguments)[
                        :MAX_ARGUMENT_KEYS
                    ],
                    observation_count=observation_count,
                )
            )
            if len(summaries) >= MAX_ACTION_SUMMARIES:
                return summaries
    return summaries


def _sanitized_prompt(
    raw: Mapping[str, Any],
    atif: AtifTrajectory | None,
) -> tuple[str, int]:
    candidate = raw.get("sanitized_prompt") or raw.get("prompt") or raw.get("instruction")
    if not isinstance(candidate, str) and atif is not None:
        for step in atif.steps:
            if step.source == "user" and isinstance(step.message, str):
                candidate = step.message
                break
    return _sanitize_text(str(candidate or ""), max_chars=PROMPT_MAX_CHARS)


def _artifact_paths(
    result_path: Path | None,
    refs: Mapping[str, Any],
    project: Mapping[str, Any],
) -> dict[str, str]:
    paths: dict[str, str] = {}
    if result_path is not None:
        paths["harbor_result"] = str(result_path)
        trial_dir = result_path.parent
        candidates = {
            "atif_trajectory": trial_dir / "agent" / "trajectory.json",
            "agent_response": trial_dir / "agent" / "response.txt",
            "agent_logs": trial_dir / "agent",
            "verifier_logs": trial_dir / "verifier",
            "holoskill_verifier": trial_dir / "verifier" / "holoskill_verifier.json",
        }
        paths.update({name: str(path) for name, path in candidates.items() if path.exists()})
    for name, raw_path in (
        (project.get("artifact_paths") or {}).items()
        if isinstance(project.get("artifact_paths"), Mapping)
        else ()
    ):
        path = _local_path(raw_path)
        if path is not None:
            paths[str(name)] = str(path)
    for name in ("patch_path", "cost_path", "job_dir"):
        path = _local_path(project.get(name) or refs.get(name))
        if path is not None:
            paths[name] = str(path)
    return dict(sorted(paths.items()))


def _read_verifier_artifact(result_path: Path | None) -> dict[str, Any] | None:
    if result_path is None:
        return None
    for path in (
        result_path.parent / "verifier" / "holoskill_verifier.json",
        result_path.parent / "logs" / "verifier" / "holoskill_verifier.json",
    ):
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None
    return None


def _merge_verifier_project(
    project: Mapping[str, Any],
    verifier: Mapping[str, Any],
) -> dict[str, Any]:
    merged = dict(project)
    merged["verifier_result"] = dict(verifier)
    merged["terminal_status"] = verifier.get("terminal_status")
    merged["changed_files"] = verifier.get("changed_files")
    merged["diff_statistics"] = verifier.get("diff")
    merged["patch_sha256"] = verifier.get("patch_sha256")
    merged["benchmark"] = verifier.get("benchmark")
    merged["performance"] = verifier.get("performance")
    merged["policy"] = verifier.get("policy")
    merged["correctness"] = {
        "before_pass": verifier.get("correctness_before_pass"),
        "after_pass": verifier.get("correctness_pass"),
    }
    return merged


def _patch_sha(project: Mapping[str, Any], artifacts: Mapping[str, str]) -> str | None:
    direct = project.get("patch_sha256")
    if isinstance(direct, str) and re.fullmatch(r"[0-9a-f]{64}", direct):
        return direct
    patch_path = artifacts.get("patch_path")
    if not patch_path:
        return None
    path = Path(patch_path)
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    except OSError:
        return None


def _usage_evidence(
    raw_cost: Any,
    atif: AtifTrajectory | None,
    runtime_seconds: Any,
) -> UsageEvidence:
    cost = raw_cost if isinstance(raw_cost, Mapping) else {}
    final = atif.final_metrics if atif is not None else None
    tool_calls = sum(len(step.tool_calls or []) for step in atif.steps) if atif else 0
    input_tokens = _nonnegative_int(
        cost.get("input_tokens")
        or cost.get("n_input_tokens")
        or (final.total_prompt_tokens if final else None)
    )
    cached_tokens = _nonnegative_int(
        cost.get("cache_tokens")
        or cost.get("n_cache_tokens")
        or (final.total_cached_tokens if final else None)
    )
    output_tokens = _nonnegative_int(
        cost.get("output_tokens")
        or cost.get("n_output_tokens")
        or (final.total_completion_tokens if final else None)
    )
    return UsageEvidence(
        input_tokens=input_tokens,
        cached_tokens=cached_tokens,
        output_tokens=output_tokens,
        total_tokens=_nonnegative_int(cost.get("total_tokens")) or input_tokens + output_tokens,
        tool_calls=_nonnegative_int(cost.get("tool_calls")) or tool_calls,
        wall_time_seconds=_nonnegative_float(
            cost.get("wall_time") if cost.get("wall_time") is not None else runtime_seconds
        ),
        cost_usd=_nonnegative_float(
            cost.get("cost_usd")
            if cost.get("cost_usd") is not None
            else (final.total_cost_usd if final else None)
        )
        or 0.0,
    )


def _policy_evidence(
    rewards: Mapping[str, float],
    project: Mapping[str, Any],
) -> PolicyEvidence:
    raw = project.get("policy") if isinstance(project.get("policy"), Mapping) else {}
    pass_value = raw.get("edit_policy_pass")
    if pass_value is None and "edit_policy_pass" in rewards:
        pass_value = rewards["edit_policy_pass"] >= 1
    forbidden_files = _string_list(raw.get("forbidden_files"))
    return PolicyEvidence(
        edit_policy_pass=None if pass_value is None else bool(pass_value),
        forbidden_edit=bool(raw.get("forbidden_edit", forbidden_files)),
        tampering_detected=bool(raw.get("tampering_detected", False)),
        forbidden_files=sorted(set(forbidden_files)),
    )


def _correctness_evidence(
    rewards: Mapping[str, float],
    project: Mapping[str, Any],
) -> CorrectnessEvidence:
    raw = project.get("correctness")
    if not isinstance(raw, Mapping):
        raw = {}
    after = raw.get("after_pass")
    if after is None and "correctness_pass" in rewards:
        after = rewards["correctness_pass"] >= 1
    return CorrectnessEvidence(
        before_pass=_optional_bool(raw.get("before_pass")),
        after_pass=_optional_bool(after),
    )


def _terminal_status(
    *,
    success: bool,
    error: str | None,
    timeout_reason: str | None,
    policy: PolicyEvidence,
    project: Mapping[str, Any],
    atif_error: str | None,
) -> TerminalStatus:
    explicit = project.get("terminal_status")
    allowed = {
        "success",
        "test_failure",
        "policy_failure",
        "timeout",
        "agent_error",
        "benchmark_error",
    }
    if explicit in allowed:
        return explicit  # type: ignore[return-value]
    if timeout_reason:
        return "timeout"
    if policy.edit_policy_pass is False or policy.forbidden_edit or policy.tampering_detected:
        return "policy_failure"
    if project.get("benchmark_error"):
        return "benchmark_error"
    if error or atif_error:
        return "agent_error"
    return "success" if success else "test_failure"


def _timeout_reason(
    error: str | None,
    refs: Mapping[str, Any],
    project: Mapping[str, Any],
) -> str | None:
    explicit = project.get("timeout_reason") or refs.get("timeout_reason")
    if explicit:
        return _sanitized_optional_string(explicit)
    if error and "timeout" in error.lower():
        return error
    return None


def _existing_normalized_record(raw: Mapping[str, Any]) -> NormalizedTrajectory | None:
    if raw.get("schema_version") == EVIDENCE_SCHEMA_VERSION:
        return NormalizedTrajectory.model_validate(raw)
    refs = raw.get("refs")
    if not isinstance(refs, Mapping):
        return None
    extra = refs.get("extra")
    if not isinstance(extra, Mapping):
        return None
    project = extra.get("holoskill_gym")
    if not isinstance(project, Mapping):
        return None
    evidence = project.get("normalized_evidence")
    return NormalizedTrajectory.model_validate(evidence) if isinstance(evidence, Mapping) else None


def _project_data(raw: Mapping[str, Any], refs: Mapping[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for container in (raw.get("extra"), refs.get("extra")):
        if isinstance(container, Mapping):
            project = container.get("holoskill_gym")
            if isinstance(project, Mapping):
                merged.update(project)
    return merged


def _source_fields(raw: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    known = {
        "task_id",
        "attempt_id",
        "view_name",
        "mode",
        "success",
        "reward",
        "score",
        "rewards",
        "cost",
        "runtime_seconds",
        "error",
        "refs",
        "extra",
        "task_result",
        "prompt",
        "instruction",
        "sanitized_prompt",
        "changed_files",
    }
    persisted: dict[str, Any] = {}
    omitted: list[dict[str, str]] = []
    for key in sorted(raw):
        if key in known:
            continue
        lowered = key.lower()
        if "reasoning" in lowered or "chain_of_thought" in lowered:
            omitted.append({"field": key, "reason": "hidden_reasoning"})
            continue
        if any(marker in lowered for marker in ("stdout", "stderr", "transcript", "log")):
            omitted.append({"field": key, "reason": "inline_log"})
            continue
        persisted[key] = _redact_source_value(raw[key])
    refs = raw.get("refs")
    if isinstance(refs, Mapping):
        for key in sorted(refs):
            lowered = key.lower()
            if any(marker in lowered for marker in ("stdout", "stderr", "command")):
                omitted.append({"field": f"refs.{key}", "reason": "inline_log"})
    return persisted, omitted


def _redact_source_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _redact_source_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_redact_source_value(item) for item in value]
    if isinstance(value, str):
        text, omitted = _sanitize_text(value, max_chars=2_000)
        return text if not omitted else {"value": text, "omitted_chars": omitted}
    return value


def _budget_value(
    value: Any,
    *,
    path: str,
    depth: int,
    budget: EvidenceBudget,
    elisions: list[dict[str, Any]],
) -> Any:
    if depth >= budget.max_depth and isinstance(value, Mapping | list | tuple):
        elisions.append({"path": path, "reason": "max_depth"})
        return None
    if isinstance(value, str):
        if len(value) <= budget.max_string_chars:
            return value
        elisions.append(
            {
                "path": path,
                "reason": "max_string_chars",
                "omitted_chars": len(value) - budget.max_string_chars,
            }
        )
        return value[: budget.max_string_chars]
    if isinstance(value, Mapping):
        items = sorted(((str(key), item) for key, item in value.items()), key=lambda x: x[0])
        kept = items[: budget.max_mapping_items]
        if len(items) > len(kept):
            elisions.append(
                {
                    "path": path,
                    "reason": "max_mapping_items",
                    "omitted_items": len(items) - len(kept),
                }
            )
        return {
            key: _budget_value(
                item,
                path=f"{path}.{key}",
                depth=depth + 1,
                budget=budget,
                elisions=elisions,
            )
            for key, item in kept
        }
    if isinstance(value, list | tuple):
        kept = value[: budget.max_list_items]
        if len(value) > len(kept):
            elisions.append(
                {
                    "path": path,
                    "reason": "max_list_items",
                    "omitted_items": len(value) - len(kept),
                }
            )
        return [
            _budget_value(
                item,
                path=f"{path}[{index}]",
                depth=depth + 1,
                budget=budget,
                elisions=elisions,
            )
            for index, item in enumerate(kept)
        ]
    return value


def _required_task_id(raw: Mapping[str, Any]) -> str:
    task_id = str(raw.get("task_id") or "").strip()
    if not task_id:
        raise ValueError("every training trajectory requires task_id")
    return task_id


def _attempt_id(raw: Mapping[str, Any], *, attempt_index: int) -> str:
    refs = raw.get("refs") if isinstance(raw.get("refs"), Mapping) else {}
    value = raw.get("attempt_id") or refs.get("attempt_id") or refs.get("trial_name")
    if not value:
        value = refs.get("trial_uri") or f"attempt-{attempt_index + 1:04d}"
    return _sanitize_text(str(value), max_chars=512)[0] or f"attempt-{attempt_index + 1:04d}"


def _evidence_id(
    task_id: str,
    *,
    attempt_id: str,
    attempt_index: int,
    attempt_count: int,
    used: set[str],
) -> str:
    candidate = task_id if attempt_count == 1 else f"{task_id}::attempt::{attempt_id}"
    if candidate in used:
        candidate = f"{candidate}::{attempt_index + 1}"
    used.add(candidate)
    return candidate


def _sanitize_text(value: str, *, max_chars: int) -> tuple[str, int]:
    text = value.replace("\x00", "")
    patterns = (
        re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+"),
        re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"),
        re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)[^\s,;]+"),
        re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]+\b"),
    )
    for pattern in patterns:
        text = pattern.sub(
            lambda match: (match.group(1) if match.lastindex else "") + "[REDACTED]", text
        )
    omitted = max(0, len(text) - max_chars)
    return text[:max_chars], omitted


def _sanitized_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text, _ = _sanitize_text(str(value), max_chars=2_000)
    return text or None


def _local_path(value: Any) -> Path | None:
    if not value or not isinstance(value, str | Path):
        return None
    text = str(value)
    if "://" in text:
        return None
    return Path(text).resolve()


def _model_from_mapping(model: type[EvidenceModel], value: Any) -> Any:
    return model.model_validate(value if isinstance(value, Mapping) else {})


def _finite_float_mapping(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): parsed
        for key, item in value.items()
        if (parsed := _optional_finite_float(item)) is not None
    }


def _finite_float(value: Any, *, default: float) -> float:
    parsed = _optional_finite_float(value)
    return default if parsed is None else parsed


def _optional_finite_float(value: Any) -> float | None:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def _nonnegative_float(value: Any) -> float | None:
    parsed = _optional_finite_float(value)
    return parsed if parsed is not None and parsed >= 0 else None


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0
    return max(0, int(value))


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _optional_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list | tuple | set):
        return []
    return [str(item) for item in value if str(item)]
