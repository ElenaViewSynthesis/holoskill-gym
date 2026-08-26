# Agents and executor bindings

How SEAGym drives coding agents it does not own, and the precedent our own
executor follows.

All paths below are relative to `reference/seagym/`.

## The worked example: AHE NexAU

`seagym/rollout_agents/ahe_nexau.py` contains **both halves** of one binding:

- `AHENexAURolloutAgent(HarborRolloutAgent)` at line 32 — the SEAGym side
- `AHENexAUHarborAgent(BaseAgent)` at line 114 — the Harbor side, *"runs AHE's
  NexAU code agent in the task sandbox"*

The NexAU implementation itself is not in SEAGym; it comes from the
`agentic-harness-engineering` submodule.

## What an executor binding is

It's the adapter that lets SEAGym drive an agent it doesn't own. Two ends, one
file:

```text
SEAGym                          sandbox
  │                                │
  │ AHENexAURolloutAgent           │  AHENexAUHarborAgent
  │   .rollout(batch, env, ...)    │    (subclasses harbor BaseAgent)
  │   → TrajectoryBatch            │    actually runs NexAU on the repo
  └────────── HarborAgentSpec ─────┘
             agent_import_path
```

The SEAGym half satisfies the `RolloutAgent` protocol —
`rollout(batch, *, env, task_index, baseline_state) -> TrajectoryBatch`. It
never runs the agent itself; it builds a `HarborAgentSpec` naming the class to
instantiate inside the sandbox:

```python
agent_import_path="seagym.rollout_agents.ahe_nexau:AHENexAUHarborAgent"
```

Harbor imports that string in the container and runs it. So the binding's job is
**translation, not execution**: turn a SEAGym task batch plus the current skill
into whatever the foreign agent expects, then turn its messy output back into a
normalized trajectory. It's the seam that keeps SEAGym ignorant of Codex flags,
Claude Code sessions, or NexAU internals.

The Harbor import in the SEAGym half is wrapped in
`try/except ModuleNotFoundError`, so the module still imports when Harbor is
absent — the sandbox half simply never runs.

## How `HarborRolloutAgent` gets used

Subclass it and override what differs. It's a dataclass carrying `agent_id`,
`agent_import_path`, `agent_kwargs`, `agent_env`, `n_attempts`, `attempt_modes`,
built from JSON by `from_config(name, config, models, run_dir, base_dir)`. Its
`harbor_agent_spec()` does one notable thing:

```python
if baseline_state is not None and "prompt_template_path" in baseline_state.metadata:
    kwargs["prompt_template_path"] = str(prompt_template_path)
```

That's the **skill-injection point**. The baseline's checkpointed state reaches
the sandboxed agent through `baseline_state.metadata`, which is precisely how
our evolving skill document will get in front of Codex or Claude Code — no
global config mutation, exactly as §18 demands.

For agents Harbor already owns, no project-specific sandbox class is needed.
Our rollout binding subclasses `HarborRolloutAgent`, selects a registered
Harbor agent ID, and leaves `agent_import_path=None`; Harbor's factory imports
the built-in implementation inside the trial. A custom `agent_import_path`
remains appropriate for foreign harnesses such as AHE NexAU.

## What this means for `CliCodeOptRolloutAgent`

`holoskill_gym.rollout_agent:CliCodeOptRolloutAgent` is implemented as one
configurable binding with an `executor` strategy field rather than one class per
CLI:

| Executor strategy | Harbor built-in agent | Custom import path |
|---|---|---|
| `codex_exec` | `codex` | none |
| `claude_code_exec` | `claude-code` | none |

`from_config()` delegates common model, environment, attempt, and agent-kwarg
handling to `HarborRolloutAgent`, then rejects optimizer-only Holo environment
variables from the target-agent environment. The checkpointed skill still
enters through `prompt_template_path`; SEAGym creates a Harbor-compatible
template without changing the stored skill bytes.

Harbor owns trial checkout, isolation, CLI installation/execution, timeouts,
network enforcement configured by the task/environment, and ATIF production.
The remaining project work is normalization and verification: convert Harbor
results and ATIF artifacts into bounded code-optimization evidence without
duplicating Harbor's sandbox.

Implementation roadmap: [todo.md](todo.md). Per-executor auth requirements
live in its deferred executor backlog.
