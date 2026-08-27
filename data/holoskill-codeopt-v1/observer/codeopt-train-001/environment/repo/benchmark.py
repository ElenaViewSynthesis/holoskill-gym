#!/usr/bin/env python3
"""Deterministic benchmark for the prefix_cache workload.

Emits JSON on stdout: {'encode_throughput_units': float} measured in operations per second.
"""

from __future__ import annotations

import json
import sys
import time

from src.prefix_cache import encode_batch

SAMPLES = 5
WARMUPS = 1


def workload() -> int:
    prompts = [f"prompt number {i} with words" for i in range(400)]
    prefix = " ".join(f"shared{i}" for i in range(40))
    out = encode_batch(prompts, prefix)
    return sum(sum(row) for row in out)


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
        {'encode_throughput_units': value, 'checksum': checksum, 'samples': timings},
        sys.stdout,
    )
    sys.stdout.write('\n')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
