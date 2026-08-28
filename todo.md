# TODO — HoloSkill Gym implementation roadmap

The control plane is implemented: Holo can produce strict bounded proposals,
SkillOpt owns the private acceptance gate, SEAGym remains a passive evaluator,
checkpoint state is hash-verified, and Harbor selects Codex or Claude Code.
The normalized evidence, strict verifier, fixture repositories, deterministic
verification smoke, report metrics, experiment configs, and completed-final
resume/eval lifecycle coverage are now implemented. The next milestone is to
provision and execute trusted production Harbor tasks, then harden the
remaining executor and durability edges.

Status legend: `[ ]` not started · `[~]` in progress · `[x]` done

---

## Priority implementation roadmap

### 1. Resolve specification and roadmap drift

- [x] Establish one authoritative optimizer-model policy. The integration is
      now formally 35B-only: `holo3-1-35b-a3b` is required for SkillOpt
      mutation, the implementation prompt supersedes its older 122B language,
      and unsupported optimizer model IDs fail closed.
- [x] Update `agents.md` and the deferred executor backlog below so they reflect
      the implemented Harbor binding. `CliCodeOptRolloutAgent` now selects
      Harbor's built-in `codex` or `claude-code` agent; it is no longer an
      unimplemented class awaiting a custom Harbor-side executor.
- [x] Correct the prerequisite status for vendored dependencies. The primary
      SEAGym submodules are present; only the private or removed nested
      `reference/ace/ace-eval` checkout is absent and is not required for this
      integration.
- [x] Audit the existing dirty root documentation and the modifications reported
      inside vendored submodules before changing either dependency. Preserve
      user-owned work and distinguish substantive edits from line-ending-only
      changes.

Audit recorded on 2026-08-26:

- Root `.env.example`, `README.md`, and `codebase-overview.md` contain
  substantive user-owned 35B-policy documentation changes. They were preserved.
- `reference/seagym` and `reference/skillopt` report broad working-tree changes
  caused by LF-to-CRLF conversion. Representative source and documentation
  files match their pinned Git blobs after removing carriage returns; no
  vendored file was normalized or reset.
