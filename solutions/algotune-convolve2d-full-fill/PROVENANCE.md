# algotune-convolve2d-full-fill — Codex solution

| Field | Value |
|---|---|
| Task | `algotune-convolve2d-full-fill` (`algotune@1.0`, harbor-datasets `479f07dd`) |
| Agent | Harbor `codex`, model `gpt-5.6-sol`, `reasoning_effort=medium` |
| Job | `trusted-algotune-convolve2d-codex-paid` |
| Trial | `algotune-convolve2d-full-fill__kUV5uQc` |
| Harbor | v0.22.0 |
| Reward | **114.863** (raw speedup) |
| Baseline / solver time | 13.3952 s → 0.1166 s |
| Validity | `True` — outputs match the reference |
| Tokens | 246,787 in / 7,731 out |
| Cost | not recorded (litellm pricing unavailable; the ATIF fallback patch preserves token counts) |
| `source_sha256` | `819d2e54de5c83de66fa9c1631d4de60afcd3234210ece3663537680a2e92f77` |
| Oracle on same task | 1.0066 — the agent beat the reference implementation ~114× |

## Algorithm

FFT convolution via the convolution theorem: `scipy.fft.rfft2` on both operands,
pointwise spectrum multiply, `irfft2` back, cropped to the full-convolution
output size. Padded to `next_fast_len` so the transform hits smooth prime
factors.

| | Time | Space |
|---|---|---|
| Baseline (direct spatial) | O(N²M²) | O(N²) |
| This solution | O(P² log P) | O(P²) |

`N = 30n` input side, `M = 8n` kernel side, `P = next_fast_len(38n − 1)` the
padded FFT side. The baseline sums M² products for each of N² output cells; the
solution replaces that with three transforms of a P×P real array. `rfft2`/`irfft2`
exploit real-valued input for roughly half the work of a complex transform — a
constant factor, not a change of order. `overwrite_x=True` reuses the spectrum
buffer for the inverse instead of allocating a second.

## Caveats — this is not a general 2D convolution

1. **Input shape is hardcoded.** `n` is recovered as `a.shape[0] // 30` and the
   output side assumed to be `38n − 1`. Arbitrary input/kernel pairs give wrong
   results.
2. **Bounded plan table.** Plans are precomputed for `n ∈ [1, 512]` only;
   `n > 512` raises `IndexError` with no bounds check.
3. **Deliberate use of the timing boundary.** Plan precomputation is placed in
   `__init__` — outside the timed region — and the source comment says so
   explicitly. It only computes integers, so it contributes negligibly to the
   measured speedup, but it shows the agent reasoning about the measurement
   protocol rather than only the problem.

The algorithmic win is real and is what AlgoTune exists to reward. The caveats
matter if this run is ever cited as evidence that the method produces *general*
optimizations.

## Reproducing

```bash
.venv-linux/bin/harbor run \
  -p results/trusted-tasks/algotune/algotune-convolve2d-full-fill \
  -e docker -a codex -m gpt-5.6-sol --ak reasoning_effort=medium \
  --n-concurrent 1 --max-retries 0 --agent-timeout-multiplier 0.333333 \
  --env-file .env --job-name <new-name> --jobs-dir jobs -y

scripts/ingest-run jobs/<new-name>
```
