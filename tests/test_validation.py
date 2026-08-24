from __future__ import annotations

import pytest

from holoskill_gym.schemas import SkillUpdateProposal
from holoskill_gym.validation import (
    ProposalPolicy,
    ProposalValidationError,
    validate_and_apply_proposal,
)

SKILL = """# Optimizer Skill

## Measure
Run the benchmark once.

## Verify
Run the tests.
"""


def proposal(*edits: dict[str, object]) -> SkillUpdateProposal:
    return SkillUpdateProposal.model_validate(
        {
            "diagnosis": ["A measured weakness."],
            "edits": list(edits),
            "expected_effects": ["A measurable improvement."],
            "risks": ["Additional runtime."],
        }
    )


def edit(
    operation: str = "replace",
    *,
    section: str = "Measure",
    old_text: str | None = "Run the benchmark once.",
    new_text: str | None = "Run the benchmark three times and compare the median.",
    evidence_ids: list[str] | None = None,
) -> dict[str, object]:
    return {
        "operation": operation,
        "section": section,
        "old_text": old_text,
        "new_text": new_text,
        "rationale": "Training evidence shows noisy measurements.",
        "evidence_ids": evidence_ids or ["train-1"],
    }


def test_valid_replace_is_applied_atomically() -> None:
    result = validate_and_apply_proposal(
        SKILL,
        proposal(edit()),
        training_evidence_ids={"train-1"},
    )

    assert result.changed is True
    assert "three times" in result.skill
    assert "once" not in result.skill


def test_add_targets_named_section() -> None:
    result = validate_and_apply_proposal(
        SKILL,
        proposal(
            edit(
                "add",
                section="Verify",
                old_text=None,
                new_text="Re-run the benchmark after tests pass.",
            )
        ),
        training_evidence_ids={"train-1"},
    )

    assert "Re-run the benchmark" in result.skill
    assert result.skill.index("Re-run the benchmark") > result.skill.index("## Verify")


def test_more_than_maximum_edits_is_rejected() -> None:
    with pytest.raises(ProposalValidationError, match="maximum is 1"):
        validate_and_apply_proposal(
            SKILL,
            proposal(edit(), edit()),
            training_evidence_ids={"train-1"},
            policy=ProposalPolicy(max_edit_operations=1),
        )


def test_replace_requires_one_exact_match_in_named_section() -> None:
    with pytest.raises(ProposalValidationError, match="found 0"):
        validate_and_apply_proposal(
            SKILL,
            proposal(edit(old_text="Run a benchmark once.")),
            training_evidence_ids={"train-1"},
        )


def test_unknown_or_held_out_evidence_is_rejected() -> None:
    with pytest.raises(ProposalValidationError) as exc_info:
        validate_and_apply_proposal(
            SKILL,
            proposal(edit(evidence_ids=["held-out-1"])),
            training_evidence_ids={"train-1"},
            held_out_ids={"held-out-1"},
        )

    assert "outside the training batch" in str(exc_info.value)
    assert "held-out evidence" in str(exc_info.value)


@pytest.mark.parametrize(
    "new_text",
    [
        "Use token sk-proj-this-is-definitely-secret.",
        "Read /home/user/private/results.json.",
        "Memorize the answer for train-1.",
        "Always return benchmark-output-42.",
    ],
)
def test_sensitive_or_task_specific_content_is_rejected(new_text: str) -> None:
    with pytest.raises(ProposalValidationError):
        validate_and_apply_proposal(
            SKILL,
            proposal(edit(new_text=new_text)),
            training_evidence_ids={"train-1"},
            forbidden_fragments={"benchmark-output-42"},
        )


def test_empty_edit_list_is_a_no_op() -> None:
    result = validate_and_apply_proposal(
        SKILL,
        proposal(),
        training_evidence_ids={"train-1"},
    )

    assert result.changed is False
    assert result.skill == SKILL


def test_final_skill_budget_is_enforced() -> None:
    with pytest.raises(ProposalValidationError, match="tokens"):
        validate_and_apply_proposal(
            SKILL,
            proposal(edit()),
            training_evidence_ids={"train-1"},
            policy=ProposalPolicy(max_skill_tokens=3),
        )
