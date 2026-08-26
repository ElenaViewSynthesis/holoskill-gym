"""Provider-neutral schemas for bounded skill updates and optimizer accounting."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """Base model whose JSON schema is suitable for strict structured output."""

    # Skill documents and exact-match edit operands are byte-sensitive.  Do not
    # enable Pydantic's global whitespace stripping here: doing so would mutate
    # both gate decisions and delete/replace targets during validation.
    model_config = ConfigDict(extra="forbid")


class SkillEdit(StrictModel):
    """One bounded edit to a named Markdown section in the skill document."""

    operation: Literal["add", "delete", "replace"]
    section: str = Field(min_length=1)
    old_text: str | None
    new_text: str | None
    rationale: str = Field(min_length=1)
    evidence_ids: list[str]

    @model_validator(mode="after")
    def validate_operation_fields(self) -> SkillEdit:
        if self.operation == "add":
            if self.old_text is not None:
                raise ValueError("add edits must set old_text to null")
            if not self.new_text:
                raise ValueError("add edits require non-empty new_text")
        elif self.operation == "delete":
            if not self.old_text:
                raise ValueError("delete edits require non-empty old_text")
            if self.new_text not in (None, ""):
                raise ValueError("delete edits must set new_text to null or an empty string")
        else:
            if not self.old_text or not self.new_text:
                raise ValueError("replace edits require non-empty old_text and new_text")
            if self.old_text == self.new_text:
                raise ValueError("replace edits must change the selected text")
        return self


class SkillUpdateProposal(StrictModel):
    """Schema-constrained proposal returned by the optimizer."""

    diagnosis: list[str]
    edits: list[SkillEdit]
    expected_effects: list[str]
    risks: list[str]


class OptimizerUsage(StrictModel):
    """Token usage for exactly one optimizer request."""

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class OptimizerCallRecord(StrictModel):
    """Auditable metadata for a provider call, excluding prompts and secrets."""

    provider: str
    model: str
    latency_ms: float = Field(ge=0)
    attempts: int = Field(ge=1)
    response_id: str | None = None
    finish_reason: str | None = None
    usage: OptimizerUsage = Field(default_factory=OptimizerUsage)


class ProposalResponse(StrictModel):
    """A parsed proposal paired with its optimizer accounting record."""

    proposal: SkillUpdateProposal
    call: OptimizerCallRecord


class ReflectionRecord(StrictModel):
    """Visible SkillOpt reflection output and its token usage."""

    summary: str
    usage: OptimizerUsage = Field(default_factory=OptimizerUsage)


class GateTaskScore(StrictModel):
    """One private gate task result for a single skill version."""

    task_id: str = Field(min_length=1)
    hard_score: float = Field(ge=0, le=1)
    soft_score: float = Field(ge=0, le=1)
    correctness_pass: bool
    edit_policy_pass: bool
    infra_valid: bool
    speedup: float | None = Field(default=None, gt=0)
    error: str | None = None


class GateDecision(StrictModel):
    """Auditable SkillOpt gate decision."""

    accepted: bool
    action: Literal["accept_new_best", "accept", "reject", "greedy_applied", "greedy_noop"]
    reason: str
    baseline_score: float
    candidate_score: float
    deployed_skill: str
    gate_task_ids: list[str]
