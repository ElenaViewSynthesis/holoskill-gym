"""Provider-neutral schemas for bounded skill updates and optimizer accounting."""

from __future__ import annotations

from copy import deepcopy
from typing import Annotated, Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


class StrictModel(BaseModel):
    """Base model whose JSON schema is suitable for strict structured output."""

    # Skill documents and exact-match edit operands are byte-sensitive.  Do not
    # enable Pydantic's global whitespace stripping here: doing so would mutate
    # both gate decisions and delete/replace targets during validation.
    model_config = ConfigDict(extra="forbid")


ShortText = Annotated[str, StringConstraints(min_length=1, max_length=1_000)]
SectionName = Annotated[str, StringConstraints(min_length=1, max_length=200)]
EditText = Annotated[str, StringConstraints(min_length=1, max_length=12_000)]
EvidenceId = Annotated[str, StringConstraints(min_length=1, max_length=512)]


class EditBase(StrictModel):
    """Fields shared by every discriminated edit variant."""

    section: SectionName
    rationale: ShortText
    evidence_ids: list[EvidenceId] = Field(min_length=1, max_length=16)


class AddEdit(EditBase):
    operation: Literal["add"]
    old_text: None
    new_text: EditText


class DeleteEdit(EditBase):
    operation: Literal["delete"]
    old_text: EditText
    new_text: None


class ReplaceEdit(EditBase):
    operation: Literal["replace"]
    old_text: EditText
    new_text: EditText

    @model_validator(mode="after")
    def require_changed_text(self) -> ReplaceEdit:
        if self.old_text == self.new_text:
            raise ValueError("replace edits must change the selected text")
        return self


SkillEdit = Annotated[AddEdit | DeleteEdit | ReplaceEdit, Field(discriminator="operation")]


class SkillUpdateProposal(StrictModel):
    """Schema-constrained proposal returned by the optimizer."""

    schema_version: Literal["2"]
    action: Literal["edit", "noop"]
    diagnosis: list[ShortText] = Field(min_length=1, max_length=8)
    edits: list[SkillEdit] = Field(max_length=3)
    noop_reason: ShortText | None
    expected_effects: list[ShortText] = Field(max_length=8)
    risks: list[ShortText] = Field(max_length=8)

    @model_validator(mode="after")
    def validate_envelope(self) -> SkillUpdateProposal:
        if self.action == "edit":
            if not self.edits:
                raise ValueError("edit proposals require at least one edit")
            if self.noop_reason is not None:
                raise ValueError("edit proposals must set noop_reason to null")
        else:
            if self.edits:
                raise ValueError("noop proposals must have an empty edit list")
            if self.noop_reason is None:
                raise ValueError("noop proposals require noop_reason")
        return self


def proposal_json_schema(
    *, evidence_ids: list[str] | tuple[str, ...], sections: list[str] | tuple[str, ...]
) -> dict[str, Any]:
    """Return a strict batch-specific schema with closed evidence and section enums."""

    if not evidence_ids:
        raise ValueError("proposal schema requires at least one evidence ID")
    if not sections:
        raise ValueError("proposal schema requires at least one skill section")
    schema = deepcopy(SkillUpdateProposal.model_json_schema())
    for definition in ("AddEdit", "DeleteEdit", "ReplaceEdit"):
        properties = schema["$defs"][definition]["properties"]
        properties["section"] = {"enum": sorted(set(sections)), "type": "string"}
        properties["evidence_ids"]["items"] = {
            "enum": sorted(set(evidence_ids)),
            "type": "string",
        }
    return schema


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


@runtime_checkable
class ProposalBackend(Protocol):
    """The contract an optimizer backend must satisfy to drive skill mutation.

    Holo and Inkling are peers: either may fill the optimizer role, and the
    engine is written against this protocol rather than against a concrete
    provider. A backend is responsible for issuing one strict schema request
    and returning a parsed proposal with its accounting record; semantic edit
    policy is enforced locally afterwards regardless of which one is used.
    """

    @property
    def config(self) -> BackendIdentity: ...

    def propose(
        self, *, system: str, user: str, schema: dict[str, Any] | None = None
    ) -> ProposalResponse: ...


class BackendIdentity(Protocol):
    """The identity fields every backend config exposes for checkpoint metadata."""

    model: str
