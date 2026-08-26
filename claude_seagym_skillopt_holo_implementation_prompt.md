# Claude implementation prompt: SEAGym × SkillOpt × Holo for self-evolving CLI code-optimization agents

You are the principal software engineer responsible for implementing a production-quality, hackathon-runnable integration in the **SEAGym** repository. Do not merely write an architecture proposal. Inspect the repository, implement the code, add tests and documentation, execute all safe deterministic checks, and report exactly what changed and what remains blocked by credentials or external infrastructure.

The system must evaluate reusable coding-agent skill evolution for **Codex CLI and Claude Code** on deterministic code-optimization tasks. **SkillOpt owns skill proposal, acceptance/rejection, and its private held-out validation gate. SEAGym remains a passive evaluation framework:** it records checkpointed states and evaluates them through train, frozen update-validation, replay, held-out ID/OOD, cost, and reliability views. SEAGym must never accept, reject, promote, or roll back an update.

Use **H Company Holo3** as the priority model integration. The optimizer policy
below supersedes older 122B requirements in this prompt:

- `holo3-1-35b-a3b` is the sole SkillOpt optimizer/evolver supported by this integration. It analyzes scored trajectories and emits bounded structured edits to the skill document.
- Skill-mutation calls use strict JSON-schema output with tools disabled, followed by mandatory local semantic validation. The model's tool capability may be used only in a separate, explicitly configured read-only evidence phase.
- Other Holo models may remain available to general-purpose clients such as `scripts/holo`, but they are outside the reproducible SkillOpt mutation policy and must not be selected silently.
- The target executor is either `codex_exec` or `claude_code_exec`. The executor model/harness is frozen during a run; only the natural-language skill artifact changes.
- SkillOpt v0.2.0 is the compatibility target. The implementation may support a later pinned SkillOpt commit, but it must not silently depend on unpinned `main` behavior.

Authoritative references:

- SEAGym: <https://github.com/antropy-research/SEAGym>
- SEAGym extension contract: <https://github.com/antropy-research/SEAGym/blob/main/docs/extending.md>
- SEAGym concepts and passive-evaluation boundary: <https://github.com/antropy-research/SEAGym/blob/main/docs/concepts.md>
- SEAGym baseline API: <https://github.com/antropy-research/SEAGym/blob/main/seagym/baselines/base.py>
- SEAGym rollout-agent API: <https://github.com/antropy-research/SEAGym/blob/main/seagym/rollout_agents/base.py>
- SkillOpt: <https://github.com/microsoft/SkillOpt>
- SkillOpt v0.2.0: <https://github.com/microsoft/SkillOpt/releases/tag/v0.2.0>
- SkillOpt-Sleep: <https://github.com/microsoft/SkillOpt/blob/main/docs/sleep/README.md>
- SkillOpt backend guide: <https://github.com/microsoft/SkillOpt/blob/main/docs/guide/new-backend.md>
- SkillOpt benchmark guide: <https://github.com/microsoft/SkillOpt/blob/main/docs/guide/new-benchmark.md>
- H documentation index: <https://hub.hcompany.ai/llms.txt>
- H Models API quickstart: <https://hub.hcompany.ai/quickstart>
- H model capabilities: <https://hub.hcompany.ai/models>
- H structured agent loop: <https://hub.hcompany.ai/agent-loop>

## 1. Mission and product definition

Build a minimal but extensible system called **HoloSkill Gym** with this lifecycle:

1. SEAGym materializes a deterministic batch of repository-optimization tasks.
2. A `CodexCliRolloutAgent` or `ClaudeCodeRolloutAgent` checks out each repository at a pinned commit, installs the current skill, runs the CLI agent in an isolated environment, and captures a normalized trajectory.
3. Deterministic verifiers run correctness tests, edit-policy checks, and benchmarks.
4. SEAGym passes only the scored **training trajectories** to `SkillOptHoloBaseline.update()`.
5. The baseline invokes SkillOpt’s reflection/aggregation/edit machinery. `holo3-1-35b-a3b` is the optimizer model and must produce schema-constrained add/delete/replace edits.
6. SkillOpt evaluates the candidate on its own private `skillopt_gate` task set. It accepts the candidate only according to the configured SkillOpt gate policy.
7. The baseline persists either the accepted skill or the unchanged prior skill and returns an auditable `UpdateResult`.
8. SEAGym checkpoints that state and independently runs frozen update-validation, replay, held-out ID, held-out OOD, cost, and reliability evaluations.
9. Reports compare the initial `A_0` skill, every update checkpoint, and the final skill. They must also distinguish a proposed edit from an accepted skill state.

The central product claim is:

