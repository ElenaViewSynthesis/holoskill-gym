"""Credential-free deterministic components for tests and the smoke experiment."""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import SimpleNamespace

from .schemas import (
    GateTaskScore,
    OptimizerCallRecord,
    OptimizerUsage,
    ProposalResponse,
    SkillUpdateProposal,
)


@dataclass(frozen=True)
class DeterministicBackendConfig:
    model: str = "deterministic-holo"


class DeterministicHoloBackend:
    """Return the same evidence-linked improvement for identical input bytes."""

    def __init__(self) -> None:
        self.config = DeterministicBackendConfig()
        self.records: list[OptimizerCallRecord] = []

    def propose(self, *, system: str, user: str) -> ProposalResponse:
        del system
        match = re.search(r'"task_id"\s*:\s*"([^"]+)"', user)
        evidence_id = match.group(1) if match else "missing-evidence"
        if "Run three times and compare the median." in user:
            edits: list[dict[str, object]] = []
        else:
            edits = [
                {
                    "operation": "replace",
                    "section": "Measure",
                    "old_text": "Run once.",
                    "new_text": "Run three times and compare the median.",
                    "rationale": "A robust aggregate reduces measurement noise.",
                    "evidence_ids": [evidence_id],
                }
            ]
        proposal = SkillUpdateProposal.model_validate(
            {
                "diagnosis": ["Single measurements are noisy."],
                "edits": edits,
                "expected_effects": ["More stable performance comparisons."],
                "risks": ["The measurement stage takes longer."],
            }
        )
        record = OptimizerCallRecord(
            provider="deterministic",
            model=self.config.model,
            latency_ms=0,
            attempts=1,
            response_id="deterministic-proposal",
            finish_reason="stop",
            usage=OptimizerUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
        )
        self.records.append(record)
        return ProposalResponse(proposal=proposal, call=record)


def deterministic_reflection(**_: object) -> tuple[str, dict[str, int]]:
    return "Use repeated measurements and a robust aggregate.", {
        "prompt_tokens": 5,
        "completion_tokens": 5,
        "total_tokens": 10,
    }


def deterministic_gate(*, skill: str, task_ids: list[str]) -> list[GateTaskScore]:
    value = 0.75 if "compare the median" in skill else 0.5
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


def deterministic_client() -> SimpleNamespace:
    """Compatibility marker for callers that expect an object-like fake client."""

    return SimpleNamespace(provider="deterministic")
