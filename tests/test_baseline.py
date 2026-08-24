from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from seagym.baselines import Checkpoint, Trajectory, TrajectoryBatch

from holoskill_gym.baseline import SkillOptHoloBaseline
from holoskill_gym.engine import SkillOptHoloEngine
from holoskill_gym.holo_backend import HoloBackend, HoloBackendConfig
from holoskill_gym.leakage import LeakageGuard
from holoskill_gym.schemas import GateTaskScore

INITIAL = """# Skill

## Measure
Run once.
"""

PROPOSAL = {
    "diagnosis": ["Measurements are noisy."],
    "edits": [
        {
            "operation": "replace",
            "section": "Measure",
            "old_text": "Run once.",
            "new_text": "Run three times and compare the median.",
            "rationale": "Use a robust aggregate.",
            "evidence_ids": ["train-1"],
        }
    ],
    "expected_effects": ["Less noise."],
    "risks": ["Longer runtime."],
}


class FakeCompletions:
    def create(self, **_: object) -> SimpleNamespace:
        return SimpleNamespace(
            id="proposal-1",
            model="holo3-1-35b-a3b",
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(content=json.dumps(PROPOSAL)),
                )
            ],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        )


def reflection(**_: object) -> tuple[str, dict[str, int]]:
    return "Use robust timing.", {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}


def evaluator(*, skill: str, task_ids: list[str]) -> list[GateTaskScore]:
    value = 0.7 if "median" in skill else 0.5
    return [
        GateTaskScore(
            task_id=task_id,
            hard_score=1,
            soft_score=value,
            correctness_pass=True,
            edit_policy_pass=True,
            infra_valid=True,
        )
        for task_id in task_ids
    ]


def batch() -> TrajectoryBatch:
    trajectory = Trajectory(
        task_id="train-1",
        attempt_id="attempt-1",
        view_name="train",
        mode="train",
        success=True,
        reward=0.4,
        score=0.4,
        rewards={"score": 0.4},
        refs={"authorization": "Bearer should-not-persist"},
    )
    return TrajectoryBatch(
        trajectories=[trajectory],
        task_ids=["train-1"],
        view_name="train",
        mode="train",
    )


def make_baseline(tmp_path: Path, *, gate=evaluator) -> SkillOptHoloBaseline:
    tmp_path.mkdir(parents=True, exist_ok=True)
    initial = tmp_path / "initial.md"
    initial.write_text(INITIAL, encoding="utf-8")
    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    backend = HoloBackend(HoloBackendConfig(api_key="fake"), client=client)
    engine = SkillOptHoloEngine(backend, reflection_fn=reflection)
    guard = LeakageGuard(
        train_ids=frozenset({"train-1"}),
        gate_ids=frozenset({"gate-1"}),
        observer_ids={"seagym_test_id": frozenset({"test-1"})},
    )
    return SkillOptHoloBaseline(
        baseline_id="skillopt_holo",
        state_dir=tmp_path / "state",
        initial_skill_path=initial,
        leakage_guard=guard,
        engine=engine,
        gate_evaluator=gate,
    )


def test_baseline_accepts_and_persists_auditable_update(tmp_path) -> None:
    baseline = make_baseline(tmp_path)
    state = baseline.initialize(tmp_path)

    result = baseline.update(batch(), state)

    assert result.status == "accepted_by_skillopt_gate"
    assert result.changed is True
    assert "median" in (tmp_path / "state" / "best_skill.md").read_text()
    update_dir = tmp_path / "state" / "updates" / "update_0001"
    assert (update_dir / "proposal.json").exists()
    assert (update_dir / "gate_decision.json").exists()
    assert "should-not-persist" not in (update_dir / "trajectories.jsonl").read_text()
    assert result.logs["optimizer_usage"]["total_tokens"] == 35


def test_rejected_candidate_keeps_deployed_bytes(tmp_path) -> None:
    def regressing(*, skill: str, task_ids: list[str]) -> list[GateTaskScore]:
        value = 0.4 if "median" in skill else 0.5
        return (
            evaluator(skill=INITIAL if value == 0.5 else skill, task_ids=task_ids)[0].model_copy(
                update={"soft_score": value}
            ),
        )

    baseline = make_baseline(tmp_path, gate=regressing)
    state = baseline.initialize(tmp_path)

    result = baseline.update(batch(), state)

    assert result.status == "rejected_by_skillopt_gate"
    assert result.changed is False
    assert baseline.store.read_skill() == INITIAL


def test_checkpoint_load_never_calls_optimizer_and_round_trips_state(tmp_path) -> None:
    baseline = make_baseline(tmp_path)
    state = baseline.initialize(tmp_path)
    baseline.update(batch(), state)
    checkpoint_dir = tmp_path / "checkpoint"
    checkpoint = baseline.save_checkpoint(state, checkpoint_dir)

    restored = make_baseline(tmp_path / "restored")
    loaded = restored.load_checkpoint(
        Checkpoint(
            checkpoint_dir=checkpoint.checkpoint_dir,
            state_ref=checkpoint.state_ref,
            metadata=checkpoint.metadata,
        )
    )

    assert restored.store.read_skill() == baseline.store.read_skill()
    assert restored.store.load() == baseline.store.load()
    assert restored.update_index == 1
    assert loaded.metadata["prompt_template_path"].endswith("best_skill.md")
