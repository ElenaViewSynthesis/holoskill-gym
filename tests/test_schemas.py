from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from holoskill_gym.schemas import SkillEdit, SkillUpdateProposal, proposal_json_schema

EDIT_ADAPTER = TypeAdapter(SkillEdit)


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
            "schema_version": "2",
            "action": "edit",
            "diagnosis": ["Verification was incomplete."],
            "edits": [_edit()],
            "noop_reason": None,
            "expected_effects": ["More reliable measurements."],
            "risks": ["Longer task runtime."],
        }
    )

    assert proposal.edits[0].operation == "add"
    schema = SkillUpdateProposal.model_json_schema()
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["AddEdit"]["additionalProperties"] is False


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
        EDIT_ADAPTER.validate_python(_edit(**overrides))


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        EDIT_ADAPTER.validate_python(_edit(unexpected=True))


def test_versioned_noop_and_edit_envelopes_fail_closed() -> None:
    base = {
        "schema_version": "2",
        "diagnosis": ["No safe edit is supported."],
        "expected_effects": [],
        "risks": [],
    }
    noop = SkillUpdateProposal.model_validate(
        {**base, "action": "noop", "edits": [], "noop_reason": "Evidence is inconclusive."}
    )
    assert noop.action == "noop"
    with pytest.raises(ValidationError):
        SkillUpdateProposal.model_validate(
            {**base, "action": "edit", "edits": [], "noop_reason": None}
        )


def test_batch_schema_closes_evidence_and_section_values() -> None:
    schema = proposal_json_schema(evidence_ids=["train-1"], sections=["Measure"])
    for definition in ("AddEdit", "DeleteEdit", "ReplaceEdit"):
        properties = schema["$defs"][definition]["properties"]
        assert properties["section"]["enum"] == ["Measure"]
        assert properties["evidence_ids"]["items"]["enum"] == ["train-1"]
