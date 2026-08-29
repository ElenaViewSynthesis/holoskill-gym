"""Code-optimization metrics with explicit correctness and cost roles."""

from __future__ import annotations

import math
import statistics
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
    """Map a raw positive speedup to a bounded correctness-gated score.

    Neutral performance maps to 0.5, regressions map below 0.5, and
    improvements approach 1 without collapsing distinct speedups. Callers
    retain the raw speedup separately for reporting.
    """

    if not math.isfinite(speedup) or speedup <= 0:
        raise ValueError("speedup must be finite and positive")
    if not correctness_pass:
        return 0.0
    return 0.5 + 0.5 * math.tanh(math.log(speedup))


def geometric_mean_speedup(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    if any(not math.isfinite(value) or value <= 0 for value in values):
        raise ValueError("speedups must be finite and positive")
    return math.exp(sum(math.log(value) for value in values) / len(values))


def harmonic_mean_speedup(values: Sequence[float], *, mercy_score: float = 1.0) -> float:
    """Return the AlgoTune Score: harmonic mean of per-task speedups.

    This is *not* interchangeable with :func:`geometric_mean_speedup`. The
    harmonic mean is dominated by the smallest values, so a single task that
    fails to improve caps the aggregate far more sharply than the geometric
    mean does. AlgoTune uses it deliberately: it rewards broad improvement over
    a spectacular win on one task, which the geometric mean would let through.

    ``mercy_score`` is AlgoTune's floor for a solution that fails validation or
    runs slower than the reference. Non-positive samples are raised to it rather
    than rejected, matching the upstream protocol; pass ``mercy_score=0`` only if
    you intend a failed task to zero the aggregate.

    Reporting both statistics side by side is the point. A harmonic mean well
    below the geometric mean means the gain is concentrated in a few tasks.
    """

    if not values:
        return 0.0
    if not math.isfinite(mercy_score) or mercy_score < 0:
        raise ValueError("mercy_score must be finite and non-negative")
    floored: list[float] = []
    for value in values:
        if not math.isfinite(value):
            raise ValueError("speedups must be finite")
        floored.append(max(float(value), mercy_score))
    if any(value <= 0 for value in floored):
        return 0.0
    return len(floored) / sum(1.0 / value for value in floored)


def latency_delta_pct(*, before: float, after: float) -> float:
    """Return raw latency change; negative values are improvements."""

    return _percentage_delta(before=before, after=after, label="latency")


def throughput_delta_pct(*, before: float, after: float) -> float:
    """Return raw throughput change; positive values are improvements."""

    return _percentage_delta(before=before, after=after, label="throughput")


def peak_memory_delta_pct(*, before: float, after: float) -> float:
    """Return raw peak-memory change; negative values are improvements."""

    return _percentage_delta(before=before, after=after, label="peak memory")


def benchmark_cv(samples: Sequence[float]) -> float:
    """Return population coefficient of variation for positive samples."""

    if not samples:
        raise ValueError("benchmark samples must not be empty")
    values = [float(value) for value in samples]
    if any(not math.isfinite(value) or value <= 0 for value in values):
        raise ValueError("benchmark samples must be finite and positive")
    mean = statistics.fmean(values)
    return statistics.pstdev(values) / mean


def regression_indicator(*, speedup: float, tolerance: float = 0.0) -> int:
    if not math.isfinite(speedup) or speedup <= 0:
        raise ValueError("speedup must be finite and positive")
    if tolerance < 0:
        raise ValueError("tolerance must be non-negative")
    return int(speedup < 1.0 - tolerance)


def timeout_indicator(*, timed_out: bool) -> int:
    return int(timed_out)


def separate_costs(
    *, target_cost_usd: float = 0.0, optimizer_cost_usd: float = 0.0
) -> dict[str, float]:
    """Never hide method optimizer spend inside target rollout spend."""

    return {
        "target_cost_usd": float(target_cost_usd),
        "optimizer_cost_usd": float(optimizer_cost_usd),
        "total_cost_usd": float(target_cost_usd + optimizer_cost_usd),
    }


def _percentage_delta(*, before: float, after: float, label: str) -> float:
    if not math.isfinite(before) or not math.isfinite(after) or before <= 0 or after < 0:
        raise ValueError(f"{label} values must be finite with before > 0 and after >= 0")
    return 100.0 * (after - before) / before