- Superseded for `reference/seagym` only. Two deliberate patches are applied to
  the pinned checkout: `patches/seagym-redaction-usage-keys.patch` preserves
  numeric token telemetry, and `patches/seagym-final-resume-idempotence.patch`
  prevents duplicate final evaluation on completed-run resume. Both are applied
  by `scripts/apply-vendor-patches`, never committed into the submodule, and the
  pin stays `9e61e14`. The redaction fix was proposed upstream as
  [SEAGym#2](https://github.com/antropy-research/SEAGym/pull/2); drop the patch
  and move the pin once it lands.
- SEAGym's `reference/ace`, `reference/agentic-harness-engineering`,
  `reference/harbor`, and `reference/tf-grpo` submodules are initialized. The
  nested private or removed `reference/ace/ace-eval` submodule is the sole
  missing checkout and is not required here.

### 2. Implement normalized code-optimization evidence

Implementation reference: [Verifiers v1 — Harbor integration](docs/verifiers-v1-harbor.md)
defines the HarborTaskset, reward, artifact, timeout, network, and separate-grader
contracts that the normalized evidence layer must preserve. The runtime fields
and trust boundaries are catalogued in
[Harbor task and agentic-environment structure](docs/harbor-task-structure.md).

- [x] Add a dedicated normalized trajectory/verifier layer, for example
      `holoskill_gym/trajectory.py` and `holoskill_gym/verifier.py`, that reads
      each Harbor trial's `result_path` and canonical ATIF trajectory.
- [x] Validate ATIF before consuming it and retain only bounded summaries plus
      local artifact paths. Put project-specific fields under
      `extra.holoskill_gym`; do not invent a second provider-specific transcript
      format or persist hidden reasoning content.
- [x] Normalize task ID, split/view, run/checkpoint/update IDs, executor and
      model identity, skill version and hashes, parent hash, repository commit,
      sanitized prompt, bounded tool/action summaries, exit status, timeout
      reason, and terminal status.
- [x] Normalize patch hash, changed-file list, diff statistics, correctness
      before/after, edit-policy and tampering checks, benchmark samples
      before/after, latency/throughput/memory aggregates, wall time, tool calls,
      target tokens/cost, and artifact paths.
- [x] Wire this normalized record into both SEAGym reporting and SkillOpt
      reflection. `normalize_training_evidence()` currently reduces production
      trajectories to coarse success, score, reward, runtime, and error fields,
      so Holo cannot yet learn from the evidence described by the ATIF contract.
- [x] Support multiple attempts per task by aggregating or assigning stable
      attempt-level evidence IDs. Do not reject a valid Harbor batch merely
      because several attempts share one task ID.
- [x] Replace whole-payload character slicing with deterministic per-record and
      per-field evidence budgets so later records are not silently removed from
      the optimizer prompt.

### 3. Connect the task schema and verifier to Harbor

Task-authoring references:
[Harbor task and agentic-environment structure](docs/harbor-task-structure.md)
defines the production single-step package and agentic runtime boundary, while
[Harbor multi-step tasks](docs/harbor-multi-step-tasks.md) defines the future
sequential-task extension. The
[Verifiers v1 Harbor bridge](docs/verifiers-v1-harbor.md) documents which Harbor
features are currently supported and which parity gaps must remain fail-closed.

- [~] Integrate `CodeOptTask`, `verify_edit_policy()`, and code-optimization
      metrics with Harbor task materialization. The production verifier drives
      checked-in repositories and normalized smoke records, but trusted
      production Harbor packages remain an external prerequisite.
- [~] Create a fresh isolated workspace for every task and checkout exactly the
      pinned commit. Validate the source repository and record its resolved
      commit before the agent runs.
- [x] Run authoritative baseline correctness and benchmark commands before the
      agent edits anything. Use repeated samples, deterministic warmup, robust
      central estimates, and a recorded noise measure where practical.
- [x] Install the checkpointed skill only through Harbor's task-local prompt or
      skill mechanism. Never mutate a user-global Codex or Claude directory.
- [x] Enforce protected files before final verification: tests, benchmarks,
      task metadata, `.git`, verifier code, and configured forbidden globs must
      not be changed. Compute the patch from the pinned commit and run edit
      policy checks before final tests and benchmarks.
- [~] Disable task-workspace network access by default, set explicit agent and
      verifier timeouts, enforce maximum agent steps where the harness supports
      them, and rely on Harbor to terminate timed-out execution.
- [x] Return valid failed trajectories for agent, timeout, policy, test, and
      benchmark failures. Treat missing or broken infrastructure as an
      infrastructure error, never as an ordinary incorrect solution.
- [~] Add production Harbor task datasets and configs for Codex gated, Claude
      Code gated, Codex static control, Claude static control, and the gate-off
      ablation. Keep first-run concurrency at one.
- [x] Ship a neutral production initial skill of roughly 300–700 tokens. Keep
      the tiny deterministic skill as a smoke fixture rather than treating it
      as the production starting point.

### 4. Make executor configuration strict and effective

- [ ] Define and validate the supported `CliCodeOptRolloutAgent` configuration
      instead of silently ignoring unknown keys. Reject unsupported fields with
      an actionable error.
- [ ] Map task timeout, verifier timeout, maximum steps, network policy, attempt
      policy, raw-log retention, and executor-specific controls to the actual
      Harbor task, backend, or agent configuration that enforces them.
- [ ] Pass target reasoning effort explicitly through Harbor agent kwargs for
      both Codex and Claude Code and record the applied value in ATIF. Do not
      rely on `OPENAI_REASONING_EFFORT`, which the current Harbor binding does
      not consume automatically.
- [ ] Reconcile `CODEX_EXECUTABLE` and `CLAUDE_CODE_EXECUTABLE` documentation
      with Harbor's sandbox-installed agents. Remove unused variables or add a
      real, tested override path; do not claim they are required when the
      implementation ignores them.
- [ ] Validate executor/model compatibility and required credentials during
      runtime inspection without printing secret values.

### 5. Correct gate metrics and cost accounting

- [x] Define a strict verifier-result schema with explicit
      `correctness_pass`, `edit_policy_pass`, `infra_valid`, benchmark samples,
      and infrastructure error fields. Do not infer correctness from the generic
      `trajectory.success` flag.
- [x] Make the private runtime gate consume those explicit verifier fields.
      Missing, malformed, or non-finite results must produce
      `gate_execution_error`, not a candidate rejection or zero score.
- [x] Implement robust direction-aware speedup, latency/throughput/memory
      deltas, benchmark coefficient of variation, regression indicators, and a
      bounded correctness-gated soft-score transform. Do not clip arbitrary raw
      speedups to `[0, 1]`, because that collapses distinct improvements.
- [x] Register the code-optimization metrics with SEAGym so observer views
      independently compute the same underlying metrics without reading the
      SkillOpt gate decision as ground truth.
- [x] Expose optimizer usage in the update-cost structure recognized by
      SEAGym. The current deterministic artifacts record optimizer tokens in
      method state while the generated `agent_update` token metric remains
      zero.
- [x] Persist target and optimizer usage/cost in separate namespaced records.
      ATIF `final_metrics.total_cost_usd` must remain target-only; optimizer
      spend belongs to method/update state. Remove or rename any ambiguous
      aggregate that encourages the two roles to be conflated.
- [x] Report candidate acceptance, invalid proposal, no-op, optimizer failure,
      and gate infrastructure rates separately. Gate-off application must not
      be mislabeled as private-gate acceptance.

### 6. Preserve audit data on failures and harden privacy

- [ ] Refactor proposal execution into staged outcomes so a parsed but
      semantically invalid proposal still records the structured response,
      response metadata, reflection usage, proposal-call usage, and validation
      diagnostics. Usage incurred before a later optimizer or gate failure must
      also be counted.
- [ ] Record safe metadata for malformed and truncated responses. Classify
      invalid JSON returned with `finish_reason=length` as truncation and retain
      returned usage when the provider supplies it.
- [ ] Mark `HoloBackendConfig.api_key` as excluded from dataclass `repr` and add
      regression tests proving configuration objects and exceptions cannot
      expose the key.
- [ ] Apply secret and absolute-path policy to every model-provided proposal
      field, including diagnosis, expected effects, risks, rationale, section,
      and edit operands—not only inserted skill text.
- [ ] Strengthen evidence and log redaction for standalone API-key shapes,
      bearer tokens, authorization values, nested sensitive keys, and provider
      stdout/stderr. Persist redacted bounded summaries and artifact paths
      instead of complete captured logs in normalized records.
- [ ] Derive and pass real forbidden benchmark/repository fragments to proposal
      validation so the policy can detect task-specific material beyond task IDs
      and generic secret/path patterns.
- [ ] Add artifact-level secret scanning tests covering update directories,
      SEAGym normalized records, checkpoint metadata, reports, and Harbor
      references.

### 7. Strengthen proposal schemas and state durability

- [ ] Generate the proposal request schema per batch so `evidence_ids` are an
      enum of the current training evidence and `section` is an enum of unique
      headings in the current skill. Keep all local semantic checks after
      parsing.
- [ ] Replace nullable edit fields with discriminated `AddEdit`, `DeleteEdit`,
      and `ReplaceEdit` variants so illegal field combinations cannot be
      represented in structured output.
- [ ] Add an explicit versioned `edit`/`noop` envelope. Require a non-empty edit
      list for `edit`, an empty list and concise explanation for `noop`, and a
      known schema/policy version for both.
- [ ] Add schema-level list and string limits for diagnosis, edits, rationale,
      evidence IDs, expected effects, and risks. Continue enforcing final skill
      token/character limits locally.
- [ ] Make `StateStore.commit()` transactionally recoverable across
      `best_skill.md`, `state.json`, `update_history.jsonl`, and
      `rejected_edits.jsonl`. A crash between writes must be recoverable rather
      than leaving a permanent skill/state hash mismatch.
- [ ] Add a state migration strategy before introducing schema version 2 and
      test loading, rejecting, or migrating every supported historical version.
- [ ] Record actual SkillOpt, SEAGym, Harbor, and project Git revisions plus a
      dirty-state indicator instead of only hard-coded commit strings. Hash the
      complete task specifications, effective configuration, prompts, initial
      skill, and split manifests needed to reproduce a run.
- [ ] Commit a root dependency lockfile so the editable submodule pins and all
      transitive Python dependencies can be reconstructed deterministically.

### 8. Add deterministic integration and CI coverage

- [x] Add a pytest integration test that invokes `seagym train` against the
      deterministic config in a temporary run directory and inspects all
      expected checkpoints, normalized records, update artifacts, metrics, and
      reports.
- [ ] Extend the deterministic fake sequence to emit a valid improvement, an
      invalid proposal, a regressing proposal rejected by the gate, and an
      intentional no-op. Assert deployed bytes and status attribution after
      every update.
- [x] Verify `seagym eval --checkpoint ...` never calls SkillOpt reflection,
      Holo proposal generation, or baseline update.
- [~] Resume from an intermediate and a final checkpoint. Completed-final
      resume is integration-tested as idempotent; intermediate trainer recovery
      remains open. Assert committed updates are not repeated and that final
      state, deployed skill, metrics, and reports are byte-identical.
- [~] Exercise fake Codex and Claude executables, including non-interactive
      launch, bounded stdout/stderr, timeout, process-group termination, and
      failed-trajectory normalization, without requiring real credentials or
      network access.
- [x] Validate generated ATIF with Harbor's validator and assert all
      HoloSkill-specific extensions live under `extra.holoskill_gym`.
- [~] Run config and runtime inspection for deterministic and production
      configs in CI. Test that unsupported executor settings fail instead of
      being ignored.
- [x] Give the deterministic rollout an explicit fake identity. The fixture
      reports `deterministic-codeopt-fixture`, never Codex or Claude Code.
- [~] Add report assertions for separate correctness, performance, reliability,
      target cost, optimizer cost, forgetting, and candidate disposition. Also
      assert reports never claim SEAGym accepted or rejected a proposal.
- [ ] Add CI commands for root pytest, Ruff, deterministic training, checkpoint
      evaluation, resume, `git diff --check`, and artifact secret scanning.

### 9. Documentation, production evaluation, and deferred extensions

- [x] Add `docs/skillopt_holo.md` covering architecture, method/evaluator
      boundaries, split policy, installation, credentials, task schema,
      executor setup, metric definitions, artifacts, resume/eval commands,
      privacy, troubleshooting, and known limitations.
- [x] Keep the main README concise and link to the detailed guide. Clearly mark
      the ATIF mapping and production experiment matrix as implemented only
      after their corresponding code and tests land.
- [ ] Run the production Codex and Claude gated/static experiments only after
      credentials, CLIs, Harbor capacity, and trusted code-optimization tasks
      are explicitly available. Record unexecuted external prerequisites rather
      than simulating success.
- [~] Cross-harness transfer configs and frozen-skill eval support are present:
      evolve with Codex and evaluate on Claude Code, then reverse the direction.
      Trusted production runs remain unexecuted until their external
      prerequisites are available; transfer eval never updates skill.
- [ ] Defer Claude Agent SDK and OpenAI Agents SDK executors until the CLI MVP,
      verifier, accounting, privacy, and cross-harness evaluation paths are
      complete. Additional harnesses should reuse the same normalized evidence
      and sandbox contracts rather than introduce parallel implementations.

---

## Production runtime integration — Harbor CLI, Docker, and credentials

Complete these steps in order. Harbor and Docker are trusted execution
dependencies; provider checks may spend tokens and therefore come only after
credential-free task validation. Keep `backend.n_concurrent: 1` until the
single-task gated canary has produced a valid ATIF record, verifier result, and
role-separated cost report.

### A. Install and pin the Harbor CLI in the project environment

- [ ] Initialize the Harbor checkout at the revision pinned through SEAGym and
      record both the SEAGym and nested Harbor SHAs in the production run
      manifest. Do not install an unrelated global Harbor build: SEAGym and the
      `harbor` command must use the same checked-in API version.
- [ ] Install Harbor into `.venv-linux` alongside this project, SkillOpt, and
      SEAGym, using the editable source already declared by `pyproject.toml`:

      ```bash
      uv venv --python 3.12 .venv-linux
      UV_CACHE_DIR=/tmp/cua-holo-uv-cache uv pip install \
        -e '.[dev]' \
        -e 'reference/skillopt[dev]' \
        -e 'reference/seagym[models]' \
        -e reference/seagym/reference/harbor
      ```

- [ ] Verify command and import discovery from the same interpreter. The
      printed import path must point inside this checkout, not a system package:

      ```bash
      .venv-linux/bin/harbor --help
      .venv-linux/bin/python -c "import harbor; print(harbor.__file__)"
      .venv-linux/bin/seagym inspect env
      bash scripts/apply-vendor-patches --check
      ```

- [ ] Run `seagym inspect config` and `seagym inspect runtime` for every file
      under `examples/holo_skillopt_matrix/configs/`. Treat a missing Harbor
      executable, unresolved Harbor class, missing task path, incompatible
      executor/model pair, or unsupported environment as a blocking preflight
      failure.
- [ ] Extend runtime inspection to report the resolved Harbor executable,
      package path, pinned revision, selected environment provider, and built-in
      agent name (`codex` or `claude-code`) without reporting environment values
      or credentials.

**Harbor CLI exit criterion:** the pinned CLI imports from `.venv-linux`, all
matrix configs load, runtime inspection resolves both built-in agents, and no
credentialed API call has been made.

### B. Provision and validate the Docker execution provider

- [ ] Install Docker Engine, or enable Docker Desktop's WSL integration for
      this distribution. Ensure the user running SEAGym can reach the daemon
      without embedding `sudo` in experiment commands or granting the task
      containers access to the host Docker socket.
- [ ] Validate the client, daemon, image pull, container start, and cleanup
      path before invoking Harbor:

      ```bash
      docker version
      docker info
      docker run --rm hello-world
      ```

- [ ] Build one checked-in task image locally and retain the build log as a
      run artifact. Confirm that the image contains only task inputs and does
      not copy `.env`, Git credentials, provider profiles, or host paths into
      the build context.
- [ ] Run the task's checked-in oracle solution through Harbor and Docker with
      no model credentials:

      ```bash
      .venv-linux/bin/harbor run \
        -p data/holoskill-codeopt-v1/observer/codeopt-train-001 \
        -e docker \
        -a oracle \
        --n-concurrent 1 \
        -y
      ```

- [ ] Repeat the oracle run for every observer and private-gate task. Require a
      valid verifier reward, canonical ATIF, collected artifacts, and clean
      container teardown for each package. A build, launch, timeout, collection,
      or verifier infrastructure failure must not be recorded as reward zero.
- [ ] Confirm that task network policy, CPU/memory/storage limits, agent and
      verifier timeouts, process-group termination, and separate-verifier mode
      resolve as declared. Inspect `docker ps` after forced timeout tests and
      require that no task or sidecar container remains running.
- [ ] Add a Docker-capable CI or dedicated runner job for the oracle pass. Keep
      the ordinary unit-test job credential-free and able to run without a
      daemon.

**Docker exit criterion:** every checked-in Harbor task passes with the oracle
agent at concurrency one, failure-path containers are removed, and no provider
credential was present in a container or artifact.

### C. Establish one provider-credential loading contract

- [ ] Store local secrets in the ignored root `.env` only for development, or
      inject them from the production runner's secret manager. Never commit
      `.env`, print its contents, pass keys as command-line arguments, enable
      shell tracing around secret setup, or copy a credential file into a task
      image.
- [ ] Fix credential loading before the first production run. The current Holo
      baseline resolves its default `.env` relative to the config directory,
      and the static baseline does not load dotenv at all. Add one common,
      tested load step before baseline and rollout-agent construction, or set an
      explicit absolute/portable `env_file` contract that also covers static and
      checkpoint-eval runs. Do not rely on the caller's current directory or an
      already-exported interactive shell.
- [ ] Validate only the credentials required by the selected condition and
      fail before Harbor starts if one is absent or still a placeholder:

      | Condition | Required secret inputs |
      |---|---|
      | Codex gated or Codex gate-off | `HAI_API_KEY`, `OPENAI_API_KEY` |
      | Claude Code gated | `HAI_API_KEY`, `ANTHROPIC_API_KEY` |
      | Codex static control | `OPENAI_API_KEY` only |
      | Claude Code static control | `ANTHROPIC_API_KEY` only |
      | Codex-to-Claude transfer eval | `ANTHROPIC_API_KEY` plus the frozen source checkpoint |
      | Claude-to-Codex transfer eval | `OPENAI_API_KEY` plus the frozen source checkpoint |

      `OPENAI_PROJECT_ID` and `OPENAI_ORG_ID` remain optional routing metadata.
      `HOLO_BASE_URL`, `OPENAI_BASE_URL`, and model IDs are configuration, not
      secrets, but their resolved values must be recorded for reproducibility.

- [ ] Prove optimizer isolation: `HAI_API_KEY` must be visible only to the Holo
      proposal process and must never appear in `HarborAgentSpec.agent_env`, a
      Docker build argument, task environment, ATIF, captured subprocess output,
      checkpoint, or report.
- [ ] Prove target isolation: export only `OPENAI_API_KEY` to Codex tasks or only
      `ANTHROPIC_API_KEY` to Claude Code tasks. The private verifier receives no
      provider credential unless its own declared environment explicitly needs
      one.
- [ ] Add safe credential-presence diagnostics that print role, source, and
      status (`present`, `missing`, or `placeholder`) but never length, prefix,
      suffix, hash, or value. Add regression tests for exception, dataclass
      `repr`, subprocess environment, logs, ATIF, checkpoints, and reports.

**Credential exit criterion:** each condition fails closed before container
startup when its required key is missing, irrelevant role keys are not
forwarded, and artifact secret scans remain clean.

### D. Add automated runtime and provider preflights

- [ ] Extend `holoskill_gym.preflight` with non-spending `--harbor` and
      `--docker` checks. Add `--target codex` and `--target claude-code` modes
      that validate configuration and credential presence without calling a
      provider; require a separate explicit flag for a billable network canary.
- [ ] Keep `python -m holoskill_gym.preflight --optimizer --structured` as the
      one-request Holo authentication check. Run it only after local Harbor and
      oracle-Docker checks pass; its structured output must contain safe request
      metadata but no key or provider response content.
- [ ] Add a one-task static canary config per target executor. Run Codex and
      Claude Code independently so authentication, sandbox launch, ATIF
      validation, verifier execution, and target-only cost accounting can be
      diagnosed without involving SkillOpt or Holo.
- [ ] Mock command discovery, Docker responses, missing-daemon errors, missing
      keys, placeholder keys, provider 401/403, rate limits, and timeouts in
      unit tests. Keep default test and inspection paths network-free.
- [ ] Make the combined production preflight emit a machine-readable manifest
      containing boolean readiness by dependency and safe version/revision
      metadata. It must exit nonzero if any dependency required by the selected
      config is unavailable.

**Preflight exit criterion:** one command can prove configuration, Harbor,
Docker, task-package, and credential readiness before a paid rollout, while
network canaries remain explicit and opt-in.

### D2. Add two Daytona run examples alongside the Docker path

Daytona is the cloud execution provider Harbor supports for running many
environments in parallel. It is the alternative to local Docker, not a
replacement for it: validate a task under `-e docker` with `-a oracle` first,
because a task that fails locally will fail remotely too, only slower and at
cost.

**Credentials.** Harbor accepts either form
(`environments/daytona/environment.py:118-127`):

| Variable | Required |
|---|---|
| `DAYTONA_API_KEY` | yes, *or* both of the two below |
| `DAYTONA_JWT_TOKEN` + `DAYTONA_ORGANIZATION_ID` | alternative to the API key |
| `DAYTONA_TARGET` | optional; selects the region/target |
| `DAYTONA_GPU_TYPE_MAP` | optional; only for GPU tasks, which none of ours are |

An API key alone is enough. The slot is in `.env.example` with no value; keep
the value in `.env` and export it for the run, the same handling as
`HAI_API_KEY`.

The Daytona SDK is installed and pinned. Harbor raises
`MissingExtraError(package="daytona", extra="daytona")` without it, and the
editable source pin in `[tool.uv.sources]` cannot carry an extra, so `daytona`
is a direct dependency in `pyproject.toml`. Installed version 0.207.0;
`harbor.environments.daytona.environment.DaytonaEnvironment` imports cleanly.

- [ ] **Example 1 — single-task parity check.** Same task and agent as the
      Docker canary, so the only variable is the provider. A divergence here is
      a provider problem, not a task problem.

      ```bash
      export DAYTONA_API_KEY=...
      .venv-linux/bin/harbor run         -p data/holoskill-codeopt-v1/observer/codeopt-train-001         -e daytona         -a oracle         --n-concurrent 1         -y
      ```

      Assert the same reward, `correctness_pass`, `edit_policy_pass` and a
      comparable speedup as the local run. Record both `jobs/` paths in the run
      manifest so the comparison is reproducible.

- [ ] **Example 2 — parallel observer sweep.** What Daytona is actually for:
      the whole observer split at once, which local Docker cannot do at
      sensible speed.

      ```bash
      export DAYTONA_API_KEY=...
      export OPENAI_API_KEY=...
      .venv-linux/bin/harbor run         -d holoskill-codeopt-v1         -e daytona         -a codex         -m gpt-5.6-sol         --n-concurrent 4         -y
      ```

      Raise `--n-concurrent` only after example 1 passes. Note the ceiling is
      the *provider* quota and the model provider's rate limit, not
      `backend.n_concurrent`, which governs SEAGym runs rather than direct
      `harbor run` invocations.

**Harbor's Daytona adapter drops `allowed_hosts`. Decide the policy before
the first Daytona run.**

Daytona is a fully supported Harbor environment. The gap is in the adapter, not
the platform: Daytona's SDK exposes
`CreateSandboxFromImageParams(network_block_all, network_allow_list)`, but
Harbor only ever passes `network_block_all`. `grep -rn "network_allow_list"
src/harbor/` returns nothing, and nothing under `environments/daytona/` or the
shared `dind_compose.py` references egress or `allowed_hosts`. The egress
sidecar is wired only at `environments/docker/docker.py:359`.

| `network_mode` | `-e docker` | `-e daytona` |
|---|---|---|
| `no-network` | blocked | blocked |
| `allowlist` | enforced by the sidecar | **degrades to public network** |

Our tasks use `allowlist` for `[environment]` and `[agent]`, so a Daytona run
has unrestricted egress with no warning. Treat Daytona results as obtained
under a weaker network policy than the local run.

- [ ] Choose one before the first Daytona run: accept public egress and record
      it in the run manifest, or set those phases to `no-network` for Daytona
      conditions and pre-bake dependencies into the snapshot.
- [ ] Consider an upstream fix mapping `allowed_hosts` onto
      `network_allow_list` in the Daytona adapter. It is a small, well-defined
      change of the same shape as SEAGym#2, and it would make the two providers
      behave alike rather than requiring per-provider task variants.

**Snapshot invalidation is content-addressed, so a rebuilt image cannot go
stale.** `snapshots.py:86-94` names auto snapshots
`harbor__{env_hash}__snapshot`, where `env_hash` is
`environment_dir_hash_truncated(environment_dir)`. Editing a task's
`environment/` changes the hash, which changes the snapshot name, so a modified
task resolves to a different snapshot rather than reusing the old one.
Snapshots found in `ERROR` state are deleted and recreated; an explicitly named
`snapshot_template_name` fails fast instead.

- [ ] Note in the run manifest which snapshot name each Daytona condition
      resolved to, so a result can be traced back to the exact image content.

**Daytona stays out of CI and the deterministic smoke.** It needs credentials
and spends money, so the credential-free path remains the default; these
examples are operator-invoked only.

### E. Stage the first paid run and then unlock the matrix

- [ ] Run one target-only static canary for Codex, then one for Claude Code.
      Validate agent identity, model identity, terminal status, verifier schema,
      ATIF, artifact paths, target spend, and absence of optimizer spend.
- [ ] Run one Holo optimizer preflight, then one gated update against a single
      training task and the complete private-gate set. Keep concurrency one and
      retain all safe diagnostics needed to distinguish provider, Docker,
      Harbor, agent, verifier, and gate failures.
- [ ] Require the gated canary to report target and optimizer tokens, wall time,
      tool calls, and cost in separate namespaces with no combined total.
      Confirm that every private-gate task returns a `GateTaskScore`, including
      failures, and that gate-off application is not reported as acceptance.
- [ ] Exercise checkpoint resume and frozen-checkpoint evaluation on the canary
      run before increasing task count. Resume must not repeat a committed
      update, and evaluation must not call reflection, Holo, or baseline update.
- [ ] Scan the complete run directory for secrets and absolute host paths,
      archive the preflight manifest and dependency revisions, then execute the
      static controls, gated conditions, gate-off ablation, and transfer pair in
      the order documented by `examples/holo_skillopt_matrix/matrix.json`.
- [ ] Increase concurrency only after serialized runs are stable. Document the
      chosen limit against provider rate limits and Harbor capacity, and rerun
      timeout/process-group cleanup tests at that concurrency before adopting
      it as a production default.

**Production exit criterion:** both executor canaries and the single-update
gated canary are reproducible, resume/eval invariants hold, cost roles remain
separate, and the archived readiness manifest identifies the exact Harbor,
Docker, task, model, and repository revisions used.

---

## Deferred executor-extension backlog

HoloSkill Gym freezes the executor during a run and evolves only the
natural-language skill document. Adding an executor therefore means adding a
**rollout agent**, never a second optimizer. SkillOpt + Holo remain the only
things that propose, accept, or reject a skill edit.

The checklist below predates the implemented Harbor built-in binding. Retain it
as historical and extension planning material until the roadmap-drift tasks
above reconcile each item with current behavior.

### Phase 0 — Prerequisites

- [x] Vendor SEAGym at `reference/seagym` (pinned `9e61e14`)
- [x] Vendor SkillOpt at `reference/skillopt` (pinned `v0.2.0`, `e4ea6a6`)
- [x] Confirm SkillOpt v0.2.0 ships an `openai_compatible` auth mode
      (`skillopt/model/azure_openai.py`) — no local backend fork needed
- [x] Initialise SEAGym's required nested submodules. ACE, AHE, Harbor, and
      TF-GRPO are present; the unavailable nested `ace-eval` checkout is not
      required by HoloSkill Gym.
- [x] Install SEAGym and its model support in the project environment; root
      tests and `seagym inspect` import the editable checkout successfully.
- [ ] Read `seagym/rollout_agents/ahe_nexau.py` end to end — it is the closest
      working precedent for every executor below

---

### Phase 1 — `CliCodeOptRolloutAgent` (MVP, spec §11)

Implemented in `holoskill_gym/rollout_agent.py` as one configurable agent with
an `executor` strategy field rather than one class per CLI. It selects Harbor's
built-in agents; code-optimization task enforcement and normalized evidence
remain in the priority roadmap above.

- [x] `executor: "codex_exec"` — select Harbor's built-in `codex` agent
- [x] `executor: "claude_code_exec"` — select Harbor's built-in `claude-code`
      agent
- [ ] Fresh isolated workspace per task; checkout the pinned commit only
- [ ] Baseline correctness + benchmark run *before* the agent edits anything
- [x] Inject the checkpointed skill through Harbor's task-local prompt template,
      never through a user-global Codex/Claude skill directory
- [ ] Non-interactive launch with explicit timeout and max steps; terminate the
      process group on timeout
- [ ] Block edits to tests, benchmarks, task metadata, `.git`, verifier code
- [ ] Network disabled inside the task workspace by default
- [ ] Return a valid `TrajectoryBatch` even for failed tasks; infrastructure
      failure must not score as an ordinary wrong answer

---

### Phase 2 — Claude Agent SDK executor

`claude-agent-sdk` (Python) / `@anthropic-ai/claude-agent-sdk` (TypeScript) is
Claude Code packaged as a library: `query(prompt, options)` drives the full
harness with built-in Read/Write/Edit/Bash/Glob/Grep/WebSearch/WebFetch, plus
MCP servers and subagents. It is **harness-only** — we still host and deploy it,
which is exactly the shape a SEAGym rollout agent needs.

Docs: <https://code.claude.com/docs/en/agent-sdk> (not covered by the bundled
`claude-api` skill, which targets the Messages API instead).

