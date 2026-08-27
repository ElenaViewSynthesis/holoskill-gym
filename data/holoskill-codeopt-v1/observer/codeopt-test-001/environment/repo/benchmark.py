#!/usr/bin/env python3
"""Deterministic benchmark for the locking workload.

Emits JSON on stdout: {'read_latency_units': float} measured in milliseconds.
"""

from __future__ import annotations

import json
import sys
import time

from src.locking import Registry

SAMPLES = 5
WARMUPS = 1


def workload() -> int:
    reg = Registry({f"k{i}": i for i in range(500)})
    keys = [f"k{i % 500}" for i in range(60000)]
    return sum(reg.read_many(keys))


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
    value = median * 1000.0
    json.dump(
        {'read_latency_units': value, 'checksum': checksum, 'samples': timings},
        sys.stdout,
    )
    sys.stdout.write('\n')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
