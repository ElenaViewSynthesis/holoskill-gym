from __future__ import annotations

from pathlib import Path

from seagym.logging.redaction import redact_sensitive
from seagym.trainers.checkpoint import TrainerState, write_checkpoint_manifest


def test_numeric_token_usage_survives_redaction_but_credentials_do_not() -> None:
    redacted = redact_sensitive(
        {
            "input_tokens": 12,
            "completion_tokens": 7,
            "total_tokens": 19,
            "access_token": "secret-value",
            "authorization": "Bearer secret-value",
            "nested": {"API_KEY": "secret-value"},
        }
    )

    assert redacted["input_tokens"] == 12
    assert redacted["completion_tokens"] == 7
    assert redacted["total_tokens"] == 19
    assert redacted["access_token"] == "<redacted>"
    assert redacted["authorization"] == "<redacted>"
    assert redacted["nested"]["API_KEY"] == "<redacted>"


def test_checkpoint_manifest_redacts_nested_agent_environment(tmp_path: Path) -> None:
    secret = "sk-test-checkpoint-secret"
    state = TrainerState(
        epoch=1,
        train_batch_index=1,
        global_step=1,
        updates_completed=1,
        num_train_tasks_seen=1,
        previous_update_validation_results=[
            {
                "refs": {
                    "command": [
                        "harbor",
                        "run",
                        "--agent-env",
                        f"OPENAI_API_KEY={secret}",
                    ]
                }
            }
        ],
    )

    manifest = write_checkpoint_manifest(
        tmp_path,
        checkpoint_id="epoch_0001",
        checkpoint_type="epoch",
        run_id="run-1",
        experiment_id="experiment-1",
        trainer_state=state,
    )

    persisted = (tmp_path / "checkpoint.json").read_text(encoding="utf-8")
    command = manifest["trainer_state"]["previous_update_validation_results"][0]["refs"]["command"]
    assert secret not in persisted
    assert command[-1] == "OPENAI_API_KEY=<redacted>"
