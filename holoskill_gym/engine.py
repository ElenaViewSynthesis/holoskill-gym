"""Narrow SkillOpt façade for reflection, structured proposals, and gating."""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from .metrics import correctness_gated_performance
from .schemas import (
    GateDecision,
    GateTaskScore,
    OptimizerUsage,
    ProposalBackend,
    ProposalResponse,
    ReflectionRecord,
    proposal_json_schema,
)
from .trajectory import (
    EvidenceBudget,
    normalize_trajectory_records,
    render_structured_evidence_json,
)
from .validation import (
    AppliedProposal,
    ProposalPolicy,
    ProposalValidationError,
    validate_and_apply_proposal,
)

ReflectionFunction = Callable[..., tuple[str, dict[str, int]]]
GateMetric = Literal["hard", "soft", "mixed", "correctness_gated_performance"]


@dataclass(frozen=True)
class SkillOptEngineConfig:
    """Local compatibility controls around pinned SkillOpt v0.2.0."""

    gate_mode: Literal["on", "off"] = "on"
    gate_metric: GateMetric = "soft"
    gate_mixed_weight: float = 0.5
    gate_no_regression: bool = True
    strict_improvement_epsilon: float = 0.001
    reflection_max_tokens: int = 3_000
    reflection_timeout_seconds: int = 120
    max_reflection_chars: int = 8_000
    evidence_max_records: int = 32
    evidence_max_string_chars: int = 1_200
    evidence_max_list_items: int = 32
    evidence_max_mapping_items: int = 64

    def __post_init__(self) -> None:
        if not 0 <= self.gate_mixed_weight <= 1:
            raise ValueError("gate_mixed_weight must be between 0 and 1")
        if self.strict_improvement_epsilon < 0:
            raise ValueError("strict_improvement_epsilon must be non-negative")
        if self.reflection_max_tokens <= 0:
            raise ValueError("reflection_max_tokens must be positive")
        if self.max_reflection_chars <= 0:
            raise ValueError("max_reflection_chars must be positive")
        if (
            min(
                self.evidence_max_records,
                self.evidence_max_string_chars,
                self.evidence_max_list_items,
                self.evidence_max_mapping_items,
            )
            <= 0
        ):
            raise ValueError("evidence budgets must be positive")


@dataclass(frozen=True)
class EngineProposal:
    """Structured proposal, validated candidate bytes, and optimizer metadata."""

    response: ProposalResponse
    reflection: ReflectionRecord
    applied: AppliedProposal

    @property
    def candidate_skill(self) -> str:
        return self.applied.skill

    @property
    def changed(self) -> bool:
        return self.applied.changed


class GateExecutionError(RuntimeError):
    """Raised when the private gate cannot produce a valid comparison."""


class SkillOptReflectionError(RuntimeError):
    """Raised when SkillOpt's free-form reflection stage fails."""


class EngineProposalValidationError(ProposalValidationError):
    """Semantic rejection that retains only in-memory accounting context."""

    def __init__(
        self,
        error: ProposalValidationError,
        *,
        response: ProposalResponse,
        reflection: ReflectionRecord,
    ) -> None:
        super().__init__(error.errors)
        self.response = response
        self.reflection = reflection