> Holo and SkillOpt form the self-evolution method; SEAGym is the independent microscope that reveals reusable improvement, overfitting, forgetting, cost change, and reliability shifts.

Do not call SEAGym a trainer, optimizer, selection gate, promotion controller, champion selector, or rollback manager.

## 2. Non-negotiable framework boundary

Enforce the following boundary in code, tests, documentation, configuration names, and reports:

### SkillOpt/method responsibilities

- Reflect on training trajectories.
- Generate bounded skill edits.
- Maintain a rejected-edit buffer and optimizer metadata when supported by the pinned upstream version.
- Run the method-private held-out gate.
- Accept or reject a candidate.
- Optionally perform replay/dream rollouts when explicitly enabled.
- Produce the deployable `best_skill.md` artifact.

### SEAGym responsibilities

- Materialize deterministic batches and evaluation views.
- Call the rollout agent and baseline lifecycle.
- Save checkpointed method states.
- Run frozen update-validation and final evaluations.
- Record normalized trajectories, verifier records, metrics, artifact references, cost, and latency.
- Label observed checkpoint changes as beneficial/neutral/harmful if existing SEAGym metrics do so.
- Never feed these labels back into SkillOpt during the same run.

### Leakage rule

The following evidence must never be visible to `SkillOptHoloBaseline.update()` or the SkillOpt gate:

- SEAGym frozen update-validation outcomes;
- SEAGym replay outcomes;
- SEAGym final ID test outcomes;
- SEAGym OOD outcomes;
- cross-harness transfer outcomes;
- any report derived from those views.

Create a `LeakageGuard` with explicit task-ID sets. It must fail closed if any task ID overlaps between:

- `skillopt_train`;
- `skillopt_gate`;
- `seagym_update_val`;
- `seagym_replay` where applicable;
- `seagym_test_id`;
- `seagym_test_ood`.

The private SkillOpt gate must use tasks that are disjoint from both the training trajectories and all SEAGym observer-only evaluation views. If the existing SEAGym split-manifest schema cannot express this extra method-private split, store it as a separate `skillopt_gate.json` referenced only from baseline configuration. Do not overload SEAGym `val` as the SkillOpt gate.

## 3. Version and dependency strategy

Start by inspecting the current repository and existing user changes. Do not overwrite unrelated work. Do not use destructive Git commands.

Run:

```bash
pwd
git status --short
git branch --show-current
git submodule status || true
rg -n "class .*Baseline|class .*RolloutAgent|UpdateResult|TrajectoryBatch|class_path" seagym tests examples runs docs || true
```

If `reference/skillopt` already exists, inspect and preserve it. If it is an existing submodule, initialize it. If it does not exist, add SkillOpt as a pinned submodule only if that is consistent with the repository’s existing `reference/` convention:

```bash
git submodule update --init --recursive

# Only when reference/skillopt is absent:
git submodule add https://github.com/microsoft/SkillOpt.git reference/skillopt
git -C reference/skillopt fetch --tags
git -C reference/skillopt checkout v0.2.0

git -C reference/skillopt describe --tags --always
git -C reference/skillopt status --short
```

Do not edit upstream SkillOpt source directly unless the repository explicitly vendors dependencies instead of using adapters. Prefer an integration layer in SEAGym.

SkillOpt’s `openai_compatible` backend may be present on current `main` but absent from the v0.2.0 tag. Verify rather than assuming:

```bash
rg -n "openai_compatible|configure_openai_compatible" reference/skillopt/skillopt reference/skillopt/docs || true
rg -n "def chat_optimizer|def chat_target|set_backend|configure_" reference/skillopt/skillopt/model || true
```

Compatibility behavior:

1. If the pinned SkillOpt revision contains a working `openai_compatible` backend, use it with H’s base URL.
2. If it does not, implement a thin SEAGym-local `HoloSkillOptBackend` that satisfies the exact function-based SkillOpt backend contract at that pinned revision.
3. Do not copy broad sections of an unreleased upstream branch.
4. Do not silently checkout `main`.
5. Record the SkillOpt version/commit in every run and checkpoint.

Install using the repository’s documented environment first. Avoid creating a second environment when one is already active:

```bash
conda env create -f environment.yml  # only if the documented env does not already exist
conda activate seagym
python -m pip install --upgrade pip
python -m pip install -e ".[dev,models]"
python -m pip install -e reference/skillopt
```

If optional extras differ at the pinned revision, inspect `pyproject.toml` and install only the required extras. Do not guess extra names.

## 4. Required source-tree structure

Prefer this structure, adapting only when existing repository conventions clearly require another location:

