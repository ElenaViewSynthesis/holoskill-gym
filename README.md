# holoskill-gym

SEAGym x SkillOpt x Holo: self-evolving skills for CLI coding agents.

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
python -m holoskill_gym.preflight --optimizer
```

Copy `.env.example` to `.env` and set `HAI_API_KEY` first.
