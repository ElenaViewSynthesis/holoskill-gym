# codeopt-train-001

Reduce repeated prefix work in encode_batch without changing its output.

## Context

The repository is checked out at `/app`. The hot path is
`src/prefix_cache.py`; the bottleneck family is **prefix-caching**.

## What you must achieve

1. Keep every test in `tests/` passing. They are authoritative and must
   not be modified.
2. Improve `encode_throughput_units` as reported by `benchmark.py` (higher is better).
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
