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
| [todo.md](todo.md) | Roadmap for further executors and their auth requirements |

## Vendored dependencies

| Path | Upstream | Pinned at |
|---|---|---|
| `reference/seagym` | [antropy-research/SEAGym](https://github.com/antropy-research/SEAGym) | `9e61e14` (main) |
| `reference/skillopt` | [microsoft/SkillOpt](https://github.com/microsoft/SkillOpt) | `v0.2.0` (`e4ea6a6`) |

```bash
git submodule update --init --recursive
```

The nested `reference/ace/kayba-ai/ace-eval` submodule is private or removed
upstream. Its initialization failure is expected and does not affect this
SkillOpt/Holo integration.

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

Holo 35B's tool-calling capability is deliberately not used for skill edits.
The optimizer requests strict structured output from the
`SkillUpdateProposal` JSON schema, then enforces semantic edit policy locally.
Codex/GPT-5.6-sol owns tool-using target rollouts through Harbor.

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

ATIF's `extra` dictionaries are the extension point for SEAGym-specific data;
the root schema otherwise forbids unknown fields. Store bounded summaries and
local artifact paths there, not complete provider logs or transcripts.

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

The H Models API serves two vision-language models built for GUI agents and
computer use. The values below are read from `GET /v1/models`, not copied from
documentation, so they reflect what this account is actually served.

| Model | Context | Max output | Features | Input / M | Output / M | Free tier |
|---|---|---|---|---|---|---|
| `holo3-1-35b-a3b` | 65,537 | 4,096 | reasoning, tools | $0.25 | $1.80 | yes, 10 req/min |
| `holo3-122b-a10b` | 65,537 | 32,768 | reasoning | $0.40 | $3.00 | no, paid tier only |

Both take text and image input and return text. There is no per-request fee;
cost is token-based only.

Two consequences worth knowing before configuring a run:

- `holo3-122b-a10b` answers `402 insufficient_credit` without paid credits, so
  `HOLO_OPTIMIZER_MODEL` defaults to the free-tier model. Add credits at
  [portal.hcompany.ai](https://portal.hcompany.ai) to switch it back.
- Both models emit a reasoning preamble that counts against `max_tokens`.
  Budget at least ~256 completion tokens or the answer is cut off before it
  starts.

Listing is not access: both models appear in `/v1/models` with `is_active` and
`is_ready` set to true, yet the 122B still refuses this key. Only a real
completion proves access.

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