```text
seagym/
  integrations/
    skillopt_holo/
      __init__.py
      baseline.py
      rollout_agent.py
      engine.py
      holo_backend.py
      schemas.py
      state.py
      leakage.py
      task_runner.py
      verifier.py
      metrics.py
      reporting.py
      prompts/
        evolve_skill.md
        reflect_trajectory.md
        aggregate_failures.md

runs/
  holo_skillopt_codeopt/
    README.md
    tasks/
      task_index.json
      skillopt_gate.json
    splits/
      split.json
    skills/
      initial_skill.md
    configs/
      deterministic_smoke.json
      codex_holo_gated.json
      claude_holo_gated.json
      codex_holo_gate_off_ablation.json
      codex_static_control.json

examples/
  holo_skillopt_deterministic/
    README.md
    config.json
    fixtures/

tests/
  test_skillopt_holo_baseline.py
  test_skillopt_holo_rollout_agent.py
  test_skillopt_holo_backend.py
  test_skillopt_holo_leakage.py
  test_skillopt_holo_verifier.py
  test_skillopt_holo_checkpoint_resume.py

docs/
  skillopt_holo.md

reference/
  skillopt/
```

The deterministic example must run without H credentials, Codex, Claude, Harbor, Docker, E2B, or external datasets.

## 5. Configuration design

Use SEAGym’s existing JSON config model and `class_path` loading. Do not create a second top-level configuration framework. Add only the smallest optional fields required by this integration.

A representative config should look like this, but adapt field names to the actual validated SEAGym schema instead of bypassing validation:

```json
{
  "experiment_id": "holo_skillopt_codex_codeopt",
  "seed": 42,
  "task_dataset": {
    "path": "../tasks/task_index.json"
  },
  "split_manifest": {
    "path": "../splits/split.json"
  },
  "schedule": {
    "train_size": 20,
    "val_size": 10,
    "test_size": 20,
    "batch_size": 5,
    "num_epochs": 3,
    "num_updates_per_batch": 1
  },
  "backend": {
    "name": "harbor",
    "n_concurrent": 2
  },
  "rollout_agent": {
    "name": "codex_cli_codeopt",
    "class_path": "seagym.integrations.skillopt_holo.rollout_agent:CliCodeOptRolloutAgent",
    "config": {
      "executor": "codex_exec",
      "task_timeout_seconds": 1200,
      "max_agent_steps": 80,
      "network_policy": "disabled",
      "preserve_raw_provider_logs": false
    },
    "models": {}
  },
  "baseline": {
    "name": "skillopt_holo",
    "class_path": "seagym.integrations.skillopt_holo.baseline:SkillOptHoloBaseline",
    "config": {
      "skillopt_source": "repo://reference/skillopt",
      "skillopt_gate_path": "../tasks/skillopt_gate.json",
      "gate_mode": "on",
      "gate_metric": "correctness_gated_performance",
      "gate_no_regression": true,
      "optimizer_backend": "holo_openai_compatible",
      "optimizer_model": "holo3-1-35b-a3b",
      "optimizer_base_url": "https://api.hcompany.ai/v1/",
      "max_edit_operations": 3,
      "max_skill_tokens": 2000,
      "strict_improvement_epsilon": 0.001,
      "evidence_log": true,
      "redact_secrets": true
    },
    "state": {
      "initial_skill": "../skills/initial_skill.md"
    }
  },
  "metrics": {
    "default": true,
    "custom": [
      "seagym.integrations.skillopt_holo.metrics:codeopt_metrics"
    ]
  },
  "output": {
    "run_dir": "results/runs/holo_skillopt_codex_codeopt"
  }
}
```

Secrets must stay in `.env`, never JSON:

```bash
cp .env.example .env  # only if .env does not already exist
```

Add these documented variables to `.env.example` without values:

```dotenv
HAI_API_KEY=
HOLO_BASE_URL=https://api.hcompany.ai/v1/
HOLO_OPTIMIZER_MODEL=holo3-1-35b-a3b
CODEX_EXECUTABLE=codex
CLAUDE_CODE_EXECUTABLE=claude
```

Never print API keys, subprocess environment dumps, complete user transcripts, or provider authorization headers.

## 6. Task specification for CLI code optimization

Define a validated task schema. Prefer argument arrays over untrusted shell strings. Each task must include:

```json
{
  "task_id": "python-prefix-cache-001",
  "repo_url": "https://example.invalid/repository.git",
  "commit": "full-pinned-commit-sha",
  "objective": "Reduce repeated prefix-processing latency without changing outputs.",
  "language": "python",
  "runtime": "python3.11",
  "setup_argv": ["python", "-m", "pip", "install", "-e", ".[test]"],
  "test_argv": ["python", "-m", "pytest", "-q"],
  "benchmark_argv": ["python", "benchmarks/prefix_cache.py", "--json"],
  "benchmark_metric": "requests_per_second",
  "optimization_direction": "maximize",
  "timeout_seconds": 900,
  "forbidden_globs": ["tests/**", "benchmarks/**", ".github/**"],
  "max_changed_files": 12,
  "tags": ["cache", "inference", "id"]
}
```

