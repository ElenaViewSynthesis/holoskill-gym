#!/usr/bin/env python3
"""Deterministic benchmark for the batching workload.

Emits JSON on stdout: {'scoring_throughput_units': float} measured in operations per second.
"""

from __future__ import annotations

import json
import sys
import time

from src.batching import score_all

SAMPLES = 5
WARMUPS = 1


def workload() -> int:
    items = [f"item-{i}-payload" for i in range(20000)]
    return sum(score_all(items))


def main() -> int:
    for _ in range(WARMUPS):
        workload()
    timings = []
    checksum = None
    for _ in range(SAMPLES):
        start = time.perf_counter()
        checksum = workload()
        timings.append(time.perf_counter() - start)
    timings.sort()
    median = timings[len(timings) // 2]
    value = 1.0 / median if median > 0 else 0.0
    json.dump(
        {'scoring_throughput_units': value, 'checksum': checksum, 'samples': timings},
        sys.stdout,
    )
    sys.stdout.write('\n')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
