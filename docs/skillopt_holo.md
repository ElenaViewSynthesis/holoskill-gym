# SkillOpt/Holo production guide

## Architecture and authority

HoloSkill Gym has three deliberately separate roles:

1. Harbor owns task isolation, agent execution, timeouts, and canonical ATIF
   trajectories.
2. SkillOpt/Holo is the method. Holo reflects on normalized training evidence
   and proposes a bounded skill edit; SkillOpt's private gate alone decides
   whether that candidate becomes the deployed skill.
3. SEAGym is a passive observer. It checkpoints states and independently
   computes validation, test, reliability, performance, and cost metrics. It
   never accepts, rejects, promotes, or rolls back a proposal.

The checkpointed skill reaches Harbor through `prompt_template_path`. Nothing
mutates a user-global Codex or Claude Code installation.

## Install and verify

From the repository root:

```bash
git submodule update --init --recursive
bash scripts/apply-vendor-patches
source .venv-linux/bin/activate
pytest -q
ruff check holoskill_gym tests
ruff format --check holoskill_gym tests
```

The deterministic smoke executes the checked-in fixture repositories through
the production verifier without credentials or network access:

```bash
seagym inspect config examples/holo_skillopt_deterministic/config.json
seagym train examples/holo_skillopt_deterministic/config.json
```

## Credentials and executors

Copy `.env.example` to `.env` and populate only the roles a run uses:

- `HAI_API_KEY` authenticates the Holo optimizer.
- `OPENAI_API_KEY` authenticates the Codex target condition.
- `ANTHROPIC_API_KEY` authenticates the Claude Code target condition.

Optimizer credentials are never exported into target-agent sandboxes. The
optimizer is fixed to `holo3-1-35b-a3b`; other model IDs fail closed.
`codex_exec` maps to Harbor's built-in `codex` agent and
`claude_code_exec` maps to `claude-code`.

Production retry defaults are six attempts with exponential waits of 6, 12,
24, 30, and 30 seconds. This accommodates the service's minimum request
spacing and makes a short 429 burst wait instead of failing in roughly one
second. The first production configs still use `backend.n_concurrent: 1` so
task and optimizer failures remain easy to attribute.

## Task and split contract

Observer tasks live in the SEAGym task index and immutable train/validation/test
split. SkillOpt's private gate has a separate task index. `LeakageGuard`
requires exact gate-task ID equality; every gate task must produce a
`GateTaskScore`, including infrastructure and verifier failures.

A production Harbor code-optimization task must provide:

- a pinned repository commit and task-local isolated worktree;
- authoritative correctness and benchmark commands;
- benchmark direction, repeated samples, and stable units;
- protected paths for tests, benchmarks, metadata, `.git`, and verifier code;
- explicit agent/verifier timeouts and network policy;
- a strict verifier result with correctness, edit policy, infrastructure
  validity, samples, terminal status, and artifact paths.

See [Harbor task structure](harbor-task-structure.md),
[Harbor multi-step tasks](harbor-multi-step-tasks.md), and the
[Verifiers v1 bridge](verifiers-v1-harbor.md) for the underlying formats.

## Normalized evidence and privacy

`holoskill_gym.trajectory.NormalizedTrajectory` is the shared reporting and
reflection contract. It validates canonical ATIF, assigns stable attempt-level
evidence IDs, preserves project data under `extra.holoskill_gym`, and carries
local artifact paths instead of inline logs.

Evidence budgets apply deterministically per record and per field. Elision is
structural (`omitted_records` and field-elision entries); serialized JSON is
never cut at a character offset. Duplicate task IDs from multiple Harbor
attempts are retained rather than rejected.

Hidden reasoning is never persisted. Prompts and errors are sanitized, action
summaries are bounded, subprocess stdout/stderr are bounded, and credential
fields remain redacted. Numeric token telemetry survives redaction.

## Verifier and metrics

`holoskill_gym.verifier.VerifierResult` distinguishes ordinary task failure
from invalid infrastructure. The private gate consumes explicit
`correctness_pass`, `edit_policy_pass`, and `infra_valid` fields; it never
infers correctness from generic trajectory success.

The bounded performance score is:

```text
0                                      when correctness fails
0.5 + 0.5 * tanh(log(raw_speedup))     otherwise
```

Raw speedup and untransformed latency, throughput, memory, sample variability,
regression, timeout, wall-time, and tool-call metrics remain in evidence.

Registered SEAGym report metrics include:

- geometric-mean speedup among explicitly correct, policy-valid, infra-valid
  runs;
- private-gate candidate acceptance rate;
- gate-off application rate as a separate non-acceptance disposition;
- forbidden-edit, timeout, and infrastructure-failure rates;
- p95 latency and peak-memory change;
- cross-harness transfer delta.

Target usage comes from ATIF/task rows. Optimizer usage comes from update rows.
They are never summed into a single spend figure.

## Experiment matrix

The committed matrix is under `examples/holo_skillopt_matrix/`:

- Codex gated and Claude Code gated primary conditions;
- Codex and Claude Code frozen-skill static controls;
- a Codex gate-off ablation;
- Codex-to-Claude and Claude-to-Codex frozen checkpoint evaluation configs.

The production Harbor dataset is intentionally not simulated. Provision the
trusted task packages at the paths documented by the matrix before running it.
All matrix configs can be inspected without credentials; the gated runs require
Holo and target credentials plus Harbor/Docker capacity.

Transfer configs are eval-only. Their metric subtracts the source run's `A_T`
score from the target-harness checkpoint score for each matching view. The
source `metric_inputs.jsonl` path and its SHA-256 are recorded. If the source
run is absent, the metric says `applicable: false`.

## Train, evaluate, and resume

```bash
seagym train <config.json>
seagym train <config.json> --run-dir <run-dir> --resume
seagym eval <config.json> \
  --checkpoint <source-run>/checkpoints/final \
  --run-dir <new-eval-run>
```

Checkpoint evaluation never calls baseline update, SkillOpt reflection, or
Holo proposal generation. Resuming a completed `final` checkpoint is an
idempotent no-op before metric/report recomputation: committed update count,
metric inputs, state, deployed skill, metrics, and summary report remain
byte-identical. Intermediate-checkpoint recovery is still covered primarily by
the state-store guard and remains a production follow-up.

## Artifacts

Important run paths include:

- `records/metric_inputs.jsonl`: normalized observer and update metric inputs;
- `records/agent_updates.jsonl`: proposal disposition and optimizer cost;
- `agent_state/<baseline>/`: deployed skill, state, history, and update audit;
- `checkpoints/<id>/`: hash-verified baseline snapshots and trainer state;
- `fixture_trials/` or `harbor/jobs/`: local task artifacts and ATIF paths;
- `metrics.json` and `reports/`: reproducible observer outputs.

## Known limitations

- Trusted production Harbor task packages and credentials are external and
  have not been executed in this repository.
- Per-executor reasoning-effort and several Harbor policy knobs still need
  stricter `CliCodeOptRolloutAgent` configuration validation.
- Verifiers v1 does not yet cover every Harbor feature, notably multi-step
  tasks and several sidecar/separate-verifier build paths.
- Intermediate-checkpoint trainer resume and full fake Codex/Claude wrapper
  coverage remain open even though completed-final resume and the shared
  subprocess lifecycle are integration-tested.