Support at least these task families in the schema and docs, even if the deterministic fixture implements only two:

- KV-cache reuse and eviction;
- prefix caching;
- redundant tokenization/serialization removal;
- async batching and queueing;
- reward-model scoring throughput;
- FastAPI/vLLM-style inference endpoints;
- memory allocation/copy reduction;
- concurrency and locking bottlenecks;
- GPU-kernel selection or launch overhead where hardware is available.

The deterministic fixtures must be tiny local repositories generated from checked-in files. Do not make unit tests clone remote repositories.

## 7. Normalized trajectory contract

Create Pydantic/dataclass schemas for normalized trajectories. Preserve enough evidence for SkillOpt reflection and SEAGym evaluation while avoiding provider-specific log coupling.

Each trajectory should include:

- task ID and split/view;
- run/checkpoint/update IDs;
- executor (`codex_exec`, `claude_code_exec`, deterministic fake);
- skill version, skill SHA-256 and parent skill SHA-256;
- repository commit before execution;
- sanitized task prompt;
- bounded tool/action event summaries;
- subprocess exit status and timeout reason;
- patch hash, changed-file list and diff statistics;
- correctness before/after;
- benchmark samples before/after;
- aggregate latency/throughput/memory metrics;
- forbidden-edit and benchmark-tampering checks;
- tokens, tool calls, wall time and estimated cost;
- terminal status such as `success`, `test_failure`, `policy_failure`, `timeout`, `agent_error`, `benchmark_error`;
- paths to local artifacts rather than embedding large raw logs.

Convert this record into whatever exact conversation/rollout format the pinned SkillOpt reflection stage expects. Preserve a stable mapping from SkillOpt item IDs back to SEAGym task/trajectory IDs.

## 8. Holo backend requirements

Use the H Models API at:

```text
https://api.hcompany.ai/v1/
```

The backend must:

- read `HAI_API_KEY` from the environment;
- use the official `openai` Python client or the exact client already used by SkillOpt;
- require `holo3-1-35b-a3b` for optimizer calls and reject other model IDs rather than silently changing model behavior;
- clamp proposal output to the model's 4,096-token maximum;
- use strict structured outputs with tools disabled for mutation calls, followed by local semantic validation; this is an auditability and reproducibility policy, not a workaround for missing tool support;
- use bounded retry with exponential backoff only for retryable statuses;
- surface authentication, model-access, rate-limit, malformed-output, timeout, and provider errors distinctly;
- record token usage and latency where returned;
- never convert provider failures into a silent zero score;
- never persist authorization headers or raw secrets;
- make tests use a fake client—unit tests must never call H.

Define a strict schema similar to:

```python
from typing import Literal
from pydantic import BaseModel, Field


class SkillEdit(BaseModel):
    operation: Literal["add", "delete", "replace"]
    section: str
    old_text: str | None = None
    new_text: str | None = None
    rationale: str
    evidence_ids: list[str] = Field(default_factory=list)


class SkillUpdateProposal(BaseModel):
    diagnosis: list[str]
    edits: list[SkillEdit]
    expected_effects: list[str]
    risks: list[str]
```

Enforce after parsing:

- no more than `max_edit_operations`;
- every evidence ID exists in the provided training batch;
- delete/replace operations must target exact existing text;
- no edits can inject repository-specific answers, secret material, benchmark outputs, task IDs, absolute paths, or held-out evidence;
- final skill length must be within the configured token/character budget;
- identical/no-op proposals are represented as `changed=False`;
- malformed or ambiguous patches are rejected safely and recorded.

Do not request or store Holo’s hidden reasoning trace. Persist only the structured proposal, concise model-provided rationale, usage, latency, and error metadata needed for reproducibility.

## 9. SkillOpt integration requirements

Use SkillOpt’s real abstractions wherever possible. Do not reimplement a separate optimizer and merely call it SkillOpt.

First inspect:

```bash
rg -n "class EnvAdapter|class SplitDataLoader|def reflect|def aggregate|def select|def update|best_skill" reference/skillopt/skillopt
rg -n "gate_mode|gate_no_regression|rejected|learning.rate|meta" reference/skillopt/skillopt reference/skillopt/skillopt_sleep
rg -n "codex_exec|claude_code_exec|codex_harness" reference/skillopt/skillopt reference/skillopt/plugins
```

