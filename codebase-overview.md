# Codebase overview

How the three vendored pieces connect, and the exact call path that reaches the
H Models API.

```text
holoskill-gym/
├── holoskill_gym/          schemas, Holo backend, SkillOpt facade, baseline
├── scripts/holo            terminal client for Holo models
├── reference/seagym        antropy-research/SEAGym @ 9e61e14
└── reference/skillopt      microsoft/SkillOpt @ v0.2.0 (e4ea6a6)
```

Responsibility split, which the code must preserve:

- **SkillOpt + Holo** are the method. Holo proposes bounded edits to the skill
  document; SkillOpt's private held-out gate accepts or rejects them.
- **SEAGym** is the evaluator. It checkpoints each state and measures it, and
  never accepts, rejects, promotes, or rolls back an update.

Executor bindings — how SEAGym drives Codex, Claude Code, or any other agent —
are documented separately in [agents.md](agents.md).

## Reaching Holo: a plain OpenAI client pointed at our base URL

SkillOpt v0.2.0 does not need a forked backend. `openai_compatible` is an
**auth mode**, not a separate backend, and it swaps Azure's client for a plain
`OpenAI` client. From `reference/skillopt/skillopt/model/azure_openai.py:295`:

```python
if auth_mode in {"openai_compatible", "compat", "openai"}:
    return OpenAI(
        base_url=cfg["endpoint"].rstrip("/"),
        api_key=cfg["api_key"] or "dummy",
        default_headers={"User-Agent": "SkillOpt"},
    )
```

That is exactly the shape H needs, so we pin the v0.2.0 tag rather than
tracking unreleased `main`.

### Wiring it

`configure_azure_openai()` accepts `optimizer_*` and `target_*` parameters that
each fall back to a shared value, so the optimizer role can point at H while the
target role stays on whatever runs the rollouts:

```python
import os
from skillopt.model.azure_openai import configure_azure_openai, set_optimizer_deployment

configure_azure_openai(
    optimizer_endpoint="https://api.hcompany.ai/v1",   # trailing slash is stripped
    optimizer_api_key=os.environ["HAI_API_KEY"],
    optimizer_auth_mode="openai_compatible",
)
set_optimizer_deployment(os.environ.get("HOLO_OPTIMIZER_MODEL", "holo3-1-35b-a3b"))
```

`api_version` auto-fills in compat mode, so none is supplied. "Deployment" is
Azure vocabulary for what is simply the model id here. The equivalent env vars
are `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, and
`AZURE_OPENAI_AUTH_MODE`.

`chat_optimizer(system, user, max_completion_tokens=...) -> (text, usage)` then
reaches Holo. H serves Holo through vLLM (visible as `system_fingerprint`:
`vllm-0.22.1+...`), whose OpenAI-compatible layer treats `max_completion_tokens`
as an alias of `max_tokens` — the same ceiling under two names. It is enforced,
not merely tolerated: both names stop generation at exactly the requested count
with `finish_reason: length`.

SkillOpt's upstream compatibility path can serve other OpenAI-compatible
providers. The local `HoloBackendConfig` deliberately narrows the
skill-mutation role to `holo3-1-35b-a3b`; it rejects other model IDs so a run
cannot silently change capability or output limits.

### The gap: no structured output in v0.2.0

Grepping `response_format`, `json_schema`, and `structured` across that module
returns nothing, and `chat_optimizer` returns plain text. Spec §8's "use
structured outputs" therefore cannot be met by calling `chat_optimizer` as-is.

H does support it. Verified live with `strict: true`:

```json
{"finish": "stop", "parses": true, "completion_tokens": 236,
 "content": "{\n  \"diagnosis\": [\n    \"Excessive memory allocation in tokenizer path.\"\n  ]\n}"}