- [ ] Decide in-process SDK call vs. subprocess. In-process gives structured
      events without parsing stdout; subprocess keeps the isolation story
      identical to Phase 1. **Recommend subprocess first** so the sandbox and
      timeout logic are shared with the CLI executors.
- [ ] Map SDK tool events onto the normalized trajectory contract (§7):
      bounded tool/action summaries, not raw transcripts
- [ ] Install the skill via `options` rather than mutating global config
- [ ] Verify the SDK honours a working-directory confinement equivalent to the
      CLI `--cwd` sandbox before trusting it with task repos
- [ ] Confirm token/cost accounting is attributable to *target* spend, kept
      separate from optimizer spend (§13)

**Auth:** an `ANTHROPIC_API_KEY` is *not* strictly required. Credentials resolve
in order: `ANTHROPIC_API_KEY` → `ANTHROPIC_AUTH_TOKEN` → an `ant auth login`
OAuth profile → Workload Identity Federation → default profile on disk. Run
`ant auth status` to see what is active before assuming a key is needed.

---

### Phase 3 — OpenAI Agents SDK executor

`pip install openai-agents`.

- [ ] Decide whether this is in scope at all — see the open question below
- [ ] If in scope, wrap it the same way as Phase 2 (subprocess, shared sandbox)
- [ ] Keep it out of the deterministic smoke path; it must stay optional