Then implement a narrow `SkillOptEngine` façade so the rest of SEAGym does not import dozens of unstable internals. Its public interface should be approximately:

```python
class SkillOptEngine(Protocol):
    def initialize(self, *, initial_skill: str, state_dir: Path) -> SkillOptState: ...

    def propose(
        self,
        *,
        current_skill: str,
        training_trajectories: list[NormalizedTrajectory],
        rejected_edit_buffer: list[dict],
    ) -> SkillUpdateProposal: ...

    def evaluate_gate(
        self,
        *,
        current_skill: str,
        candidate_skill: str,
        gate_tasks: list[CodeOptTask],
    ) -> GateDecision: ...

    def consolidate(
        self,
        *,
        prior_state: SkillOptState,
        proposal: SkillUpdateProposal,
        gate_decision: GateDecision,
    ) -> SkillOptState: ...
```

The façade may adapt names to the real upstream API, but preserve these semantic boundaries.

SkillOpt-Sleep is optional in the primary online/batch integration. Do not invoke `skillopt-sleep adopt` behind SEAGym’s back or mutate a user-global skill. If Sleep is integrated, implement it as an explicit offline command that:

1. harvests only artifacts from one selected SEAGym run;
2. writes to a run-local staging directory;
3. performs a dry run by default;
4. requires an explicit adopt command;
5. records the adopted artifact as a new externally supplied initial state for a future SEAGym run;
6. never changes a checkpoint inside an already completed SEAGym run.

The main experiment should provide three method variants:

- `static_control`: skill never changes;
- `skillopt_holo_gated`: default SkillOpt strict-improvement gate with no-regression enabled;
- `skillopt_holo_gate_off_ablation`: bounded proposals are applied without the private gate, while SEAGym still passively evaluates every checkpoint.

## 10. Baseline implementation

Implement `SkillOptHoloBaseline` against the **actual** `BaseBaseline`, `BaselineState`, `Checkpoint`, and `UpdateResult` definitions in the checked-out SEAGym revision. Do not rely only on documentation snippets.

The update flow must be:

```python
def update(self, trajectories, state):
    # 1. Validate that trajectories are train-view only.
    # 2. Allocate a deterministic update directory.
    # 3. Persist sanitized normalized training evidence.
    # 4. Read current skill and verify its stored hash.
    # 5. Ask SkillOpt/Holo for a bounded proposal.
    # 6. Apply the proposal to a temporary candidate skill.
    # 7. Evaluate current and candidate skills on the private SkillOpt gate.
    # 8. Let SkillOpt accept/reject according to its configured method policy.
    # 9. Atomically persist the resulting method state.
    # 10. Return UpdateResult with metrics, status, logs, and artifact paths.
```

Use statuses that clearly attribute decisions:

- `accepted_by_skillopt_gate`;
- `rejected_by_skillopt_gate`;
- `applied_gate_off_ablation`;
- `no_op_proposal`;
- `invalid_proposal`;
- `optimizer_error`;
- `gate_execution_error`.

Never use `accepted_by_seagym`, `promoted`, `champion`, or similar language.

`UpdateResult.changed` is true only when the checkpointed deployed skill bytes differ from the previous checkpoint. A rejected proposal must produce `changed=False`, while still recording proposal/gate artifacts.

Each update directory must contain, where applicable:

```text
update_0001/
  trajectories.jsonl
  skill_before.md
  proposal.json
  candidate_skill.md
  gate_results_current.json
  gate_results_candidate.json
  gate_decision.json
  deployed_skill_after.md
  diff.patch
  usage.json
  diagnostics.json
```

The checkpoint state must contain:

```text
checkpoint_dir/
  best_skill.md
  state.json
  rejected_edits.jsonl
  update_history.jsonl
```

`state.json` must include schema version, skill version, current hash, parent hash, SkillOpt version/commit, SEAGym version/commit, Holo model ID, optimizer prompt hash, target executor, gate mode, task split hashes, accepted/rejected counts, cumulative optimizer usage, and latest update status.

Checkpoint save/load and resume must be deterministic and must not require an H API call.

## 11. Rollout-agent and subprocess requirements

Implement one configurable `CliCodeOptRolloutAgent` rather than duplicating all logic for Codex and Claude Code. Use an executor strategy selected by `executor`.

Before implementation, inspect SkillOpt’s existing `codex_exec`, `claude_code_exec`, and shared `codex_harness.py`. Reuse them when compatible. Otherwise write thin adapters around the installed CLIs.

Requirements:

