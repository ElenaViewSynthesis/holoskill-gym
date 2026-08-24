"""Code-optimization metrics with explicit correctness and cost roles."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Literal


def benchmark_speedup(
    *,
    before: float,
    after: float,
    direction: Literal["minimize", "maximize"],
) -> float:
    if not math.isfinite(before) or not math.isfinite(after) or before <= 0 or after <= 0:
        raise ValueError("benchmark values must be finite and positive")
    if direction == "maximize":
        return after / before
    if direction == "minimize":
        return before / after
    raise ValueError(f"unsupported optimization direction: {direction}")


def correctness_gated_performance(*, correctness_pass: bool, speedup: float) -> float:
    if not math.isfinite(speedup) or speedup < 0:
        raise ValueError("speedup must be finite and non-negative")
    return speedup if correctness_pass else 0.0


def geometric_mean_speedup(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    if any(not math.isfinite(value) or value <= 0 for value in values):
        raise ValueError("speedups must be finite and positive")
    return math.exp(sum(math.log(value) for value in values) / len(values))


def separate_costs(
    *, target_cost_usd: float = 0.0, optimizer_cost_usd: float = 0.0
) -> dict[str, float]:
    """Never hide method optimizer spend inside target rollout spend."""

    return {
        "target_cost_usd": float(target_cost_usd),
        "optimizer_cost_usd": float(optimizer_cost_usd),
        "total_cost_usd": float(target_cost_usd + optimizer_cost_usd),
    }
