from __future__ import annotations

import json

import pytest

from holoskill_gym.report_metrics import (
    CandidateAcceptanceRateMetric,
    CorrectSpeedupGeomeanMetric,
    CrossHarnessTransferDeltaMetric,
    ForbiddenEditRateMetric,
    GateOffApplicationRateMetric,
    P95PerformanceChangeMetric,
    ReliabilityRatesMetric,
)


def _task_row(
    *,
    speedup: float = 2.0,
    correct: bool = True,
    policy_pass: bool = True,
    forbidden: bool = False,
    infra_valid: bool = True,
    terminal_status: str = "success",
    latency_delta: float | None = -10.0,
    memory_delta: float | None = -5.0,
    role: str | None = None,
    score: float = 1.0,
) -> dict[str, object]:
    return {
        "view_name": "id_test",
        "mode": "final",
        "baseline_role": role,
        "score": score,
        "refs": {
            "extra": {
                "holoskill_gym": {
                    "normalized_evidence": {
                        "benchmark": {"speedup": speedup},
                        "correctness": {"after_pass": correct},
                        "policy": {
                            "edit_policy_pass": policy_pass,
                            "forbidden_edit": forbidden,
                        },
                        "performance": {
                            "latency_delta_pct": latency_delta,
                            "peak_memory_delta_pct": memory_delta,
                        },
                        "terminal_status": terminal_status,
                        "rewards": {
                            "infra_valid": float(infra_valid),
                            "timeout": float(terminal_status == "timeout"),
                        },
                    }
                }
            }
        },
    }


def _update(status: str) -> dict[str, object]:
    return {"mode": "update", "update_summary": {"status": status}}


def test_code_optimization_metrics_use_explicit_verifier_evidence() -> None:
    records = [
        _task_row(speedup=2, latency_delta=-20, memory_delta=-10),
        _task_row(speedup=8, latency_delta=20, memory_delta=30),
        _task_row(speedup=100, correct=False, forbidden=True, infra_valid=False),
        _task_row(speedup=1, terminal_status="timeout", infra_valid=False),
    ]

    speedup = CorrectSpeedupGeomeanMetric().compute(records, {})
    forbidden = ForbiddenEditRateMetric().compute(records, {})
    reliability = ReliabilityRatesMetric().compute(records, {})
    p95 = P95PerformanceChangeMetric().compute(records, {})

    assert speedup["value"] == pytest.approx(4.0)
    assert speedup["num_correct_runs"] == 2
    assert forbidden["value"] == pytest.approx(0.25)
    assert reliability["timeout_rate"] == pytest.approx(0.25)
    assert reliability["infra_failure_rate"] == pytest.approx(0.5)
    assert p95["latency_delta_pct"] == pytest.approx(15.5)
    assert p95["peak_memory_delta_pct"] == pytest.approx(24.75)


def test_gate_off_is_never_counted_as_private_gate_acceptance() -> None:
    records = [
        _update("accepted_by_skillopt_gate"),
        _update("rejected_by_skillopt_gate"),
        _update("applied_gate_off_ablation"),
        _update("no_op_proposal"),
    ]

    acceptance = CandidateAcceptanceRateMetric().compute(records, {})
    gate_off = GateOffApplicationRateMetric().compute(records, {})

    assert acceptance == {
        "value": 0.5,
        "accepted_by_private_gate": 1,
        "rejected_by_private_gate": 1,
        "private_gate_decisions": 2,
    }
    assert gate_off["applications"] == 1
    assert gate_off["private_gate_acceptance"] is False


def test_cross_harness_delta_requires_distinct_executors_and_paired_roles() -> None:
    records = [
        _task_row(role="A_T", score=0.9),
        _task_row(role="A_0", score=0.4),
    ]
    metric = CrossHarnessTransferDeltaMetric()

    result = metric.compute(
        records,
        {
            "cross_harness_transfer": {
                "source_executor": "codex_exec",
                "evaluation_executor": "claude_code_exec",
            }
        },
    )
    same = metric.compute(
        records,
        {
            "cross_harness_transfer": {
                "source_executor": "codex_exec",
                "evaluation_executor": "codex_exec",
            }
        },
    )

    assert result["applicable"] is True
    assert result["by_view"] == {"id_test": pytest.approx(0.5)}
    assert same["applicable"] is False


def test_cross_harness_delta_compares_target_eval_to_hashed_source_records(
    tmp_path,
) -> None:
    source_path = tmp_path / "metric_inputs.jsonl"
    source_path.write_text(
        json.dumps(_task_row(role="A_T", score=0.8)) + "\n",
        encoding="utf-8",
    )
    target = _task_row(role="checkpoint", score=0.65)

    result = CrossHarnessTransferDeltaMetric().compute(
        [target],
        {
            "cross_harness_transfer": {
                "source_executor": "codex_exec",
                "evaluation_executor": "claude_code_exec",
                "reference_metric_inputs_path": str(source_path),
            }
        },
    )

    assert result["applicable"] is True
    assert result["by_view"] == {"id_test": pytest.approx(-0.15)}
    assert len(result["reference_sha256"]) == 64