- create a fresh isolated workspace per task;
- checkout only the pinned task commit;
- run baseline correctness and benchmark commands before agent modification;
- install the checkpointed skill using the harness-appropriate mechanism;
- launch the CLI non-interactively with explicit timeout and maximum steps;
- prevent the executor from editing tests, benchmarks, task metadata, `.git`, or verifier code;
- disable task-workspace network access by default;
- capture stdout/stderr to bounded files and redact secret-shaped strings;
- terminate the process group on timeout;
- compute a patch from the pinned commit after execution;
- run edit-policy verification before final tests/benchmarks;
- use repeated benchmark samples and deterministic warmup where possible;
- return a valid SEAGym `TrajectoryBatch` even for failed tasks;
- do not score infrastructure failure as an ordinary incorrect answer;
- avoid shell interpolation of task-supplied strings.

If Harbor already owns checkout, isolation, and command execution, integrate through Harbor instead of creating a competing sandbox implementation. Keep the boundary clear: Harbor/environment executes commands; the rollout agent selects prompts/skills and normalizes results.

## 12. Initial skill

Ship a compact neutral initial skill, approximately 300–700 tokens:

```markdown
# Evidence-Guided Code Optimization

## Establish the baseline
- Read the task, repository instructions, tests, and benchmark entrypoint.
- Run the authoritative correctness test and benchmark before editing.
- Record variance; do not infer a speedup from one noisy sample.

## Locate the measured bottleneck
- Trace the production path exercised by the benchmark.
- Separate compute, I/O, allocation, serialization, and synchronization costs.
- Prefer profiler or counter evidence over source-level intuition.

## Make bounded changes
- Modify the smallest production-code region that explains the bottleneck.
- Do not edit tests, benchmark logic, inputs, timing code, or verifier files.
- Preserve public behavior and APIs unless the task explicitly allows a change.

## Verify
- Run correctness checks before performance checks.
- Repeat benchmarks using the same setup and report variance.
- Inspect throughput, tail latency, and memory separately when available.

## Recover from failure
- If correctness fails, identify the semantic assumption before making more edits.
- If performance regresses, remove incidental changes and remeasure the narrow path.
```

Holo may improve the procedure, but it must never add task-specific code or answers.

## 13. Verifier and scoring design

Keep correctness and performance separate in reports. Implement:

- `correctness_pass`: all authoritative tests pass;
- `edit_policy_pass`: no forbidden edits or benchmark tampering;
- `infra_valid`: setup/test/benchmark infrastructure completed normally;
- `speedup`: direction-aware ratio using robust central estimates;
- `latency_delta_pct`;
- `throughput_delta_pct`;
- `peak_memory_delta_pct` when available;
- `benchmark_cv` or another noise estimate;
- `wall_time_seconds`;
- `tool_calls`;
- target tokens/cost;
- optimizer tokens/cost;
- regression and timeout indicators.

Use a correctness-gated soft score compatible with SkillOpt’s hard/soft convention. One acceptable mapping is:

```python
def correctness_gated_performance(result) -> float:
    if not result.infra_valid:
        raise InfrastructureError(result.infrastructure_error)
    if not result.correctness_pass or not result.edit_policy_pass:
        return 0.0
    log_speedup = math.log(max(result.speedup, 1e-9))
    return 0.5 + 0.5 * math.tanh(log_speedup)
```

Also persist the untransformed metrics. The gate should default to lexicographic/verifier-disciplined behavior:

1. no gate task may regress from pass to fail when `gate_no_regression=true`;
2. missing/non-finite gate results block acceptance;
3. correctness and edit-policy pass rate must not decrease;
4. aggregate configured gate metric must improve by more than `strict_improvement_epsilon`;
5. infrastructure failures produce `gate_execution_error`, not candidate rejection masquerading as a valid score.

SEAGym’s own evaluation views must calculate the same underlying metrics independently from normalized records, not read the SkillOpt gate decision as ground truth.

## 14. Evaluation plan

Build split materialization and configs for:

- `skillopt_train`: exposed to SkillOpt reflection;
- `skillopt_gate`: private method gate, not exposed to SEAGym observer evaluation;
- `seagym_update_val`: frozen intermediate checkpoint assessment;
- `seagym_test_id`: unseen repositories with familiar bottleneck families;
- `seagym_test_ood`: different language, framework, or bottleneck family;
- `seagym_replay`: earlier exposed tasks for forgetting diagnostics.

Add cross-harness transfer evaluation:

- evolve with Codex, evaluate the frozen skill with Codex and Claude Code;
- evolve with Claude Code, evaluate the frozen skill with Claude Code and Codex;
- never update the skill during cross-harness evaluation.

Recommended experiment matrix:

