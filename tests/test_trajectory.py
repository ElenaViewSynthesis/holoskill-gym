from __future__ import annotations

import json

from holoskill_gym.trajectory import (
    EvidenceBudget,
    normalize_trajectory_records,
    render_structured_evidence_json,
)


def _write_trial(tmp_path, *, valid: bool = True):
    trial = tmp_path / "trial"
    agent = trial / "agent"
    agent.mkdir(parents=True)
    result_path = trial / "result.json"
    result_path.write_text("{}\n", encoding="utf-8")
    if valid:
        trajectory = {
            "schema_version": "ATIF-v1.7",
            "session_id": "session-1",
            "agent": {
                "name": "codex",
                "version": "1",
                "model_name": "gpt-test",
            },
            "steps": [
                {
                    "step_id": 1,
                    "source": "user",
                    "message": "Optimize safely. Authorization: Bearer secret-token",
                },
                {
                    "step_id": 2,
                    "source": "agent",
                    "message": "(tool use)",
                    "reasoning_content": "hidden chain of thought must not persist",
                    "tool_calls": [
                        {
                            "tool_call_id": "call-1",
                            "function_name": "exec_command",
                            "arguments": {"cmd": "pytest", "secret": "do-not-copy"},
                        }
                    ],
                    "observation": {
                        "results": [
                            {
                                "source_call_id": "call-1",
                                "content": "large raw command output is not copied",
                            }
                        ]
                    },
                },
            ],
            "final_metrics": {
                "total_prompt_tokens": 11,
                "total_completion_tokens": 7,
                "total_cost_usd": 0.25,
            },
        }
    else:
        trajectory = {"schema_version": "not-atif", "steps": []}
    (agent / "trajectory.json").write_text(
        json.dumps(trajectory),
        encoding="utf-8",
    )
    return result_path


def test_normalization_validates_atif_redacts_and_avoids_hidden_reasoning(tmp_path) -> None:
    result_path = _write_trial(tmp_path)
    raw = {
        "task_id": "task-1",
        "attempt_id": "attempt-a",
        "view_name": "train",
        "mode": "train",
        "success": True,
        "score": 1.0,
        "rewards": {"reward": 1.0},
        "cost": {},
        "custom_signal": {"count": 3},
        "reasoning_content": "must be omitted",
        "refs": {
            "result_path": str(result_path),
            "agent_id": "codex",
            "harbor_stdout": "must be an artifact, not inline evidence",
        },
    }

    record = normalize_trajectory_records([raw])[0]
    rendered = record.model_dump_json()

    assert record.atif_valid is True
    assert record.executor == "codex"
    assert record.model == "gpt-test"
    assert record.sanitized_prompt.endswith("Bearer [REDACTED]")
    assert record.action_summaries[0].function_name == "exec_command"
    assert record.action_summaries[0].argument_keys == ["cmd", "secret"]
    assert record.usage.input_tokens == 11
    assert record.usage.output_tokens == 7
    assert record.usage.tool_calls == 1
    assert record.usage.cost_usd == 0.25
    assert record.extra["holoskill_gym"]["source_fields"]["custom_signal"] == {"count": 3}
    assert "hidden chain of thought" not in rendered
    assert "large raw command output" not in rendered
    assert "must be an artifact" not in rendered
    assert record.artifact_paths["atif_trajectory"].endswith("agent/trajectory.json")


def test_duplicate_task_ids_receive_stable_attempt_evidence_ids() -> None:
    raw = {
        "task_id": "task-1",
        "view_name": "train",
        "mode": "train",
        "success": False,
        "score": 0.0,
        "rewards": {},
    }
    records = normalize_trajectory_records(
        [
            {**raw, "attempt_id": "one"},
            {**raw, "attempt_id": "two"},
        ]
    )

    assert [record.evidence_id for record in records] == [
        "task-1::attempt::one",
        "task-1::attempt::two",
    ]
    assert [record.attempt_index for record in records] == [0, 1]
    assert all(record.attempt_count == 2 for record in records)


def test_invalid_atif_is_not_consumed_as_valid_evidence(tmp_path) -> None:
    result_path = _write_trial(tmp_path, valid=False)
    record = normalize_trajectory_records(
        [
            {
                "task_id": "task-1",
                "view_name": "train",
                "mode": "train",
                "success": True,
                "score": 1.0,
                "rewards": {"reward": 1.0},
                "refs": {"result_path": str(result_path)},
            }
        ]
    )[0]

    assert record.atif_valid is False
    assert record.terminal_status == "agent_error"
    assert record.action_summaries == []
    assert record.error == "invalid ATIF trajectory: ValidationError"


def test_structural_budgets_always_emit_valid_json_and_elision_counts() -> None:
    rendered = render_structured_evidence_json(
        [
            {"task_id": "one", "details": "x" * 50, "values": list(range(8))},
            {"task_id": "two", "details": "y" * 50},
        ],
        budget=EvidenceBudget(
            max_records=1,
            max_string_chars=10,
            max_list_items=3,
            max_mapping_items=8,
        ),
    )
    payload = json.loads(rendered)

    assert payload["total_records"] == 2
    assert payload["included_records"] == 1
    assert payload["omitted_records"] == 1
    assert payload["records"][0]["record"]["details"] == "x" * 10
    assert payload["records"][0]["record"]["values"] == [0, 1, 2]
    reasons = {item["reason"] for item in payload["records"][0]["field_elisions"]}
    assert reasons == {"max_string_chars", "max_list_items"}