```

So the plan is:

1. **Reuse SkillOpt's client, bypass its chat helper.** Call
   `get_optimizer_client()` for the configured `OpenAI` instance, then issue our
   own `chat.completions.create(..., response_format={"type": "json_schema", ...})`
   built from the `SkillUpdateProposal` schema. One client, one auth path, no
   fork — we skip only the helper that cannot express the parameter.
2. **Keep `chat_optimizer`** for any free-form call SkillOpt makes internally.
3. **Validate regardless.** Spec §8's post-parse rules — edit count, evidence
   IDs present in the batch, delete/replace matching exact text, token budget,
   no-op detection — are ours to enforce whether or not the schema held. Strict
   mode reduces malformed output; it does not make an edit legal.

### Raising the completion budget

The optimizer's skill-rewrite call is bounded by a config key, not a code
constant — `skillopt/config.py:39` maps `model.rewrite_max_completion_tokens`,
defaulting to 64000 (`engine/trainer.py:795`) and applied at
`engine/trainer.py:1318`:

```json
{ "model": { "rewrite_max_completion_tokens": 64000 } }
```

Verified: H accepts 64000 with HTTP 200, but `holo3-1-35b-a3b` caps generated
output at 4096. The local backend therefore clamps proposal requests to 4096
instead of relying on provider-side clamping. `gpt-5.6-sol` is a separate
target-rollout model and does not determine the Holo optimizer budget.

### Reasoning effort is per call, never global

`REASONING_EFFORT` is a single module-level global (`azure_openai.py:107`) read
by all four call paths, and `set_reasoning_effort()` is documented as applying
"for all LLM calls". With the optimizer on Holo and the target on OpenAI, one
global would be sent to both.

Holo 35B reasons, but its endpoint does not expose SkillOpt's
`reasoning_effort` parameter as a supported control. It does not reject the
unknown field — verified, HTTP 200 with `finish_reason: stop`, because vLLM
ignores it. That makes forwarding the parameter worse than an error: the value
looks set while doing nothing.

Since `_chat_impl` resolves `reasoning_effort or REASONING_EFFORT`, the per-call
argument wins. Leave the global unset and pass effort only where it applies:

```python
chat_target(system, user, reasoning_effort="medium")   # gpt-5.6-sol
chat_optimizer(system, user)                           # Holo: omit entirely
```

`medium` is `gpt-5.6-sol`'s own default; the supported set is
`none|low|medium|high|xhigh|max`. It is recorded as `OPENAI_REASONING_EFFORT`
in `.env`.

There is no separate reasoning-token budget. Reasoning tokens are drawn from the
same completion budget, so sizing `max_completion_tokens` is the only control.

### Two cautions

- **Budget for the reasoning preamble.** Holo 35B emits reasoning tokens that
  count against the completion budget; structured-output calls returned
  `content: null` at 600 tokens and succeeded at 3000. `max_completion_tokens`
  is genuinely enforced (verified: a value of 20 stops generation at exactly 20
  tokens with `finish_reason: length`), so too small a value truncates before
  any content appears. Although `chat_optimizer`'s 16384 default is accepted,
  the local structured backend clamps mutation requests to 4096 and the
  reflection stage explicitly requests 3000.
- **`_needs_responses_api(deployment)`** selects the Responses API for some
  model names. Confirm `holo3-*` does not match, or SkillOpt will call
  `client.responses.create()` against an endpoint that serves only chat
  completions.

## Optimizer model policy

| Model | Free tier | Tools | Max output |
|---|---|---|---|
| `holo3-1-35b-a3b` | yes, 10 req/min | yes | 4,096 |

**Holo is the supported production optimizer.** Two backends exist and
`optimizer_backend` selects between them.

The OpenRouter adapter is proven end to end on a paid model:
`openai/gpt-5.6-luna` returned a valid `SkillUpdateProposal` on the first
attempt (2026-08-29). No *free* model can: four either exhausted their retries
on upstream saturation or failed schema validation despite advertising
`structured_outputs`, and are rejected at configuration time. Luna is therefore
a real alternative optimizer, at $0.20/M prompt and $1.20/M completion.

The two alternatives, never both in one run:

| `optimizer_backend` | Model | Pinned by |
|---|---|---|
| `holo_openai_compatible` | `holo3-1-35b-a3b` | `HoloBackendConfig` rejects other IDs |
| `openrouter` | `OPENROUTER_MODEL`, default `z-ai/glm-5.2:free`; `thinkingmachines/inkling` also selectable | `OPENROUTER_*` and CLI arguments |

The engine binds to the `ProposalBackend` protocol in `schemas.py`, not to a
concrete provider, so the two are peers rather than a primary and a special
case. Whichever is configured, the mutation call uses strict `json_schema`
followed by the same local semantic validation, and tools are never sent.
Tool-assisted evidence gathering, if enabled later, is a separate read-only
phase rather than an alternative patch format.

`HOLO_OPTIMIZER_MODEL` must still be `holo3-1-35b-a3b` when the Holo backend is
selected; the 35B restriction is a property of that backend, not of the
integration as a whole.

Inkling is not yet reachable: OpenRouter answers `403 "only available on
agentic harnesses"` to a direct call for the free Inkling model, so a run
configured for it fails closed with `OpenRouterAccessError` rather than producing
a degraded proposal. See [docs/openrouter-inkling.md](docs/openrouter-inkling.md).

