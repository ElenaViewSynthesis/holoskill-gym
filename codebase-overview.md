# Codebase overview

How the three vendored pieces connect, and the exact call path that reaches the
H Models API.

```text
holoskill-gym/
├── holoskill_gym/          our code (preflight today, backend next)
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

The same path serves any OpenAI-compatible provider — point
`optimizer_endpoint` at `https://api.deepseek.com/v1` with `DEEPSEEK_API_KEY`
and nothing else changes.

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

Verified: H accepts 64000 with HTTP 200, so the default needs no change. The
binding constraint is the model, not this key — `holo3-1-35b-a3b` caps output at
4096, while `gpt-5.6-sol` allows 128000. For direct calls it is a plain
argument: `chat_optimizer(system, user, max_completion_tokens=32000)`.

### Reasoning effort is per call, never global

`REASONING_EFFORT` is a single module-level global (`azure_openai.py:107`) read
by all four call paths, and `set_reasoning_effort()` is documented as applying
"for all LLM calls". With the optimizer on Holo and the target on OpenAI, one
global would be sent to both.

Holo does not reject it — verified, HTTP 200 with `finish_reason: stop`, because
vLLM ignores unknown fields. That makes it worse than an error: the value looks
set while doing nothing.

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

- **Budget for the reasoning preamble.** Holo models emit reasoning tokens that
  count against the completion budget; structured-output calls returned
  `content: null` at 600 tokens and succeeded at 3000. `max_completion_tokens`
  is genuinely enforced (verified: a value of 20 stops generation at exactly 20
  tokens with `finish_reason: length`), so too small a value truncates before
  any content appears. `chat_optimizer`'s 16384 default is accepted with HTTP
  200 even though `holo3-1-35b-a3b` caps output at 4096 — the request is not
  rejected; behaviour when generation would actually exceed 4096 is untested.
- **`_needs_responses_api(deployment)`** selects the Responses API for some
  model names. Confirm `holo3-*` does not match, or SkillOpt will call
  `client.responses.create()` against an endpoint that serves only chat
  completions.

## Model access

| Model | Free tier | Tools | Max output |
|---|---|---|---|
| `holo3-1-35b-a3b` | yes, 10 req/min | yes | 4,096 |
| `holo3-122b-a10b` | no — HTTP 402 `insufficient_credit` | no | 32,768 |

`HOLO_OPTIMIZER_MODEL` defaults to the free-tier model for that reason. Listing
is not access: both appear in `/v1/models` as active and ready, but only a real
completion proves the key can use them.
