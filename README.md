# holoskill-gym

Building **HoloSkill Gym**, a SEAGym × SkillOpt × Holo system for
self-evolving CLI coding-agent skills.

SkillOpt and Holo form the self-evolution method: Holo proposes bounded edits
to a natural-language skill document, and SkillOpt's private held-out gate
accepts or rejects them. SEAGym is the independent evaluator — it checkpoints
each state and measures it, and never accepts, rejects, or rolls back an
update.

## Documentation

| File | What it covers |
|---|---|
| [codebase-overview.md](codebase-overview.md) | How the vendored pieces connect, and the plain OpenAI client pointed at the H base URL |
| [agents.md](agents.md) | Executor bindings: how SEAGym drives an agent it does not own, and how `HarborRolloutAgent` is subclassed |
| [todo.md](todo.md) | Implementation roadmap for the production data plane, plus the deferred executor backlog |
| [docs/skillopt_holo.md](docs/skillopt_holo.md) | Production architecture, evidence, verifier, metrics, experiment matrix, eval/resume, privacy, and limitations |
| [docs/docker-harbor-runtime.md](docs/docker-harbor-runtime.md) | Docker socket access, WSL integration, network phases, and running a task package end to end |
| [docs/harbor.md](docs/harbor.md) | What Harbor is, installing it, and running a dataset or a single task package from the CLI |
| [docs/verifiers-v1-harbor.md](docs/verifiers-v1-harbor.md) | Verifiers v1 to Harbor: taskset, reward, artifact and separate-grader contracts, and current parity gaps |
| [docs/harbor-task-structure.md](docs/harbor-task-structure.md) | Harbor task authoring: single-step layout, agentic runtime policy, verifier placement and reward output |
| [docs/harbor-multi-step-tasks.md](docs/harbor-multi-step-tasks.md) | Harbor's sequential multi-step task contract, documented as a future extension |

## Vendored dependencies

