# TODO — integrating further executors

HoloSkill Gym freezes the executor during a run and evolves only the
natural-language skill document. Adding an executor therefore means adding a
**rollout agent**, never a second optimizer. SkillOpt + Holo remain the only
things that propose, accept, or reject a skill edit.

Status legend: `[ ]` not started · `[~]` in progress · `[x]` done

---

## Phase 0 — Prerequisites

- [x] Vendor SEAGym at `reference/seagym` (pinned `9e61e14`)
- [x] Vendor SkillOpt at `reference/skillopt` (pinned `v0.2.0`, `e4ea6a6`)
- [x] Confirm SkillOpt v0.2.0 ships an `openai_compatible` auth mode
      (`skillopt/model/azure_openai.py`) — no local backend fork needed
- [ ] Initialise SEAGym's nested submodules; all four are currently pinned but
      empty, so Harbor and the AHE reference implementation are not on disk:
      `git -C reference/seagym submodule update --init --recursive`
- [ ] Install SEAGym: `pip install -e "reference/seagym[dev,models]"`
- [ ] Read `seagym/rollout_agents/ahe_nexau.py` end to end — it is the closest
      working precedent for every executor below

---

## Phase 1 — `CliCodeOptRolloutAgent` (MVP, spec §11)

Does not exist yet in SEAGym; we build it. One configurable agent with an
`executor` strategy field rather than one class per CLI.

- [ ] `executor: "codex_exec"` — reuse SkillOpt's `codex_backend.py` /
      `codex_harness.py` rather than reimplementing
- [ ] `executor: "claude_code_exec"` — reuse SkillOpt's `claude_backend.py`
- [ ] Fresh isolated workspace per task; checkout the pinned commit only
- [ ] Baseline correctness + benchmark run *before* the agent edits anything
- [ ] Install the checkpointed skill into the **task workspace**, never into a
      user-global Codex/Claude skill directory
- [ ] Non-interactive launch with explicit timeout and max steps; terminate the
      process group on timeout
- [ ] Block edits to tests, benchmarks, task metadata, `.git`, verifier code
- [ ] Network disabled inside the task workspace by default
- [ ] Return a valid `TrajectoryBatch` even for failed tasks; infrastructure
      failure must not score as an ordinary wrong answer

---

## Phase 2 — Claude Agent SDK executor

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

## Phase 3 — OpenAI Agents SDK executor

`pip install openai-agents`.

- [ ] Decide whether this is in scope at all — see the open question below
- [ ] If in scope, wrap it the same way as Phase 2 (subprocess, shared sandbox)
- [ ] Keep it out of the deterministic smoke path; it must stay optional

**Auth: yes, an API key is required.** The SDK expects `OPENAI_API_KEY` to be
exported and calls the Responses API by default. It *can* be pointed at other
providers through LiteLLM, any-llm, or a custom OpenAI-compatible client — but
see the constraint below before assuming H can substitute.

---

## Phase 4 — Cross-harness transfer evaluation (spec §14)

- [ ] Evolve with Codex, evaluate the frozen skill on Codex **and** Claude Code
- [ ] Evolve with Claude Code, evaluate on Claude Code **and** Codex
- [ ] Extend the matrix to any Phase 2/3 executor that lands
- [ ] Never update the skill during cross-harness evaluation

---

## Open questions

1. **Can the OpenAI Agents SDK run on Holo instead of OpenAI?**
   Only partly. `GET /v1/models` reports `supported_features` of
   `["reasoning", "tools"]` for `holo3-1-35b-a3b` but only `["reasoning"]` for
   `holo3-122b-a10b`. The Agents SDK is built on function calling, so the 122B
   model cannot back it, and the 35B model would need verification against the
   SDK's tool-call expectations. A separate `OPENAI_API_KEY` is the low-risk
   path if this phase proceeds.

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

## Executor auth summary

| Executor | Credential | Required? |
|---|---|---|
| Codex CLI | `CODEX_EXECUTABLE` + provider auth | yes |
| Claude Code CLI | `CLAUDE_CODE_EXECUTABLE` + provider auth | yes |
| Claude Agent SDK | API key **or** `ant auth login` profile | key optional |
| OpenAI Agents SDK | `OPENAI_API_KEY` | yes |
| Holo optimizer | `HAI_API_KEY` | yes |

Executor credentials pay for *target* rollouts; `HAI_API_KEY` pays for
*optimizer* proposals. Spec §13 requires these two be reported separately —
never summed into one cost figure.
