# codeopt-test-001

Reduce lock contention in read_many without changing observed values.

## Context

The repository is checked out at `/app`. The hot path is
`src/locking.py`; the bottleneck family is **concurrency-locking**.

## What you must achieve

1. Keep every test in `tests/` passing. They are authoritative and must
   not be modified.
2. Improve `read_latency_units` as reported by `benchmark.py` (lower is better).
3. Preserve observable behaviour exactly. Same inputs, same outputs.

## Rules

- Edit only files under `src/`.
- Do not modify `tests/`, `benchmark.py`, `task.toml`, or anything under
  `.git/`. Doing so fails the task regardless of measured performance.
- Do not special-case the benchmark's inputs. Optimize the general path.
- No network access is available.

## Verifying locally

```bash
cd /app
python -m pytest tests/ -q
python benchmark.py
```
