# Code Optimization Method

## Establish the baseline

Read the task and repository before editing. Run the authoritative correctness
test and benchmark exactly as provided, and note the benchmark direction and
units. Inspect the hot path and its callers. Prefer evidence from profiling,
operation counts, or repeated benchmark samples over intuition.

## Protect correctness

Preserve all observable behavior, public interfaces, ordering guarantees,
error handling, and supported inputs. Do not modify tests, benchmark programs,
task metadata, verifier code, or repository history. Keep the patch focused on
the implementation files needed for the optimization.

## Optimize deliberately

Form one concrete performance hypothesis at a time. Look first for avoidable
work in inner loops, repeated allocation or parsing, unnecessary data-structure
scans, redundant conversions, and missed opportunities to reuse invariant
state. Prefer a small algorithmic improvement over broad rewrites or fragile
micro-optimizations. Do not trade unbounded memory growth for speed.

## Measure the candidate

After each meaningful edit, rerun correctness before trusting performance.
Repeat the benchmark enough to distinguish a real improvement from noise, and
compare the same metric in the same environment. Treat timeouts, unstable
samples, and infrastructure failures as unresolved evidence—not as a score of
zero. Revert regressions and remove speculative changes that do not contribute.

## Finish with an auditable patch

Review the final diff and changed-file list. Confirm protected files are clean,
tests pass, the benchmark improves in the required direction, and no generated
logs or credentials entered the repository. Leave a concise explanation of the
bottleneck, the change, correctness evidence, benchmark samples, and remaining
risks.
