#!/usr/bin/env python3
"""Deterministic benchmark for the allocation workload.

Emits JSON on stdout: {'buffer_latency_units': float} measured in milliseconds.
"""

from __future__ import annotations

import json
import sys
import time

from src.allocation import build_buffer

SAMPLES = 5
WARMUPS = 1


def workload() -> int:
    chunks = [f"chunk{i}" for i in range(6000)]
    return len(build_buffer(chunks))


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
        {'buffer_latency_units': value, 'checksum': checksum, 'samples': timings},
        sys.stdout,
    )
    sys.stdout.write('\n')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
