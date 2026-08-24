import json

import pytest

from holoskill_gym.leakage import LeakageError, LeakageGuard


def guard() -> LeakageGuard:
    return LeakageGuard(
        train_ids=frozenset({"train-1", "train-2"}),
        gate_ids=frozenset({"gate-1"}),
        observer_ids={"seagym_test_id": frozenset({"test-1"})},
    )


def test_training_batch_must_be_train_only() -> None:
    guard().assert_training_batch(task_ids=["train-1"], view_name="train", mode="train")
    with pytest.raises(LeakageError, match="non-training"):
        guard().assert_training_batch(task_ids=["test-1"], view_name="train", mode="train")
    with pytest.raises(LeakageError, match="train/train"):
        guard().assert_training_batch(task_ids=["train-1"], view_name="test", mode="eval")


def test_split_overlap_fails_closed_but_train_replay_is_allowed() -> None:
    with pytest.raises(LeakageError, match="split overlap"):
        LeakageGuard(
            train_ids=frozenset({"same"}),
            gate_ids=frozenset({"same"}),
            observer_ids={},
        )
    LeakageGuard(
        train_ids=frozenset({"same"}),
        gate_ids=frozenset({"gate"}),
        observer_ids={"seagym_replay": frozenset({"same"})},
    )


def test_loads_manifest_and_private_gate_files(tmp_path) -> None:
    split = tmp_path / "split.json"
    gate = tmp_path / "gate.json"
    split.write_text(
        json.dumps({"splits": {"train": ["train-1"], "test": ["test-1"]}}),
        encoding="utf-8",
    )
    gate.write_text(json.dumps({"tasks": [{"task_id": "gate-1"}]}), encoding="utf-8")

    loaded = LeakageGuard.from_files(split_manifest_path=split, gate_path=gate)

    assert loaded.gate_ids == {"gate-1"}
    assert set(loaded.split_hashes()) == {
        "skillopt_train",
        "skillopt_gate",
        "seagym_test_id",
    }
