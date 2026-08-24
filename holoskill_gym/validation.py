"""Semantic validation and atomic application of skill update proposals."""

from __future__ import annotations

import re
from collections.abc import Callable, Collection
from dataclasses import dataclass

from .schemas import SkillEdit, SkillUpdateProposal

_HEADING_RE = re.compile(r"^(?P<marks>#{1,6})[ \t]+(?P<title>.+?)[ \t]*$", re.MULTILINE)
_SECRET_PATTERNS = (
    re.compile(r"\b(?:sk|sk-proj|api|token)-[A-Za-z0-9_-]{12,}\b", re.IGNORECASE),
    re.compile(r"\b(?:api[_-]?key|access[_-]?token|authorization)\s*[:=]", re.IGNORECASE),
    re.compile(r"\bbearer\s+[A-Za-z0-9._~+/=-]{12,}\b", re.IGNORECASE),
)
_ABSOLUTE_PATH_PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9_])/(?:home|Users|mnt|tmp|var|opt|root)/[^\s`]+"),
    re.compile(r"\b[A-Za-z]:\\[^\s`]+"),
)


class ProposalValidationError(ValueError):
    """Raised when a parsed proposal violates local edit policy."""

    def __init__(self, errors: Collection[str]):
        self.errors = tuple(errors)
        super().__init__("; ".join(self.errors))


@dataclass(frozen=True)
class ProposalPolicy:
    """Local constraints that structured output alone cannot guarantee."""

    max_edit_operations: int = 3
    max_skill_tokens: int = 2_000
    max_skill_chars: int = 12_000

    def __post_init__(self) -> None:
        if self.max_edit_operations < 0:
            raise ValueError("max_edit_operations must be non-negative")
        if self.max_skill_tokens <= 0:
            raise ValueError("max_skill_tokens must be positive")
        if self.max_skill_chars <= 0:
            raise ValueError("max_skill_chars must be positive")


@dataclass(frozen=True)
class AppliedProposal:
    """Result of validating and atomically applying a proposal."""

    skill: str
    changed: bool
    edit_count: int


def validate_and_apply_proposal(
    current_skill: str,
    proposal: SkillUpdateProposal,
    *,
    training_evidence_ids: Collection[str],
    held_out_ids: Collection[str] = (),
    forbidden_fragments: Collection[str] = (),
    policy: ProposalPolicy | None = None,
    token_counter: Callable[[str], int] | None = None,
) -> AppliedProposal:
    """Validate every edit, then return the fully applied skill or raise.

    Application is atomic: this function never exposes a partially edited skill.
    Each edit targets exactly one occurrence inside an exact Markdown section.
    """

    policy = policy or ProposalPolicy()
    training_ids = set(training_evidence_ids)
    held_out = set(held_out_ids)
    errors: list[str] = []

    if len(proposal.edits) > policy.max_edit_operations:
        errors.append(
            f"proposal contains {len(proposal.edits)} edits; maximum is "
            f"{policy.max_edit_operations}"
        )

    for index, edit in enumerate(proposal.edits):
        prefix = f"edit[{index}]"
        unknown = sorted(set(edit.evidence_ids) - training_ids)
        if unknown:
            errors.append(f"{prefix} references evidence outside the training batch: {unknown}")
        leaked = sorted(set(edit.evidence_ids) & held_out)
        if leaked:
            errors.append(f"{prefix} references held-out evidence: {leaked}")
        errors.extend(
            _content_policy_errors(edit, prefix, training_ids | held_out, forbidden_fragments)
        )

    if errors:
        raise ProposalValidationError(errors)

    candidate = current_skill
    for index, edit in enumerate(proposal.edits):
        try:
            candidate = _apply_edit(candidate, edit)
        except ProposalValidationError as exc:
            errors.extend(f"edit[{index}] {message}" for message in exc.errors)

    if errors:
        raise ProposalValidationError(errors)

    if len(candidate) > policy.max_skill_chars:
        errors.append(
            f"candidate skill contains {len(candidate)} characters; maximum is "
            f"{policy.max_skill_chars}"
        )
    count_tokens = token_counter or _conservative_token_count
    token_count = count_tokens(candidate)
    if token_count > policy.max_skill_tokens:
        errors.append(
            f"candidate skill contains {token_count} tokens; maximum is {policy.max_skill_tokens}"
        )
    if errors:
        raise ProposalValidationError(errors)

    return AppliedProposal(
        skill=candidate,
        changed=candidate != current_skill,
        edit_count=len(proposal.edits),
    )


def _content_policy_errors(
    edit: SkillEdit,
    prefix: str,
    task_ids: Collection[str],
    forbidden_fragments: Collection[str],
) -> list[str]:
    errors: list[str] = []
    candidate_text = "\n".join(
        part for part in (edit.section, edit.new_text, edit.rationale) if part is not None
    )
    for pattern in (*_SECRET_PATTERNS, *_ABSOLUTE_PATH_PATTERNS):
        if pattern.search(candidate_text):
            errors.append(f"{prefix} contains secret-shaped material or an absolute path")
            break
    for task_id in sorted(task_ids, key=len, reverse=True):
        if task_id and edit.new_text and task_id in edit.new_text:
            errors.append(f"{prefix} injects task identifier {task_id!r} into the skill")
    for fragment in forbidden_fragments:
        if fragment and edit.new_text and fragment in edit.new_text:
            errors.append(f"{prefix} injects forbidden benchmark or repository material")
    return errors


def _apply_edit(skill: str, edit: SkillEdit) -> str:
    start, end = _section_content_bounds(skill, edit.section)
    section_text = skill[start:end]

    if edit.operation == "add":
        addition = _normalize_block(edit.new_text or "")
        separator = "" if not section_text or section_text.endswith("\n\n") else "\n"
        return skill[:end] + separator + addition + skill[end:]

    old_text = edit.old_text or ""
    occurrences = section_text.count(old_text)
    if occurrences != 1:
        raise ProposalValidationError(
            [
                (
                    f"requires exactly one exact old_text match in section {edit.section!r}; "
                    f"found {occurrences}"
                )
            ]
        )
    relative_index = section_text.index(old_text)
    absolute_index = start + relative_index
    replacement = "" if edit.operation == "delete" else (edit.new_text or "")
    return skill[:absolute_index] + replacement + skill[absolute_index + len(old_text) :]


def _section_content_bounds(skill: str, requested_section: str) -> tuple[int, int]:
    requested = requested_section.strip()
    headings = list(_HEADING_RE.finditer(skill))
    matches = [match for match in headings if match.group("title").strip() == requested]
    if len(matches) != 1:
        raise ProposalValidationError(
            [f"requires exactly one Markdown section named {requested!r}; found {len(matches)}"]
        )
    match = matches[0]
    level = len(match.group("marks"))
    start = match.end()
    if start < len(skill) and skill[start] == "\n":
        start += 1
    end = len(skill)
    for following in headings:
        if following.start() <= match.start():
            continue
        if len(following.group("marks")) <= level:
            end = following.start()
            break
    return start, end


def _normalize_block(text: str) -> str:
    return text.strip("\n") + "\n"


def _conservative_token_count(text: str) -> int:
    """Provider-independent upper-biased approximation for policy enforcement."""

    return len(re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE))
