from __future__ import annotations

import pytest
from pydantic import ValidationError

from holoskill_gym.schemas import SkillEdit, SkillUpdateProposal


def _edit(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "operation": "add",
        "section": "Verify",
        "old_text": None,
        "new_text": "Measure the changed path twice.",
        "rationale": "The trace skipped repeat measurement.",
        "evidence_ids": ["train-1"],
    }
    values.update(overrides)
    return values


def test_proposal_schema_accepts_valid_strict_output() -> None:
    proposal = SkillUpdateProposal.model_validate(
        {
            "diagnosis": ["Verification was incomplete."],
            "edits": [_edit()],
            "expected_effects": ["More reliable measurements."],
            "risks": ["Longer task runtime."],
        }
    )

    assert proposal.edits[0].operation == "add"
    schema = SkillUpdateProposal.model_json_schema()
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["SkillEdit"]["additionalProperties"] is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"operation": "add", "old_text": "unexpected"},
        {"operation": "delete", "old_text": None},
        {"operation": "replace", "old_text": "same", "new_text": "same"},
    ],
)
def test_edit_operation_fields_are_consistent(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        SkillEdit.model_validate(_edit(**overrides))


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        SkillEdit.model_validate(_edit(unexpected=True))
