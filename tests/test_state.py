import json

import pytest

import holoskill_gym.state as state_module
from holoskill_gym.schemas import GateDecision, OptimizerUsage
from holoskill_gym.state import StateIntegrityError, StateStore


def metadata() -> dict[str, object]:
    return {
        "skillopt_version": "0.2.0",
        "skillopt_commit": "abc123",
        "seagym_version": "0.1.0",
        "seagym_commit": "def456",
        "holo_model_id": "holo3-1-35b-a3b",
        "optimizer_prompt_hash": "prompt-hash",
        "target_executor": "codex_exec",
        "gate_mode": "on",
        "task_split_hashes": {"skillopt_train": "train-hash"},
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