| Condition | Target executor | Optimizer | Skill update policy |
|---|---|---|---|
| Static control | Codex | none | static |
| Static control | Claude Code | none | static |
| Holo-SkillOpt | Codex | Holo3.1 35B | strict private gate |
| Holo-SkillOpt | Claude Code | Holo3.1 35B | strict private gate |
| Gate-off ablation | Codex | Holo3.1 35B | apply bounded edits |

Reports must compare `A_0`, every update checkpoint, and final held-out results. Include:

- success rate;
- geometric-mean speedup among correct runs;
- p95 latency and memory changes;
- harmful/neutral/beneficial checkpoint labels where SEAGym already computes them;
- replay forgetting;
- forbidden-edit rate;
- timeout and infrastructure-failure rate;
- SkillOpt candidate acceptance rate;
- target and optimizer cost separately;
- cross-harness transfer delta.

## 15. Deterministic smoke implementation

The checked-in smoke test must exercise the complete control flow without external tools:

1. A fake rollout agent operates on two tiny fixture repositories.
2. A fake Holo client emits one valid bounded edit, one invalid edit, and one no-op in deterministic sequence.
3. A fake SkillOpt gate accepts the improving edit and rejects the regressing edit.
4. SEAGym writes `A_0`, updated checkpoints, normalized records, and a summary.
5. Resume from a saved checkpoint produces byte-identical final state and metrics.

The smoke command should be:

```bash
seagym train examples/holo_skillopt_deterministic/config.json
```

If the console script is unavailable:

```bash
python scripts/seagym.py train examples/holo_skillopt_deterministic/config.json
```

No test may depend on real API keys, installed Codex/Claude binaries, Docker, E2B, Harbor capacity, or network access.

## 16. Tests

Implement at minimum:

### Unit tests

- Holo structured-output schema accepts valid output.
- Malformed JSON fails safely.
- More than the configured number of edits is rejected.
- Replace/delete must match exact source text.
- Evidence IDs must belong to the current training batch.
- A proposal containing held-out task IDs is rejected.
- Secret-shaped strings are redacted from evidence artifacts.
- A strict-improvement gate accepts only a real improvement.
- `gate_no_regression` blocks a task-level regression.
- Infrastructure failure is distinct from model failure.
- Rejected candidate leaves deployed skill bytes unchanged.
- Gate-off ablation applies a valid bounded edit.
- `UpdateResult.changed` reflects deployed bytes, not proposal existence.
- Checkpoint save/load round-trips all state.
- Split-overlap/leakage checks fail closed.
- Cost and token accounting do not mix target and optimizer usage.
- Forbidden-file changes invalidate a solution.
- Direction-aware benchmark ratios are correct for minimize/maximize metrics.

### Integration tests

- End-to-end deterministic training writes expected checkpoint artifacts.
- `seagym eval --checkpoint ...` does not call SkillOpt update or Holo.
- Resume does not repeat an already committed SkillOpt update.
- A fake Codex/Claude executable can be launched and timed out safely.
- Config inspection recognizes all integration classes.
- Reports do not claim SEAGym accepted/rejected an update.

Run:

```bash
python -m unittest discover -s tests
python -m pytest -q  # only if pytest is already an accepted project dependency
git diff --check
```

Do not add pytest solely to duplicate an existing unittest-only project unless justified.

## 17. Preflight and execution commands

After implementation, run deterministic checks:

```bash
python -m pip install -e ".[dev,models]"
python -m pip install -e reference/skillopt

seagym inspect config examples/holo_skillopt_deterministic/config.json
seagym inspect env
seagym inspect runtime examples/holo_skillopt_deterministic/config.json
seagym train examples/holo_skillopt_deterministic/config.json --run-name holo-skillopt-smoke

python -m unittest discover -s tests
git diff --check
git status --short
```

Add a separate credentialed Holo preflight command that performs one minimal structured-output request and nothing else:

```bash
python -m seagym.integrations.skillopt_holo.holo_backend \
  --preflight \
  --model "${HOLO_OPTIMIZER_MODEL:-holo3-1-35b-a3b}"
```

Then document real-run commands, but do not execute them without credentials, installed CLIs, task data, and explicit operator intent:

```bash
seagym inspect config runs/holo_skillopt_codeopt/configs/codex_holo_gated.json
seagym inspect runtime runs/holo_skillopt_codeopt/configs/codex_holo_gated.json
seagym train runs/holo_skillopt_codeopt/configs/codex_holo_gated.json

seagym inspect config runs/holo_skillopt_codeopt/configs/claude_holo_gated.json
seagym train runs/holo_skillopt_codeopt/configs/claude_holo_gated.json
```

Respect Holo3.1 free-tier limits in examples. Default concurrency for a first real smoke run must be `1`; paper/hackathon configs may increase it explicitly.

## 18. Safety, privacy, and reproducibility

