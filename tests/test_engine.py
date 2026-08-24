from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from holoskill_gym.engine import (
    GateExecutionError,
    SkillOptEngineConfig,
    SkillOptHoloEngine,
)
from holoskill_gym.holo_backend import HoloBackend, HoloBackendConfig
from holoskill_gym.schemas import GateTaskScore

SKILL = """# Skill

## Measure
Run once.
"""


PROPOSAL = {
    "diagnosis": ["One sample is noisy."],
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
            usage=SimpleNamespace(
                prompt_tokens=10,
                completion_tokens=20,
                total_tokens=30,
            ),
        )


def fake_backend() -> HoloBackend:
    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    return HoloBackend(HoloBackendConfig(api_key="fake"), client=client)


def fake_reflection(**kwargs: object) -> tuple[str, dict[str, int]]:
    assert kwargs["reasoning_effort"] is None
    return "Measurements should use a robust aggregate.", {
        "prompt_tokens": 7,
        "completion_tokens": 8,
        "total_tokens": 15,
    }


def score(
    task_id: str,
    value: float,
    *,
    correctness: bool = True,
    policy: bool = True,
    infra: bool = True,
) -> GateTaskScore:
    return GateTaskScore(
        task_id=task_id,
        hard_score=float(correctness),
        soft_score=value,
        correctness_pass=correctness,
        edit_policy_pass=policy,
        infra_valid=infra,
    )


def test_engine_reflects_then_returns_validated_candidate() -> None:
    engine = SkillOptHoloEngine(fake_backend(), reflection_fn=fake_reflection)

    result = engine.propose(
        current_skill=SKILL,
        training_trajectories=[{"task_id": "train-1", "score": 0.4, "secret": "excluded"}],
    )

    assert result.changed is True
    assert "three times" in result.candidate_skill
    assert result.reflection.usage.total_tokens == 15
    assert result.response.call.usage.total_tokens == 30


def test_gate_accepts_only_strict_improvement_using_upstream_gate() -> None:
    engine = SkillOptHoloEngine(fake_backend(), reflection_fn=fake_reflection)

    decision = engine.evaluate_gate(
        current_skill=SKILL,
        candidate_skill=SKILL + "\nImproved.\n",
        baseline_results=[score("gate-1", 0.5)],
        candidate_results=[score("gate-1", 0.7)],
        global_step=1,
    )

    assert decision.accepted is True
    assert decision.action == "accept_new_best"
    assert decision.deployed_skill.endswith("Improved.\n")


def test_gate_rejects_improvement_below_epsilon() -> None:
    engine = SkillOptHoloEngine(
        fake_backend(),
        config=SkillOptEngineConfig(strict_improvement_epsilon=0.1),
        reflection_fn=fake_reflection,
    )

    decision = engine.evaluate_gate(
        current_skill=SKILL,
        candidate_skill=SKILL + "\nChanged.\n",
        baseline_results=[score("gate-1", 0.5)],
        candidate_results=[score("gate-1", 0.55)],
        global_step=1,
    )

    assert decision.accepted is False
    assert decision.deployed_skill == SKILL


def test_gate_no_regression_blocks_pass_to_fail() -> None:
    engine = SkillOptHoloEngine(fake_backend(), reflection_fn=fake_reflection)

    decision = engine.evaluate_gate(
        current_skill=SKILL,
        candidate_skill=SKILL + "\nChanged.\n",
        baseline_results=[score("gate-1", 0.5, correctness=True)],
        candidate_results=[score("gate-1", 0.9, correctness=False)],
        global_step=1,
    )

    assert decision.accepted is False
    assert "correctness regression" in decision.reason


def test_gate_infrastructure_failure_is_not_a_rejection() -> None:
    engine = SkillOptHoloEngine(fake_backend(), reflection_fn=fake_reflection)

    with pytest.raises(GateExecutionError, match="infrastructure failed"):
        engine.evaluate_gate(
            current_skill=SKILL,
            candidate_skill=SKILL + "\nChanged.\n",
            baseline_results=[score("gate-1", 0.5)],
            candidate_results=[score("gate-1", 0.7, infra=False)],
            global_step=1,
        )


def test_gate_off_ablation_applies_changed_bytes_without_scores() -> None:
    engine = SkillOptHoloEngine(
        fake_backend(),
        config=SkillOptEngineConfig(gate_mode="off"),
        reflection_fn=fake_reflection,
    )

    decision = engine.evaluate_gate(
        current_skill=SKILL,
        candidate_skill=SKILL + "\nChanged.\n",
        baseline_results=[],
        candidate_results=[],
        global_step=1,
    )

    assert decision.accepted is True
    assert decision.action == "greedy_applied"