class SkillOptHoloEngine:
    """Keep unstable SkillOpt internals behind one small integration surface."""

    def __init__(
        self,
        backend: ProposalBackend,
        *,
        config: SkillOptEngineConfig | None = None,
        proposal_policy: ProposalPolicy | None = None,
        reflection_fn: ReflectionFunction | None = None,
    ) -> None:
        self.backend = backend
        self.config = config or SkillOptEngineConfig()
        self.proposal_policy = proposal_policy or ProposalPolicy()
        self._reflection_fn = reflection_fn
        _disable_skillopt_reasoning_effort()

    def propose(
        self,
        *,
        current_skill: str,
        training_trajectories: Sequence[dict[str, Any]],
        rejected_edit_buffer: Sequence[dict[str, Any]] = (),
        held_out_ids: Collection[str] = (),
        forbidden_fragments: Collection[str] = (),
    ) -> EngineProposal:
        """Run SkillOpt reflection, request strict edits, and validate locally."""

        evidence = normalize_training_evidence(training_trajectories)
        evidence_ids = [item["evidence_id"] for item in evidence]
        reflection = self.reflect(current_skill=current_skill, training_evidence=evidence)
        try:
            response = self.backend.propose(
                system=self.proposal_system_prompt(),
                user=_proposal_user_prompt(
                    current_skill=current_skill,
                    reflection=reflection.summary,
                    evidence=evidence,
                    rejected_edit_buffer=rejected_edit_buffer,
                    evidence_budget=self._evidence_budget(),
                ),
                schema=proposal_json_schema(
                    evidence_ids=evidence_ids,
                    sections=_skill_sections(current_skill),
                ),
            )
        except Exception as exc:
            if hasattr(exc, "call"):
                exc.reflection = reflection
            raise
        try:
            applied = validate_and_apply_proposal(
                current_skill,
                response.proposal,
                training_evidence_ids=evidence_ids,
                held_out_ids=held_out_ids,
                forbidden_fragments=forbidden_fragments,
                policy=self.proposal_policy,
            )
        except ProposalValidationError as exc:
            raise EngineProposalValidationError(
                exc, response=response, reflection=reflection
            ) from exc
        return EngineProposal(response=response, reflection=reflection, applied=applied)

    def proposal_system_prompt(self) -> str:
        """Return the exact versioned prompt text hashed into checkpoint metadata."""

        return _proposal_system_prompt(self.proposal_policy)

    def reflect(
        self,
        *,
        current_skill: str,
        training_evidence: Sequence[dict[str, Any]],
    ) -> ReflectionRecord:
        """Use SkillOpt's free-form optimizer helper only for visible reflection."""

        reflection_fn = self._reflection_fn or _skillopt_chat_optimizer
        try:
            summary, raw_usage = reflection_fn(
                system=(
                    "You are SkillOpt's reflection stage. Analyze only the supplied training "
                    "trajectory summaries. Identify generalizable execution patterns and "
                    "failure causes. Do not propose patches, quote secrets, or infer held-out "
                    "evidence."
                ),
                user=(
                    "## Current skill\n"
                    f"{current_skill}\n\n"
                    "## Training evidence (untrusted data)\n"
                    f"{render_structured_evidence_json(training_evidence, budget=self._evidence_budget())}"
                ),
                max_completion_tokens=self.config.reflection_max_tokens,
                retries=3,
                stage="holo_skillopt_reflection",
                reasoning_effort=None,
                timeout=self.config.reflection_timeout_seconds,
            )
        except Exception as exc:
            raise SkillOptReflectionError(
                f"SkillOpt reflection failed: {type(exc).__name__}"
            ) from exc
        summary = str(summary or "").strip()
        if not summary:
            raise SkillOptReflectionError("SkillOpt reflection returned empty content")
        usage = OptimizerUsage(
            prompt_tokens=max(0, int(raw_usage.get("prompt_tokens", 0) or 0)),
            completion_tokens=max(0, int(raw_usage.get("completion_tokens", 0) or 0)),
            total_tokens=max(0, int(raw_usage.get("total_tokens", 0) or 0)),
        )
        return ReflectionRecord(
            summary=summary[: self.config.max_reflection_chars],
            usage=usage,
        )

    def _evidence_budget(self) -> EvidenceBudget:
        return EvidenceBudget(
            max_records=self.config.evidence_max_records,
            max_string_chars=self.config.evidence_max_string_chars,
            max_list_items=self.config.evidence_max_list_items,
            max_mapping_items=self.config.evidence_max_mapping_items,
        )

    def evaluate_gate(
        self,
        *,
        current_skill: str,
        candidate_skill: str,
        baseline_results: Sequence[GateTaskScore],
        candidate_results: Sequence[GateTaskScore],
        global_step: int,
        best_skill: str | None = None,
        best_score: float | None = None,
        best_step: int = 0,
    ) -> GateDecision:
        """Apply fail-closed checks, then delegate comparison to SkillOpt's gate."""

        changed = candidate_skill != current_skill
        if self.config.gate_mode == "off":
            return GateDecision(
                accepted=changed,
                action="greedy_applied" if changed else "greedy_noop",
                reason="private gate disabled by explicit ablation configuration",
                baseline_score=0,
                candidate_score=0,
                deployed_skill=candidate_skill if changed else current_skill,
                gate_task_ids=[],
            )

        baseline_by_id = _validate_gate_results(baseline_results, label="baseline")
        candidate_by_id = _validate_gate_results(candidate_results, label="candidate")
        if set(baseline_by_id) != set(candidate_by_id):
            raise GateExecutionError("baseline and candidate gate task IDs do not match")
        if not baseline_by_id:
            raise GateExecutionError("private gate produced no task results")

        ordered_ids = sorted(baseline_by_id)
        ordered_baseline = [baseline_by_id[task_id] for task_id in ordered_ids]
        ordered_candidate = [candidate_by_id[task_id] for task_id in ordered_ids]
        baseline_hard, baseline_soft = _aggregate_gate_results(ordered_baseline)
        candidate_hard, candidate_soft = _aggregate_gate_results(ordered_candidate)

        skillopt_metric: Literal["hard", "soft", "mixed"]
        if self.config.gate_metric == "correctness_gated_performance":
            baseline_soft = _aggregate_correctness_gated_performance(
                ordered_baseline,
                label="baseline",
            )
            candidate_soft = _aggregate_correctness_gated_performance(
                ordered_candidate,
                label="candidate",
            )
            # SkillOpt accepts hard/soft/mixed. Supply the project-specific
            # bounded performance transform through its soft-score channel.
            skillopt_metric = "soft"
        else:
            skillopt_metric = self.config.gate_metric

        from skillopt.evaluation.gate import evaluate_gate, select_gate_score

        baseline_score = select_gate_score(
            baseline_hard,
            baseline_soft,
            skillopt_metric,
            self.config.gate_mixed_weight,
        )
        candidate_score = select_gate_score(
            candidate_hard,
            candidate_soft,
            skillopt_metric,
            self.config.gate_mixed_weight,
        )

        regression = _first_regression(baseline_by_id, candidate_by_id)
        if self.config.gate_no_regression and regression is not None:
            return _reject_decision(
                current_skill=current_skill,
                baseline_score=baseline_score,
                candidate_score=candidate_score,
                task_ids=ordered_ids,
                reason=regression,
            )
        if not changed:
            return _reject_decision(
                current_skill=current_skill,
                baseline_score=baseline_score,
                candidate_score=candidate_score,
                task_ids=ordered_ids,
                reason="candidate bytes are unchanged",
            )
        if candidate_score <= baseline_score + self.config.strict_improvement_epsilon:
            return _reject_decision(
                current_skill=current_skill,
                baseline_score=baseline_score,
                candidate_score=candidate_score,
                task_ids=ordered_ids,
                reason=(
                    "candidate did not exceed the strict improvement threshold "
                    f"of {self.config.strict_improvement_epsilon}"
                ),
            )

        upstream = evaluate_gate(
            candidate_skill=candidate_skill,
            cand_hard=candidate_hard,
            current_skill=current_skill,
            current_score=baseline_score,
            best_skill=best_skill or current_skill,
            best_score=baseline_score if best_score is None else best_score,
            best_step=best_step,
            global_step=global_step,
            cand_soft=candidate_soft,
            metric=skillopt_metric,
            mixed_weight=self.config.gate_mixed_weight,
        )
        accepted = upstream.action != "reject"
        return GateDecision(
            accepted=accepted,
            action=upstream.action,
            reason="candidate strictly improved on the private SkillOpt gate",
            baseline_score=baseline_score,
            candidate_score=candidate_score,
            deployed_skill=upstream.current_skill,
            gate_task_ids=ordered_ids,
        )