- Pin repository commits and dependency versions.
- Record tool versions using safe version commands.
- Do not persist full environment-variable dumps.
- Redact common API-key/token patterns before writing evidence.
- Keep raw session transcripts opt-in and run-local.
- Store only bounded trajectory excerpts for Holo reflection.
- Treat task repository content and transcripts as potentially untrusted.
- Never execute commands suggested by Holo; Holo edits only the skill document.
- Validate all task commands from trusted checked-in task metadata.
- Disable network inside optimization tasks by default.
- Preserve provider errors and infrastructure errors without converting them to ordinary task scores.
- Use atomic state writes followed by rename, and fsync where the existing repository convention supports it.
- Include schema versions in serialized state.
- Use stable ordering and seeded sampling.
- Hash initial skills, split manifests, prompts, and task specs.
- Never modify global Codex or Claude skills during a run; install skill state into the isolated task workspace.

## 19. Optional partner extensions—not part of MVP acceptance

Do not delay the Holo/SkillOpt/SEAGym implementation for these:

- **Pioneer:** later train a compact proposal-quality ranker from Holo proposal features and SkillOpt gate labels. It must not replace the deterministic verifier. Keep exported training records free of secrets and held-out SEAGym test evidence.
- **fal.ai:** use only if a visual artifact or demo UI materially improves judging. Do not route core evaluation or skill optimization through fal.ai.
- **HoloDesktop/Holo3.1 visual supervisor:** optionally inspect a GUI profiler, browser benchmark dashboard, or live app after the CLI implementation works. Keep it outside deterministic core scoring.

## 20. Documentation requirements

Add `docs/skillopt_holo.md` covering:

- the method/evaluator boundary;
- architecture and data flow;
- exact split/leakage policy;
- installation;
- environment variables;
- deterministic smoke run;
- Holo preflight;
- Codex and Claude Code executor setup;
- task schema;
- metric definitions;
- checkpoint/artifact layout;
- resume and evaluation commands;
- known limitations;
- SkillOpt v0.2.0 versus later-main compatibility behavior;
- privacy implications of sending trajectory excerpts to H;
- troubleshooting for auth, rate limits, CLI absence, sandbox timeout, malformed model output, and gate infrastructure failure.

Update the main README with only a concise integration link and smoke command. Do not replace SEAGym’s primary positioning.

## 21. Acceptance criteria

The implementation is complete only when all of the following are true:

1. SEAGym’s passive boundary is preserved and tested.
2. SkillOpt is the actual bounded-edit/gating method, not a renamed custom optimizer.
3. Holo3.1 35B works through a version-compatible strict structured-output backend, and unsupported optimizer model IDs fail closed.
4. The deterministic smoke run requires no external services.
5. Codex and Claude Code are selectable through one rollout-agent abstraction.
6. SkillOpt gate tasks are disjoint from SEAGym validation/test/replay views.
7. A rejected SkillOpt proposal leaves checkpointed skill bytes unchanged.
8. Every proposal and gate decision remains auditable.
9. Checkpoint evaluation never calls the updater.
10. Resume is deterministic and does not repeat committed updates.
11. Correctness, performance, cost, reliability, and forgetting metrics are separate.
12. Unit and deterministic integration tests pass.
13. Config/environment/runtime inspection passes for the deterministic example.
14. Documentation includes runnable commands and no embedded secrets.
15. `git diff --check` passes and unrelated user changes remain untouched.

## 22. Required implementation workflow and final response

Work in this order:

1. Inspect repository state, architecture, tests, configuration schemas, and extension interfaces.
2. Inspect the pinned SkillOpt implementation and resolve its exact backend and benchmark contracts.
3. Write a short implementation plan tied to concrete files.
4. Implement schemas, leakage guard, state handling, deterministic fakes, and tests first.
5. Implement the Holo backend and SkillOpt façade.
6. Implement baseline and rollout agent.
7. Add metrics, reports, configs, fixtures, and documentation.
8. Run deterministic preflight, smoke run, full tests, and diff checks.
9. Inspect generated artifacts and verify terminology.
10. Summarize results.

Do not stop after planning. Do not ask broad clarification questions when repository inspection can resolve them. If an exact upstream API differs from this specification, adapt to the checked-out code and document the difference. If a credentialed or external test cannot run, finish all deterministic work and label the unexecuted command precisely.

Your final response must include:

- outcome first;
- files added/modified;
- architecture implemented;
- commands executed and results;
- deterministic smoke-run artifact path;
- tests passed/failed/skipped;
- external prerequisites still required;
- any deviations from this specification with reasons;
- a short next-command block for the operator.

Do not claim real Holo, Codex, Claude, Harbor, Docker, or E2B execution unless it actually occurred.