This restriction is scoped to deterministic SkillOpt mutation. `scripts/holo`
is a general-purpose terminal client, not an optimizer adapter, so it retains
its `122b`/`large`/`big` aliases and sends explicitly selected model IDs through
unchanged. Their availability and billing are provider/account concerns and do
not affect a SkillOpt run. Listing a model is not proof of access; only a real
completion is.

## Step budgets: `max_steps` is a harness control, not a model setting

`max_steps` bounds how many turns the *agent harness* takes before it is cut
off. It is not a property of the model, and no model exposes it — a step budget
only exists if the process driving the model counts turns and stops. That makes
it an execution control, enforced by Harbor, and it is available only where the
built-in Harbor agent implements it.

| Executor | Harbor's native control | `max_steps` accepted? |
|---|---|---|
| `claude_code_exec` | `max_turns` | yes, mapped onto `max_turns` |
| `codex_exec` | none at this Harbor pin | no, rejected at config load |

**Claude Code.** Harbor's Claude Code agent exposes `max_turns`, so this
repository takes `max_steps` as the executor-neutral spelling and maps it onto
that kwarg. Configs stay portable, and setting both to different values is a
configuration error rather than a silent last-writer-wins.

**Codex.** The Harbor Codex agent at the revision pinned through SEAGym exposes
no equivalent enforceable control. `_validate_execution_controls` in
`holoskill_gym/rollout_agent.py` therefore rejects `max_steps` outright for
`codex_exec` rather than accepting it and dropping it: a config that reads as
bounded but is not is worse than one that refuses to load. This is why the
`claude_*` matrix configs carry `"max_steps": 50` and the `codex_*` configs
carry none — the asymmetry is deliberate, not an oversight.

**What bounds a Codex run instead.** `agent_timeout_seconds`, which Harbor does
enforce. A wall-clock bound is not a step bound: it caps cost and prevents a
hung run, but it does not cap how many tool calls an agent makes inside that
window.

**Adding `max_steps` to a Codex config will not create a step budget.** It fails
closed at load time. A real budget requires extending Harbor's Codex agent to
count turns or tool calls and terminate on the limit — an upstream change to the
vendored Harbor tree, not a configuration change here. Until that lands, treat
Codex runs as wall-clock-bounded only, and record that distinction in the run
manifest when comparing Codex and Claude Code conditions: the two harnesses are
not being held to the same kind of limit.

## Why the benchmark is a median with a variance report

The verifier does not time a task once. `VerifierConfig` runs
`benchmark_warmups = 1` discarded warmup, then `benchmark_samples = 5` measured
samples, aggregates them with `statistics.median`, and reports
`coefficient_of_variation` — population standard deviation over the mean —
alongside the result.

**This is what decides which optimizations the gym can measure at all.** A 10x
algorithmic win clears container timing noise on any host. A 4% micro-
optimization does not: at typical CI variance the measurement error is the same
size as the effect, so accepting it would mean gating a skill update on noise.
The median resists the single slow sample that a noisy neighbour produces; the
CV is what tells you whether to believe the median in the first place.

The practical consequence is a constraint on task design, not just on
reporting: **tasks whose available win is smaller than the environment's timing
variance do not belong in the set.** The checked-in canaries all target
algorithmic-complexity wins on a single hot path for exactly this reason, and
that requirement carries over to any trusted external task set. A task whose
reference solution yields a few percent is not a hard task — it is an
unmeasurable one.

## Known limitations in the privacy layer

Documented rather than silently carried. None of these is currently exploitable
in CI, where no `.env` is present, but each is a real gap.

- **Resolved:** the redaction and scan paths once received different inputs —
  the sanitize wrapper never passed `known_secret_values` while the scanner did.
  Both wrappers now share `load_known_secret_values`, so redaction and detection
  see the same live values. In CI neither has an `.env` to read, so both fall
  back to pattern matching there regardless.
- **The 512-byte chunk overlap encodes a length assumption.** A credential
  spanning a chunk boundary is caught only if it is shorter than the overlap.
  That holds for API keys; it does not necessarily hold for JWTs, which can
  exceed it.
- **`errors="ignore"` can drop a split multi-byte sequence** at a chunk
  boundary. The overlap mitigates this but does not eliminate it, so a secret
  containing non-ASCII bytes straddling a boundary is not guaranteed to match.

## AlgoTune as a candidate trusted task source

