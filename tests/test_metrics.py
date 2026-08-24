import math

import pytest

from holoskill_gym.metrics import (
    benchmark_speedup,
    correctness_gated_performance,
    geometric_mean_speedup,
    separate_costs,
)


def test_direction_aware_speedup() -> None:
    assert benchmark_speedup(before=10, after=20, direction="maximize") == 2
    assert benchmark_speedup(before=10, after=5, direction="minimize") == 2


def test_correctness_gate_and_geometric_mean() -> None:
    assert correctness_gated_performance(correctness_pass=False, speedup=10) == 0
    assert correctness_gated_performance(correctness_pass=True, speedup=1.5) == 1.5
    assert math.isclose(geometric_mean_speedup([2, 8]), 4)


def test_invalid_benchmark_and_cost_roles() -> None:
    with pytest.raises(ValueError):
        benchmark_speedup(before=0, after=1, direction="maximize")
    assert separate_costs(target_cost_usd=1, optimizer_cost_usd=2) == {
        "target_cost_usd": 1.0,
        "optimizer_cost_usd": 2.0,
        "total_cost_usd": 3.0,
    }
