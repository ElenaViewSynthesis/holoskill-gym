#!/usr/bin/env python3
"""Deterministic benchmark for the serialization workload.

Emits JSON on stdout: {'serialize_latency_units': float} measured in milliseconds.
"""

from __future__ import annotations

import json
import sys
import time

from src.serialization import serialize_records

SAMPLES = 5
WARMUPS = 1


def workload() -> int:
    records = [{"id": i, "value": i * 3} for i in range(20000)]
    return len(serialize_records(records))


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
        {'serialize_latency_units': value, 'checksum': checksum, 'samples': timings},
        sys.stdout,
    )
    sys.stdout.write('\n')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