The checked-in `holoskill-codeopt-v1` tasks are synthetic canaries. The blocker
they leave open — a *trusted* external task set — has a plausible answer already
reachable from the pinned Harbor: `algotune@1.0` in the registry, 154 algorithm
optimization tasks where the goal is to beat a reference implementation while
producing identical output ([arXiv:2507.15887](https://arxiv.org/abs/2507.15887)).

**Why it fits.** The objective is the same one this gym scores: correctness-gated
speedup on a pinned repository, measured continuously rather than pass/fail. It
brings 154 tasks across recurring technique families, which is what the current
five-task set structurally cannot provide — five tasks means five *distinct*
families, so nothing today tests within-family generalization. Its evaluation
protocol is also more careful than ours: 100 problem instances per task, 10
timing repetitions with the minimum taken, and baseline and solver timed
**interleaved** to cancel drift.

**Its metric is not ours.** AlgoTune reports the harmonic mean of speedups; this
project reports the geometric mean. `harmonic_mean_speedup` and the
`algotune_score` report metric exist so both can be computed from the same
evidence, and `python -m holoskill_gym.score` prints them side by side with
their ratio. Scores from an AlgoTune run are therefore *not* comparable to
existing `correct_speedup_geomean` numbers without recomputing.

### Four things that must be settled before it feeds a gate

1. **Network policy will reject every task as-is.** None of the 154 declares
   `[agent].network_mode` or `[verifier].network_mode`. Under the rules in
   `_validate_task_network_policy` an undeclared phase never matches a requested
   mode, so any matrix config setting `agent_network_mode` or
   `verifier_network_mode` refuses the run. This is the guard working as
   designed — the alternative is silently inheriting an effectively `public`
   baseline during grading. Resolving it means adding the declarations to a
   vendored copy of the tasks, not relaxing the check.
2. **Resource declarations differ by 4x.** AlgoTune asks for `cpus = 8`,
   `memory = "16G"` and 3600 s timeouts; the checked-in canaries declare 2 CPUs
   and 2048 MB. Its own documentation warns that timing is hardware-sensitive
   and comparable only on the same machine, which bears directly on the
   median-and-CV reasoning above. No GPU is required by any of the 154.
3. **Pretraining contamination is a different problem from split leakage.**
   AlgoTune is public and its reference solutions are published. `leakage.py`
   enforces disjointness between train, gate and observer splits; it cannot
   detect that a model memorised a solution before the run started. A private
   gate drawn from AlgoTune is therefore weaker than one drawn from unpublished
   tasks, and that limitation belongs in the run manifest.
4. **Trust labelling.** Every checked-in task carries
   `benchmark_trust = "synthetic_canary"`. AlgoTune would be the first non-
   synthetic source and needs its own value plus a recorded provenance pin — the
   registry supplies one: `harbor-datasets` at commit `479f07dd`.

### Sketch: wiring one AlgoTune task into a SEAGym config

The rollout agent binds to Harbor tasks through the task index, so an AlgoTune
task enters the same way a local one does — the work is in the task package, not
the config.

1. **Vendor the task and add the missing policy.** Copy one task out of the
   registry checkout and add what the network guard requires:

   ```toml
   # task.toml, appended
   [agent]
   network_mode = "allowlist"
   allowed_hosts = ["api.openai.com"]

   [verifier]
   network_mode = "no-network"
   ```

2. **Point the task index at it**, mirroring `holoskill-codeopt-v1`:

   ```json
   {"task_id": "algotune-base64-encoding",
    "source": {"type": "harbor",
               "dataset_path": "../../../data/holoskill-algotune-v1/observer",
               "task_name": "algotune-base64-encoding"}}
   ```

3. **Split it.** Keep gate tasks in families absent from train and test, and
   record the split hash the leakage guard computes.

4. **Raise the backend limits** to match the task declaration, or the container
   is under-resourced relative to what AlgoTune calibrated its problem sizes
   against:

   ```json
   "backend": {"name": "harbor", "env": "docker", "n_concurrent": 1,
               "agent_override_timeout_sec": 3600,
               "verifier_override_timeout_sec": 3600}
   ```

5. **Register both aggregates** so the run is readable next to existing ones:

   ```json
   {"name": "algotune_score", "type": "python",
    "import_path": "holoskill_gym.report_metrics:AlgoTuneScoreMetric"}
   ```

6. **Prove it with the oracle first.** `harbor run -p <task> -e docker -a oracle -y`
   before any credentialed agent touches it — the same free rung the CI matrix
   uses on the synthetic tasks.

The open question this sketch does not answer is whether AlgoTune's own verifier
or this project's strict verifier owns the reward. AlgoTune tasks ship their own
`tests/evaluator.py`, so running them unmodified means the reward comes from
their protocol rather than from `verify_code_optimization`, and the normalized
evidence this project depends on would have to be adapted from their output.
