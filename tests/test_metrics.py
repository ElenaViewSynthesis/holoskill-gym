import math

import pytest

from holoskill_gym.metrics import (
    benchmark_cv,
    benchmark_speedup,
    correctness_gated_performance,
    geometric_mean_speedup,
    latency_delta_pct,
    peak_memory_delta_pct,
    regression_indicator,
    separate_costs,
    throughput_delta_pct,
    timeout_indicator,
)


def test_direction_aware_speedup() -> None:
    assert benchmark_speedup(before=10, after=20, direction="maximize") == 2
    assert benchmark_speedup(before=10, after=5, direction="minimize") == 2


def test_correctness_gate_and_geometric_mean() -> None:
    assert correctness_gated_performance(correctness_pass=False, speedup=10) == 0
    assert correctness_gated_performance(correctness_pass=True, speedup=1) == 0.5
    assert 0.5 < correctness_gated_performance(correctness_pass=True, speedup=1.2) < 1
    assert correctness_gated_performance(
        correctness_pass=True, speedup=10
    ) > correctness_gated_performance(correctness_pass=True, speedup=1.2)
    assert math.isclose(geometric_mean_speedup([2, 8]), 4)


def test_invalid_benchmark_and_cost_roles() -> None:
    with pytest.raises(ValueError):
        benchmark_speedup(before=0, after=1, direction="maximize")
    assert separate_costs(target_cost_usd=1, optimizer_cost_usd=2) == {
        "target_cost_usd": 1.0,
        "optimizer_cost_usd": 2.0,
        "total_cost_usd": 3.0,
    }


def test_performance_deltas_variance_and_indicators() -> None:
    assert latency_delta_pct(before=10, after=8) == -20
    assert throughput_delta_pct(before=10, after=12) == 20
    assert peak_memory_delta_pct(before=100, after=75) == -25
    assert benchmark_cv([2, 2, 2]) == 0
    assert regression_indicator(speedup=0.9) == 1
    assert regression_indicator(speedup=1.1) == 0
    assert timeout_indicator(timed_out=True) == 1
