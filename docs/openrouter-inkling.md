# OpenRouter: `thinkingmachines/inkling-small:free`

Parameter and endpoint reference for reaching Inkling Small through OpenRouter's
OpenAI-compatible API, plus the access constraint that governs whether a request
succeeds at all.

Related references:

- [Implementation roadmap](../todo.md)
- [Codebase overview](../codebase-overview.md)

## Access constraint: verify before building on it

`thinkingmachines/inkling-small:free` is **not reachable from a plain script**.
A direct SDK call returns:

```text
403 - thinkingmachines/inkling-small:free is only available on agentic
harnesses. Try plugging it into a coding agent or productivity app listed on
https://openrouter.ai/apps
```

Verified on 2026-08-27 against a valid free-tier key:

| Attempt | Result |
|---|---|
| Plain `OpenAI` client, `reasoning.enabled` | `403` |
| Same plus `HTTP-Referer` and `X-Title` | `403` |
| `GET /api/v1/key` | `200`, key valid, `is_free_tier: true` |

Attribution headers do **not** lift the gate, and the key itself is fine — the
restriction is per-model, enforced by OpenRouter on the caller being a
registered app from its apps directory. Treat the sections below as the
contract to code against once access exists, not as a path that works today
from this repository.

## Credentials

Configured in `.env`; see `.env.example` for the documented slots.

```dotenv
OPENROUTER_API_KEY=
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
INKLING_MODEL=thinkingmachines/inkling-small:free
# OPENROUTER_HTTP_REFERER=   # optional, used for OpenRouter's rankings
# OPENROUTER_X_TITLE=        # optional, used for OpenRouter's rankings
```

Never inline a key in source.

`.env` carries credentials, endpoint and model identity only. **Sampling and
reasoning parameters are command-line arguments**, because they change what a
run produces and therefore belong in that run's recorded configuration rather
than in ambient process state. A stray `INKLING_TEMPERATURE` in the environment
is ignored, and a test asserts that.

```bash
python -m holoskill_gym.preflight --inkling   --inkling-temperature 0.0 --inkling-seed 42 --inkling-reasoning-effort medium
```

`add_sampling_arguments(parser)` registers the whole group on any argparse
parser, and `sampling_from_args(args)` turns the result into an
`InklingSampling`. Their defaults are the dataclass defaults, asserted equal by
a test so the two cannot drift.

| Argument | Default | Why this default |
|---|---|---|
| `--inkling-temperature` | `0.0` | OpenRouter defaults to `1`; an optimizer driving an accept/reject gate must be reproducible |
| `--inkling-seed` / `--no-inkling-seed` | `42` | matches the example configs' seed; the negative form sends none |
| `--inkling-max-tokens` | `4096` | matches Holo's clamp, so the two backends have comparable budgets |
| `--inkling-top-p` | `1.0` | unchanged from OpenRouter |
| `--inkling-frequency-penalty` | `0.0` | unchanged |
| `--inkling-presence-penalty` | `0.0` | unchanged |
| `--inkling-stop` | none | repeatable |
| `--inkling-reasoning` / `--no-inkling-reasoning` | enabled | it is a reasoning model |
| `--inkling-reasoning-effort` | `medium` | matches the `OPENAI_REASONING_EFFORT` convention; `none` unsets it |
| `--inkling-reasoning-max-tokens` | unset | mutually exclusive with effort; both set fails closed |
| `--inkling-reasoning-exclude` | off | omit reasoning from the response |

Tool calling is deliberately not exposed. The mutation call is strict
`json_schema` plus local semantic validation; tools would be an alternative
patch format.

## Endpoints

Three request formats reach the same model. Each takes
`Authorization: Bearer $OPENROUTER_API_KEY`, `Content-Type: application/json`,
and the two optional attribution headers.

| Endpoint | Format |
|---|---|
| `POST /api/v1/chat/completions` | OpenAI Chat Completions; streaming and non-streaming |
| `POST /api/v1/responses` | OpenAI Responses API |
| `POST /api/v1/messages` | Anthropic Messages; text, images, PDFs, tools, extended thinking |

## Reasoning

Enable thinking tokens with the `reasoning` parameter. The model's internal
reasoning comes back as a `reasoning_details` array on the assistant message,
before the final answer.

**Preserve `reasoning_details` unmodified** when passing the assistant turn back
in a multi-turn conversation, or the model cannot continue reasoning from where
it left off.

```python
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(".env")
client = OpenAI(
    base_url=os.environ["OPENROUTER_BASE_URL"],
    api_key=os.environ["OPENROUTER_API_KEY"],
)

question = "How many r's are in the word 'strawberry'?"
first = client.chat.completions.create(
    model="thinkingmachines/inkling-small:free",
    messages=[{"role": "user", "content": question}],
    extra_body={"reasoning": {"enabled": True}},
)
reply = first.choices[0].message

messages = [
    {"role": "user", "content": question},
    {
        "role": "assistant",
        "content": reply.content,
        # Pass back unmodified so reasoning continues rather than restarts.
        "reasoning_details": reply.reasoning_details,
    },
    {"role": "user", "content": "Are you sure? Think carefully."},
]

second = client.chat.completions.create(
    model="thinkingmachines/inkling-small:free",
    messages=messages,
    extra_body={"reasoning": {"enabled": True}},
)
```

The `reasoning` map controls whether reasoning is enabled, the reasoning effort,
the maximum reasoning tokens, and whether reasoning is excluded from the
response.

## Streaming

Add `"stream": true` to receive server-sent events.

```bash
curl -N https://openrouter.ai/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -d '{
    "model": "thinkingmachines/inkling-small:free",
    "stream": true,
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| `reasoning` | map | — | Reasoning behavior for models supporting thinking tokens: whether reasoning is enabled, the effort, the maximum reasoning tokens, and whether reasoning is excluded from the response. |
| `temperature` | float | `1` | Influences the variety in the model's responses. |
| `top_p` | float | `1` | Limits choices to a percentage of likely tokens: only the top tokens whose probabilities sum to P. |
| `max_tokens` | integer | — | Upper limit on generated tokens. |
| `stop` | array | — | Stop generation immediately on encountering any token in the array. |
| `frequency_penalty` | float | `0` | Controls repetition based on how often tokens appear in the input. |
| `presence_penalty` | float | `0` | Adjusts how often the model repeats tokens already used in the input. |
| `seed` | integer | — | Sample deterministically; repeated requests with the same seed and parameters should return the same result. |
| `tools` | array | — | Tool calling, following OpenAI's tool-calling format. |

## Relationship to this project

Inkling is an **alternative optimizer**, a peer of Holo rather than an
extension of it. `optimizer_backend` selects one:

| `optimizer_backend` | Backend |
|---|---|
| `holo_openai_compatible` | `holo3-1-35b-a3b`, pinned by `HoloBackendConfig` |
| `inkling_openrouter` | `INKLING_MODEL`, parameters from the CLI |
| `deterministic_fake` | credential-free, used by the smoke |

The engine binds to the `ProposalBackend` protocol in
[`schemas.py`](../holoskill_gym/schemas.py), so neither backend is privileged.
Whichever is configured, the proposal is validated locally afterwards; strict
schema compliance never substitutes for edit policy.

The 35B restriction is a property of the Holo backend, not of the integration:
selecting a different optimizer is done with `optimizer_backend`, never by
pointing `HOLO_OPTIMIZER_MODEL` somewhere else.

Because the model is not reachable yet, a run configured for
`inkling_openrouter` fails closed with `InklingAccessError` rather than
producing a degraded proposal.