| Path | Upstream | Pinned at |
|---|---|---|
| `reference/seagym` | [antropy-research/SEAGym](https://github.com/antropy-research/SEAGym) | `9e61e14` (main) |
| `reference/skillopt` | [microsoft/SkillOpt](https://github.com/microsoft/SkillOpt) | `v0.2.0` (`e4ea6a6`) |

```bash
git submodule update --init --recursive
bash scripts/apply-vendor-patches
```

The nested `reference/ace/kayba-ai/ace-eval` submodule is private or removed
upstream. Its initialization failure is expected and does not affect this
SkillOpt/Holo integration.

### Vendor patches

A submodule records a commit SHA, not file contents, so an edit inside
`reference/` cannot be committed here and would be lost on a fresh clone.
Patches live in `patches/` and are re-applied after every `git submodule
update`. `scripts/apply-vendor-patches` is idempotent, and `--check` reports
what is missing without writing anything.

| Patch | Target | Why | Upstream |
|---|---|---|---|
| `seagym-redaction-usage-keys.patch` | `reference/seagym` | `redact_sensitive()` matches `TOKEN` as a substring, so token *counts* such as `total_tokens` were written to run records as `<redacted>` | [SEAGym#2](https://github.com/antropy-research/SEAGym/pull/2) |
| `seagym-final-resume-idempotence.patch` | `reference/seagym` | Resuming an already-complete final checkpoint appended duplicate final evaluation rows and changed metrics | local pending upstream proposal |

Retire a patch by moving the submodule pin to a commit that already contains
the fix, then deleting the file.

## Python environment

Use a project venv. It keeps the editable reference checkouts and their pinned
dependencies isolated from the system interpreter. This repository already has
a Windows-style `.venv`, so WSL/Linux development uses `.venv-linux` without
overwriting it:

```bash
uv venv --python 3.12 .venv-linux
source .venv-linux/bin/activate
UV_CACHE_DIR=/tmp/cua-holo-uv-cache uv pip install \
  -e '.[dev]' \
  -e 'reference/skillopt[dev]' \
  -e 'reference/seagym[models]' \
  -e reference/seagym/reference/harbor
```

That installs `python-dotenv`, pytest, Ruff, SkillOpt, SEAGym, and Harbor into
one active interpreter. The three reference packages remain editable. A normal
`uv sync --extra dev` also understands these local sources through
`[tool.uv.sources]`.

Run the offline end-to-end smoke:

```bash
.venv-linux/bin/seagym inspect config examples/holo_skillopt_deterministic/config.json
.venv-linux/bin/seagym train examples/holo_skillopt_deterministic/config.json
```

The smoke never uses credentials or external agents. Production target
rollouts map `codex_exec` to Harbor's built-in Codex agent (configured with
`gpt-5.6-sol`) and `claude_code_exec` to Harbor's built-in Claude Code agent.
Holo remains the optimizer role; target and optimizer usage are recorded
separately.

The production condition configs and neutral initial skill are committed under
[`examples/holo_skillopt_matrix/`](examples/holo_skillopt_matrix/README.md).
They cover gated and static Codex/Claude runs, gate-off, and both transfer
directions with first-run concurrency fixed at one. Trusted Harbor task packages
and credentials are explicit external prerequisites and have not been
simulated or executed here.

## Commands

Every command below is run from the repository root. Substitute your own config
path for the deterministic example.

### Inspect before you run

`seagym inspect` has four subcommands and none of them execute a rollout, so
all four are safe without credentials.

```bash
seagym inspect config <config.json>    # load and validate a config
seagym inspect runtime <config.json>   # check runtime deps a config needs
seagym inspect run <run-dir>           # summarize a finished run
seagym inspect env                     # print runtime paths
```

Run `inspect config` then `inspect runtime` before any credentialed run. They
catch an unresolvable class path or a missing executor dependency before
Harbor capacity or Holo tokens are spent.

### Train

```bash
seagym train <config.json>
seagym train <config.json> --run-name my-run --output-dir results/runs
seagym train <config.json> --resume
seagym train <config.json> --resume-from-checkpoint epoch_0001
```

`--resume` picks up the latest checkpoint in the run directory;
`--resume-from-checkpoint` names one explicitly. Committed SkillOpt updates are
not repeated on resume — `StateStore` rejects a duplicate update index.

Completed-final resume is integration-tested: no update or metric-input row is
repeated, and state, deployed skill, metrics, and the summary report stay
byte-identical. Intermediate-checkpoint recovery remains a roadmap item.

### Evaluate a frozen checkpoint

```bash
# a named checkpoint from an earlier run, written to a fresh output directory
seagym eval --checkpoint <run-dir>/checkpoints/final <config.json>

# re-evaluate the newest checkpoint in place, reusing the same run directory
seagym eval --checkpoint latest --run-dir <run-dir> <config.json>
```

`--checkpoint` takes `latest`, a filesystem path, or a bare name. A **bare
name is resolved inside the run directory this eval creates**, not the run you
took the checkpoint from, so it only works alongside `--run-dir`. Pass the path
form when evaluating an earlier run — `--checkpoint final --run-dir <run-dir>`
fails with `FileExistsError` because anything other than `latest` resets the
run directory first.

`eval` measures a saved skill on the config's final views and **never calls
the updater** — no SkillOpt reflection, no Holo proposal, no gate. That is what
makes it the right tool for:

- **Cross-harness transfer** — evolve with Codex, then evaluate the frozen
  skill under `claude_code_exec` by pointing `eval` at a config whose rollout
  agent differs. The skill must not change during transfer evaluation.
- **`A_0` versus final** — `<run-dir>/checkpoints/initial` against
  `<run-dir>/checkpoints/final` on the same held-out view is the headline
  comparison.
- **Re-scoring** an old checkpoint against a view added later, without
  retraining.

A training run writes `initial`, `final`, per-epoch (`epoch_0001`) and
per-evaluation (`E_1`, `E_2`) checkpoints; list them with
`ls <run-dir>/checkpoints/`.

Verified on the deterministic example: an eval run writes only `checkpoint_eval`
mode records, no `agent_updates.jsonl`, and zero `agent_update` rows.

Do not use `eval` for routine validation during training — the trainer already
runs update-validation, replay and final views itself.

An integration test replaces baseline update, SkillOpt reflection, and Holo
proposal generation with fail-fast sentinels, then runs checkpoint eval. The
eval completes with only `checkpoint_eval` records and no update artifact.

### Harbor tasks

Harbor owns checkout, isolation, CLI execution and timeouts. These commands
operate on a task package directly, outside SEAGym, and are how you develop or
debug a task before wiring it into a config.

```bash
harbor init --task "<org>/<name>"                 # scaffold a task package
harbor run -p <path/to/task> -a <agent> -m <model>  # run one task
```

Pre-populate defaults for a new task from a shared TOML template so a family of
tasks does not drift apart:

```bash
harbor tasks init "<task-name>" --metadata-template task-template.toml
```

Harbor also publishes a task-authoring skill for coding agents:

```bash
npx skills add harbor-framework/harbor --skill create-task
```

Layout, `task.toml` fields, network policy and reward output are documented in
[docs/harbor-task-structure.md](docs/harbor-task-structure.md).

### Docker runtime for Harbor tasks

Harbor talks to the Docker Engine API over a socket and builds each task's own
image, so the process running it needs socket access and build permission.
Verify before a first run:

```bash
wsl -e bash -lc "docker version --format '{{.Server.Version}}'"   # daemon reachable in WSL
wsl -e bash -lc "ls -l /var/run/docker.sock"                      # srw-rw---- root docker
wsl -e bash -lc "id -nG | tr ' ' '
' | grep -x docker"           # you are in the group
```

If the daemon answers on Windows but not in WSL, enable this distro under
Docker Desktop → **Settings → Resources → WSL integration**, then **Apply &
restart**. If the socket is there but denied, add yourself to the group and
restart the distro — never reach for `sudo harbor`, which leaves job artifacts
your user cannot read:

```bash
sudo usermod -aG docker "$USER" && wsl --shutdown
```

Network policy is per phase. Task builds need egress for `apt-get` and `pip`,
the agent phase needs its model provider, and verification runs with
`no-network` so grading cannot depend on anything remote. Any `allowlist` phase
makes Harbor build an egress-control sidecar on first use, which is why an
initial run appears to pause shortly after starting.

Build and run the first repaired task through Docker Desktop using the oracle
agent, which applies the reference solution and needs no model credentials:

```bash
.venv-linux/bin/harbor run   -p data/holoskill-codeopt-v1/observer/codeopt-train-001   -e docker   -a oracle   --n-concurrent 1   -y
```

Start with `oracle`: it proves the image builds, tests run, the benchmark
measures and the verifier writes a reward, without spending a token. Swap in
`-a codex -m gpt-5.6-sol` with `OPENAI_API_KEY` set once it passes. Results land
in `jobs/<timestamp>/<task>__<id>/`; read `trial.log` first when a run fails.

Full setup, network-phase configuration and troubleshooting:
[docs/docker-harbor-runtime.md](docs/docker-harbor-runtime.md).

### Multi-step Harbor tasks

A multi-step task runs an ordered sequence of steps in one persistent
environment, declared as `[[steps]]` entries in `task.toml`.

```bash
harbor run -t <path/to/multi-step-task> -a claude-code -m <model>
harbor run -t <path/to/multi-step-task> -a claude-code -m <model> --resume-trajectory
```

By default every step starts a fresh agent conversation even though the
environment persists. `--resume-trajectory` continues the agent's native
session so each step arrives as a follow-up. It is a run setting, not a task
field, and an agent lacking the `capabilities.resume` capability fails before
step 1 rather than silently getting fresh sessions.

Multi-step is **not yet supported** by the Verifiers v1 Harbor adapter, so it
is not reachable from a SEAGym config today. See
[docs/harbor-multi-step-tasks.md](docs/harbor-multi-step-tasks.md).

### Maintenance

```bash
bash scripts/apply-vendor-patches          # re-apply vendor patches
bash scripts/apply-vendor-patches --check  # report without writing; exits 1 if missing
python -m pytest -q                        # project test suite
python -m ruff check holoskill_gym tests
python -m ruff format --check holoskill_gym tests
python -m holoskill_gym.preflight --optimizer --structured   # needs HAI_API_KEY
```

`preflight` is the only command here that spends credentials. It sends one
structured request to confirm the key, base URL and model resolve.


The production role split is configured like this (task and split paths
omitted here):

```json
{
  "baseline": {
    "config": {
      "optimizer_backend": "holo_openai_compatible",
      "optimizer_model": "holo3-1-35b-a3b",
      "gate_mode": "on"
    }
  },
  "rollout_agent": {
    "class_path": "holoskill_gym.rollout_agent:CliCodeOptRolloutAgent",
    "config": {"executor": "codex_exec", "model_ref": "rollout_model"},
    "models": {
      "rollout_model": {
        "model": "gpt-5.6-sol",
        "api_base": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "exports": {
          "OPENAI_API_KEY": "{api_key}",
          "OPENAI_BASE_URL": "{api_base}"
        }
      }
    }
  }
}
```

`holo3-1-35b-a3b` is the only **Holo** model used by this integration, and
`HoloBackendConfig` rejects other Holo IDs. It is not the only optimizer:
`optimizer_backend` selects between `holo_openai_compatible` and
`inkling_openrouter`, which are alternatives filling the same role behind the
`ProposalBackend` protocol. Inkling's parameters and defaults are documented in
[docs/openrouter-inkling.md](docs/openrouter-inkling.md); it is not reachable
yet, and fails closed rather than degrading. Holo supports
both reasoning and tool calls. For the skill-mutation request specifically,
the optimizer uses strict `SkillUpdateProposal` JSON output followed by local
semantic validation. This keeps mutation deterministic and auditable; it is
not a workaround for another Holo model. Tool calling remains available to
separate 35B workflows that need tools. Codex/GPT-5.6-sol continues to own the
target coding-agent rollouts through Harbor.

### Strict proposal-schema policy options

The current schema is intentionally small: diagnosis, bounded
add/delete/replace edits, expected effects, and risks. There are several safe
ways to make it stricter without weakening local validation:

1. **Dynamic enums (recommended next step).** Generate the request schema per
   training batch so `evidence_ids` can only contain IDs in that batch and
   `section` can only name headings in the current skill. Keep the same checks
   after parsing because schema compliance does not prove an edit is legal.
2. **Discriminated edit variants.** Replace nullable `old_text`/`new_text`
   combinations with separate `AddEdit`, `DeleteEdit`, and `ReplaceEdit`
   objects selected by the `operation` discriminator. This makes invalid field
   combinations unrepresentable in model output.
3. **Explicit no-op envelope.** Add a top-level `decision` of `edit` or `noop`.
   Require an empty edit list and a concise explanation for `noop`; require at
   least one edit for `edit`. This separates intentional abstention from a
   malformed empty proposal.
4. **Schema-level size bounds.** Add `maxItems`, string-length limits, and
   bounded rationale/effect/risk counts. Local token, character, edit-count,
   exact-match, leakage, and forbidden-content checks still remain mandatory.
5. **Two-phase tool-assisted proposal.** Allow 35B tools only in a separate,
   read-only evidence-gathering call, normalize its outputs into bounded
   evidence, then make a second call with tools disabled and strict
   `json_schema`. Never combine side-effecting tools with the mutation response.
6. **Versioned proposal envelope.** Add a schema version and policy-profile ID
   so historical proposals remain replayable when constraints evolve. Reject
   unknown versions and profiles rather than guessing compatibility.

The recommended progression is dynamic enums plus discriminated edit variants,
then an explicit no-op envelope. Native tool calls should remain a separate
evidence phase rather than becoming an alternative patch format.

## ATIF trajectory contract

Target-agent rollouts use Harbor's **Agent Trajectory Interchange Format
(ATIF)** as their canonical trajectory representation. Do not introduce a
second provider-specific conversation schema. Harbor currently emits
`ATIF-v1.7` and accepts the `ATIF-v1.0` through `ATIF-v1.7` family.

An ATIF document records the agent identity and model, sequential interaction
steps, tool calls and their matching observations, per-step metrics, aggregate
final metrics, and independently valid subagent trajectories. Harbor validates
that step IDs start at 1 and remain sequential, subagent trajectory IDs are
non-null and unique, and every observation's `source_call_id` refers to a tool
call in the same step.

The code-optimization fields required by this project map onto ATIF as follows:

| HoloSkill Gym datum | ATIF location |
|---|---|
| Executor name, version, and target model | `agent` |
| Bounded action and tool summaries | `steps[].tool_calls` |
| Tool results | `steps[].observation.results` |
| Per-step target reasoning effort | `steps[].reasoning_effort` |
| Target prompt, completion, and cached tokens | `steps[].metrics` |
| Target rollout cost and total steps | `final_metrics` |
| Task/view, checkpoint, update, skill hashes, repository commit, patch/verifier/benchmark summaries, terminal status, and artifact paths | namespaced `extra.holoskill_gym` dictionaries |

Three serialization constraints are non-negotiable:

- ATIF's `extra` dictionaries are the only extension point for
  SEAGym/HoloSkill Gym data because the root schema forbids unknown fields.
- `reasoning_content` stays null; hidden Holo reasoning is never requested or
  persisted.
- Target and optimizer cost/usage remain separate; ATIF final metrics describe
  the target rollout, while optimizer accounting is namespaced method state.

Store bounded summaries and local artifact paths in `extra`, not complete
provider logs or transcripts.

`reasoning_effort` is target-step metadata. It records the effort actually used
by Codex or Claude Code and is independent from optimizer configuration.
`reasoning_content` remains null in HoloSkill Gym records: Holo's hidden
reasoning trace must never be requested, copied into ATIF, or persisted. Only
the structured proposal, concise rationale, usage, latency, and safe error
metadata are retained for optimizer calls.

ATIF's `final_metrics.total_cost_usd` represents the **target-agent rollout**
only. Optimizer usage belongs to the separate SkillOpt/Holo baseline call and
must not be folded into that value. Reports and checkpoint metadata use this
namespaced extension shape:

```json
{
  "extra": {
    "holoskill_gym": {
      "target": {
        "cost_usd": 0.0,
        "prompt_tokens": 0,
        "completion_tokens": 0
      },
      "optimizer": {
        "cost_usd": 0.0,
        "prompt_tokens": 0,
        "completion_tokens": 0
      }
    }
  }
}
```

The rollout binding remains intentionally thin: `codex_exec` selects Harbor's
built-in Codex agent, `claude_code_exec` selects its built-in Claude Code
agent, and the checkpointed skill enters through Harbor's existing
`prompt_template_path` hook. Harbor owns checkout, isolation, command
execution, and ATIF production. Holo optimizer credentials are rejected if a
configuration attempts to export them into the target-agent environment.

## Computer-use agent models

The H Models API serves the 35B vision-language model used here for reasoning
and tool-capable workflows. The values below are read from `GET /v1/models`,
not copied from documentation, so they reflect what this account is actually
served.

| Model | Context | Max output | Features | Input / M | Output / M | Free tier |
|---|---|---|---|---|---|---|
| `holo3-1-35b-a3b` | 65,537 | 4,096 | reasoning, tools | $0.25 | $1.80 | yes, 10 req/min |

The model takes text and image input and returns text. There is no per-request
fee; cost is token-based only.

Two consequences are worth knowing before configuring a run:

- `HOLO_OPTIMIZER_MODEL` must remain `holo3-1-35b-a3b` whenever the Holo
  backend is selected; configuration rejects other Holo model IDs rather than
  silently changing model behavior. Selecting a different *optimizer* is done
  with `optimizer_backend`, not by changing this variable.
- The model emits a reasoning preamble that counts against `max_tokens`.
  Budget at least ~256 completion tokens or the answer is cut off before it
  starts.

Listing is not access. Only a real completion proves that a configured key can
use the model.

## Computer-Use Agents plans

Token allowances apply to Computer-Use Agents, which is a separate product from
the Models API. The Models API free tier is limited by request rate, not by a
token pool.

| Plan | Tokens / billing period | Concurrent sessions |
|---|---|---|
| Free | 15,000,000 | 3 |
| Developer ($29/mo) | 65,000,000 | 10 |

Neither plan imposes a request-rate limit. Exhausting the token allowance makes
session creation fail with `402 Payment Required`. Allowances are subject to
change, so read live values from the API rather than trusting this table.

## Terminal client

`scripts/holo` is intentionally broader than the SkillOpt mutation adapter. It
remains a general-purpose H Models client and retains its 122B aliases; choosing
one there does not change or bypass the 35B-only optimizer policy.

```bash
bash scripts/holo "explain prefix caching"          # default 35b
bash scripts/holo -m opt -v "..."                   # HOLO_OPTIMIZER_MODEL
bash scripts/holo -i                                # multi-turn chat
bash scripts/holo --list                            # resolve model aliases
```

Verify credentials with a single request:

```bash
python -m holoskill_gym.preflight --optimizer --structured
```

This exercises the same strict `json_schema` path used for proposals. Copy
`.env.example` to `.env` and set `HAI_API_KEY` first. The preflight reports only
safe request metadata and never displays the credential or response content.