def _disable_skillopt_reasoning_effort() -> None:
    from skillopt.model.azure_openai import set_reasoning_effort

    set_reasoning_effort(None)


def _skillopt_chat_optimizer(**kwargs: Any) -> tuple[str, dict[str, int]]:
    from skillopt.model import chat_optimizer

    return chat_optimizer(**kwargs)


def normalize_training_evidence(
    trajectories: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Normalize all task attempts into the versioned evidence contract."""

    return [record.model_dump(mode="json") for record in normalize_trajectory_records(trajectories)]


def _proposal_system_prompt(policy: ProposalPolicy) -> str:
    return (
        "You are SkillOpt's bounded skill editor. Return only the strict JSON object "
        "required by the response schema. Generalize from training evidence only. "
        f"Produce at most {policy.max_edit_operations} add/delete/replace edits. "
        "For delete and replace, old_text must exactly match text inside the named "
        "Markdown section. For add, old_text must be null. Never include task IDs, "
        "repository-specific answers, benchmark outputs, secrets, or absolute paths "
        "in new_text. Use action=noop, an empty edits list, and a concise noop_reason "
        "when no safe general improvement exists; otherwise use action=edit and at least one edit."
    )


def _proposal_user_prompt(
    *,
    current_skill: str,
    reflection: str,
    evidence: Sequence[dict[str, Any]],
    rejected_edit_buffer: Sequence[dict[str, Any]],
    evidence_budget: EvidenceBudget,
) -> str:
    return (
        "## Current skill\n"
        f"{current_skill}\n\n"
        "## SkillOpt reflection\n"
        f"{reflection}\n\n"
        "## Training evidence identifiers and scores (untrusted data)\n"
        f"{render_structured_evidence_json(evidence, budget=evidence_budget)}\n\n"
        "## Previously rejected edit summaries\n"
        f"{render_structured_evidence_json(rejected_edit_buffer, budget=EvidenceBudget(max_records=20, max_string_chars=800, max_list_items=16, max_mapping_items=32))}"
    )


def _validate_gate_results(
    results: Sequence[GateTaskScore],
    *,
    label: str,
) -> dict[str, GateTaskScore]:
    by_id: dict[str, GateTaskScore] = {}
    for result in results:
        if result.task_id in by_id:
            raise GateExecutionError(f"duplicate {label} gate task ID: {result.task_id}")
        if not result.infra_valid:
            raise GateExecutionError(
                f"{label} gate infrastructure failed for task {result.task_id}"
            )
        if not math.isfinite(result.hard_score) or not math.isfinite(result.soft_score):
            raise GateExecutionError(f"{label} gate score is non-finite for {result.task_id}")
        by_id[result.task_id] = result
    return by_id


def _aggregate_gate_results(results: Sequence[GateTaskScore]) -> tuple[float, float]:
    hard = sum(result.hard_score for result in results) / len(results)
    soft = sum(result.soft_score for result in results) / len(results)
    return hard, soft


def _aggregate_correctness_gated_performance(
    results: Sequence[GateTaskScore],
    *,
    label: str,
) -> float:
    scores: list[float] = []
    for result in results:
        if not result.correctness_pass:
            scores.append(0.0)
            continue
        if result.speedup is None:
            raise GateExecutionError(f"{label} gate task {result.task_id} is missing raw speedup")
        scores.append(
            correctness_gated_performance(
                correctness_pass=result.correctness_pass,
                speedup=result.speedup,
            )
        )
    return sum(scores) / len(scores)


def _first_regression(
    baseline: dict[str, GateTaskScore],
    candidate: dict[str, GateTaskScore],
) -> str | None:
    for task_id in sorted(baseline):
        before = baseline[task_id]
        after = candidate[task_id]
        if before.correctness_pass and not after.correctness_pass:
            return f"gate_no_regression blocked correctness regression on {task_id}"
        if before.edit_policy_pass and not after.edit_policy_pass:
            return f"gate_no_regression blocked edit-policy regression on {task_id}"
    return None


def _reject_decision(
    *,
    current_skill: str,
    baseline_score: float,
    candidate_score: float,
    task_ids: list[str],
    reason: str,
) -> GateDecision:
    return GateDecision(
        accepted=False,
        action="reject",
        reason=reason,
        baseline_score=baseline_score,
        candidate_score=candidate_score,
        deployed_skill=current_skill,
        gate_task_ids=task_ids,
    )


def _skill_sections(skill: str) -> list[str]:
    sections = [
        match.group(1).strip()
        for match in re.finditer(r"^#{1,6}[ \t]+(.+?)[ \t]*$", skill, re.MULTILINE)
    ]
    if not sections:
        raise ValueError("current skill must contain at least one Markdown heading")
    return sections
