import json

import pytest

import holoskill_gym.state as state_module
from holoskill_gym.schemas import GateDecision, OptimizerUsage
from holoskill_gym.state import StateIntegrityError, StateStore


def metadata() -> dict[str, object]:
    return {
        "skillopt_version": "0.2.0",
        "seagym_version": "0.1.0",
        "harbor_version": "0.1.0",
        "source_revisions": {
            "project": {"commit": "project123", "dirty": True},
            "skillopt": {"commit": "abc123", "dirty": False},
            "seagym": {"commit": "def456", "dirty": True},
            "harbor": {"commit": "harbor789", "dirty": False},
        },
        "holo_model_id": "holo3-1-35b-a3b",
        "optimizer_prompt_hash": "prompt-hash",
        "target_executor": "codex_exec",
        "gate_mode": "on",
        "task_split_hashes": {"skillopt_train": "train-hash"},
        "input_hashes": {"initial_skill": "initial-hash"},
    }


def accepted(skill: str) -> GateDecision:
    return GateDecision(
        accepted=True,
        action="accept_new_best",
        reason="improved",
        baseline_score=0.5,
        candidate_score=0.7,
        deployed_skill=skill,
        gate_task_ids=["gate-1"],
    )


def test_state_round_trip_and_atomic_commit(tmp_path) -> None:
    store = StateStore(tmp_path / "state")
    prior = store.initialize(initial_skill="initial\n", metadata=metadata())

    updated = store.commit(
        prior=prior,
        update_index=1,
        deployed_skill="improved\n",
        status="accepted_by_skillopt_gate",
        optimizer_usage=OptimizerUsage(prompt_tokens=2, completion_tokens=3, total_tokens=5),
        gate_decision=accepted("improved\n"),
        proposal_record={"edits": ["bounded"]},
    )

    assert store.read_skill() == "improved\n"
    assert store.load() == updated
    assert updated.skill_version == 1
    assert updated.accepted_count == 1
    assert updated.cumulative_optimizer_usage.total_tokens == 5
    assert len((tmp_path / "state" / "update_history.jsonl").read_text().splitlines()) == 1


def test_runtime_input_hashes_are_merged_without_changing_update_identity(tmp_path) -> None:
    store = StateStore(tmp_path)
    prior = store.initialize(initial_skill="initial\n", metadata=metadata())

    updated = store.update_input_hashes({"task_index": "task-hash"})

    assert updated.current_hash == prior.current_hash
    assert updated.last_committed_update == prior.last_committed_update
    assert updated.input_hashes == {
        "initial_skill": "initial-hash",
        "task_index": "task-hash",
    }


def test_schema_v1_state_is_migrated_and_rewritten(tmp_path) -> None:
    store = StateStore(tmp_path)
    skill = "initial\n"
    old_state = {
        "schema_version": "1",
        "skill_version": 0,
        "current_hash": state_module.skill_sha256(skill),
        "parent_hash": None,
        "skillopt_version": "0.2.0",
        "skillopt_commit": "abc123",
        "seagym_version": "0.1.0",
        "seagym_commit": "def456",
        "holo_model_id": "holo3-1-35b-a3b",
        "optimizer_prompt_hash": "prompt-hash",
        "target_executor": "codex_exec",
        "gate_mode": "on",
        "task_split_hashes": {"skillopt_train": "train-hash"},
        "accepted_count": 0,
        "rejected_count": 0,
        "cumulative_optimizer_usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
        "latest_update_status": "initialized",
        "last_committed_update": 0,
        "best_score": None,
        "best_step": 0,
    }
    store.skill_path.write_text(skill, encoding="utf-8")
    store.state_path.write_text(json.dumps(old_state), encoding="utf-8")

    migrated = store.load()

    assert migrated.schema_version == "2"
    assert migrated.source_revisions.skillopt.commit == "abc123"
    assert migrated.source_revisions.seagym.commit == "def456"
    assert migrated.source_revisions.harbor.commit == "unknown"
    assert migrated.input_hashes["initial_skill"] == state_module.skill_sha256(skill)
    assert json.loads(store.state_path.read_text(encoding="utf-8"))["schema_version"] == "2"


def test_unknown_state_schema_fails_closed(tmp_path) -> None:
    store = StateStore(tmp_path)
    store.skill_path.write_text("initial\n", encoding="utf-8")
    store.state_path.write_text('{"schema_version":"99"}', encoding="utf-8")

    with pytest.raises(StateIntegrityError, match="cannot load baseline state"):
        store.load()