**Auth: yes, an API key is required.** The SDK expects `OPENAI_API_KEY` to be
exported and calls the Responses API by default. It *can* be pointed at other
providers through LiteLLM, any-llm, or a custom OpenAI-compatible client — but
see the constraint below before assuming H can substitute.

---

### Phase 4 — Cross-harness transfer evaluation (spec §14)

- [ ] Evolve with Codex, evaluate the frozen skill on Codex **and** Claude Code
- [ ] Evolve with Claude Code, evaluate on Claude Code **and** Codex
- [ ] Extend the matrix to any Phase 2/3 executor that lands
- [ ] Never update the skill during cross-harness evaluation

---

### Open questions

1. **Can the OpenAI Agents SDK run on Holo instead of OpenAI?**
   This is outside the current optimizer policy. The supported
   `holo3-1-35b-a3b` model reports tool support, but compatibility with the
   Agents SDK's function-call and Responses API expectations would require a
   separate verification effort. A separate `OPENAI_API_KEY` remains the
   low-risk path if this optional phase proceeds.

2. **Does adding SDK executors dilute the MVP?**
   Spec §19 keeps partner extensions out of acceptance. Phases 2–3 should not
   block Phase 1, the deterministic smoke run, or the leakage tests.

3. **Where does our code live?**
   Spec §4 proposes `seagym/integrations/skillopt_holo/`, but no `integrations/`
   directory exists. SEAGym's actual convention is `seagym/baselines/<method>/`
   (see `ace/`, `ahe/`, `gepa/`, `tf_grpo/`) plus
   `seagym/rollout_agents/<method>.py`. Follow the house convention and document
   the deviation, as §22 requires.

---

### Executor auth summary

| Executor | Credential | Required? |
|---|---|---|
| Codex CLI through Harbor | OpenAI target auth supported by Harbor | yes for real runs |
| Claude Code through Harbor | Anthropic target auth/profile supported by Harbor | yes for real runs |
| Claude Agent SDK | API key **or** `ant auth login` profile | key optional |
| OpenAI Agents SDK | `OPENAI_API_KEY` | yes |
| Holo optimizer | `HAI_API_KEY` | yes |

Executor credentials pay for *target* rollouts; `HAI_API_KEY` pays for
*optimizer* proposals. Spec §13 requires these two be reported separately —
never summed into one cost figure.