def test_rejected_commit_keeps_skill_and_records_proposal(tmp_path) -> None:
    store = StateStore(tmp_path)
    prior = store.initialize(initial_skill="initial\n", metadata=metadata())
    decision = accepted("candidate\n").model_copy(
        update={"accepted": False, "action": "reject", "deployed_skill": "initial\n"}
    )

    updated = store.commit(
        prior=prior,
        update_index=1,
        deployed_skill="initial\n",
        status="rejected_by_skillopt_gate",
        optimizer_usage=OptimizerUsage(),
        gate_decision=decision,
        proposal_record={"diagnosis": ["x"]},
    )

    assert updated.current_hash == prior.current_hash
    assert updated.rejected_count == 1
    assert json.loads(store.rejected_path.read_text().splitlines()[0])["update_index"] == 1


def test_invalid_proposal_is_retained_for_the_next_optimizer_prompt(tmp_path) -> None:
    store = StateStore(tmp_path)
    prior = store.initialize(initial_skill="initial\n", metadata=metadata())

    store.commit(
        prior=prior,
        update_index=1,
        deployed_skill="initial\n",
        status="invalid_proposal",
        optimizer_usage=OptimizerUsage(),
        gate_decision=None,
        proposal_record={"edit_count": 1},
    )

    record = json.loads(store.rejected_path.read_text().splitlines()[0])
    assert record == {
        "update_index": 1,
        "status": "invalid_proposal",
        "proposal": {"edit_count": 1},
    }


def test_hash_mismatch_and_duplicate_commit_fail_closed(tmp_path) -> None:
    store = StateStore(tmp_path)
    prior = store.initialize(initial_skill="initial\n", metadata=metadata())
    store.skill_path.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(StateIntegrityError, match="hash mismatch"):
        store.load()

    store.skill_path.write_text("initial\n", encoding="utf-8")
    store.commit(
        prior=prior,
        update_index=1,
        deployed_skill="initial\n",
        status="no_op_proposal",
        optimizer_usage=OptimizerUsage(),
        gate_decision=None,
        proposal_record=None,
    )
    with pytest.raises(StateIntegrityError, match="already committed|changed since"):
        store.commit(
            prior=prior,
            update_index=1,
            deployed_skill="initial\n",
            status="no_op_proposal",
            optimizer_usage=OptimizerUsage(),
            gate_decision=None,
            proposal_record=None,
        )


def test_interrupted_commit_is_replayed_without_duplicate_history(tmp_path, monkeypatch) -> None:
    store = StateStore(tmp_path)
    prior = store.initialize(initial_skill="initial\n", metadata=metadata())
    real_write = state_module._atomic_write_text
    failed = False

    def interrupt_history(path, content):
        nonlocal failed
        if path == store.history_path and not failed:
            failed = True
            raise OSError("simulated crash")
        real_write(path, content)

    monkeypatch.setattr(state_module, "_atomic_write_text", interrupt_history)
    with pytest.raises(OSError, match="simulated crash"):
        store.commit(
            prior=prior,
            update_index=1,
            deployed_skill="improved\n",
            status="accepted_by_skillopt_gate",
            optimizer_usage=OptimizerUsage(total_tokens=5),
            gate_decision=accepted("improved\n"),
            proposal_record={"edit_count": 1},
        )

    assert store.transaction_path.exists()
    recovered = StateStore(tmp_path).load()
    assert recovered.last_committed_update == 1
    assert recovered.current_hash != prior.current_hash
    assert not store.transaction_path.exists()
    assert len(store.history_path.read_text().splitlines()) == 1


def test_commit_recovery_is_idempotent_when_state_was_already_written(
    tmp_path, monkeypatch
) -> None:
    store = StateStore(tmp_path)
    prior = store.initialize(initial_skill="initial\n", metadata=metadata())
    real_unlink = state_module._atomic_unlink
    failed = False

    def interrupt_cleanup(path):
        nonlocal failed
        if not failed:
            failed = True
            raise OSError("simulated cleanup crash")
        real_unlink(path)

    monkeypatch.setattr(state_module, "_atomic_unlink", interrupt_cleanup)
    with pytest.raises(OSError, match="simulated cleanup crash"):
        store.commit(
            prior=prior,
            update_index=1,
            deployed_skill="improved\n",
            status="accepted_by_skillopt_gate",
            optimizer_usage=OptimizerUsage(),
            gate_decision=accepted("improved\n"),
            proposal_record={"edit_count": 1},
        )

    recovered = StateStore(tmp_path).load()
    assert recovered.last_committed_update == 1
    assert len(store.history_path.read_text().splitlines()) == 1
