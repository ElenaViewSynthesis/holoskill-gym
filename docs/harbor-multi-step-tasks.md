# Harbor multi-step tasks

This document describes Harbor's multi-step task contract for future HoloSkill
Gym tasksets. Multi-step support belongs to the Harbor task layer; the current
Verifiers v1 Harbor adapter does not yet support it.

Related references:

- [Verifiers v1 — Harbor integration](verifiers-v1-harbor.md)
- [Harbor task and agentic-environment structure](harbor-task-structure.md)
- [Implementation roadmap](../todo.md)

## Purpose

A multi-step task runs an agent through an ordered sequence of steps in one
shared environment. Each step has its own instruction, tests, and optional setup
hook. Steps execute sequentially and produce verifier results that roll up into
one trial-level reward.

This is useful for:

- long-horizon tasks with early-stopping conditions;
- continual-learning and memory experiments;
- evaluating whether an agent builds on prior work;
- separating scaffold, implementation, verification, and documentation phases.

Harbor publishes a `create-task` coding-agent skill:

```bash
npx skills add harbor-framework/harbor --skill create-task
```

## Directory layout

A multi-step task replaces the root single-step `instruction.md`, `tests/`, and
`solution/` workflow with a `steps/` directory:

```text
my-task/
├── task.toml
├── environment/
│   └── Dockerfile
├── steps/
│   ├── step-one/
│   │   ├── instruction.md
│   │   ├── workdir/
│   │   │   ├── setup.sh
│   │   │   └── ...
│   │   ├── tests/
│   │   │   └── test.sh
│   │   └── solution/
│   │       └── solve.sh
│   └── step-two/
│       ├── instruction.md
│       └── ...
└── tests/
    └── test.sh
```

The root `environment/` remains the shared environment definition and is built
once. An optional root `tests/` directory provides shared verifier helpers and
a fallback `test.sh`. Harbor uploads root tests for every step, then overlays
step-level tests; same-named step files win.

## Configuration

Declare ordered steps with `[[steps]]` array-of-tables entries in `task.toml`:

```toml
schema_version = "1.4"
multi_step_reward_strategy = "mean"

[task]
name = "harbor/example-multi-step"
version = "1.0.0"
description = "A three-step example task"

[[steps]]
name = "scaffold"
# Stop if later steps cannot safely build on this result.
min_reward = 1.0

[steps.agent]
timeout_sec = 60.0

[steps.verifier]
timeout_sec = 30.0

[[steps]]
name = "implement"
min_reward = 0.5

[steps.agent]
timeout_sec = 120.0

[steps.verifier]
timeout_sec = 30.0

[[steps]]
name = "document"

[steps.agent]
timeout_sec = 60.0

[steps.verifier]
timeout_sec = 30.0
```

Order in `task.toml` is execution order. Every `steps[].name` must match its
directory under `steps/`.

### Step fields

| Field | Type/default | Contract |
|---|---|---|
| `name` | `string`, required | Step identifier and directory name. |
| `agent.timeout_sec` | `float \| null`, `null` | Per-step agent timeout; falls back to task-level agent timeout. |
| `agent.user` | `string \| int \| null`, `null` | Per-step agent OS user; falls back to task-level user. |
| `verifier.timeout_sec` | `float \| null`, `null` | Per-step verifier timeout; falls back to task-level verifier timeout. |
| `verifier.env` | `dict[str, str]`, `{}` | Environment variables scoped to this verifier run. |
| `verifier.user` | `string \| int \| null`, `null` | Per-step verifier OS user; falls back to task-level user. |
| `verifier.environment_mode` | `"shared" \| "separate" \| null`, `null` | Overrides trial-level verifier placement. Steps may mix modes. |
| `verifier.environment` | `EnvironmentConfig \| null`, `null` | Optional separate verifier environment for this step. |
| `min_reward` | `float \| dict[str, float] \| null`, `null` | Stops after the step if a required reward is missing or below threshold. |
| `healthcheck.command` | `string` | Command run after setup; exit zero means healthy. |
| `healthcheck.interval_sec` | `float`, `5.0` | Interval between ordinary checks. |
| `healthcheck.timeout_sec` | `float`, `30.0` | Per-check timeout. |
| `healthcheck.start_period_sec` | `float`, `0.0` | Grace period before failures count. |
| `healthcheck.start_interval_sec` | `float`, `5.0` | Check interval during the grace period. |
| `healthcheck.retries` | `int`, `3` | Consecutive failures before abort. |
| `artifacts` | `list[str \| ArtifactConfig]`, `[]` | Paths collected after this step into `steps/{name}/artifacts/`. |

A step healthcheck executes after `steps/{name}/workdir/setup.sh` and before
the agent. It supplements the top-level environment healthcheck. Failure aborts
the step and trial.

## Agent context across steps

By default, every step starts a fresh agent conversation even though the
environment persists. Pass `--resume-trajectory` when the agent should continue
its native session and receive the next instruction as a follow-up:

```bash
harbor run \
  -t path/to/multi-step-task \
  -a claude-code \
  -m anthropic/claude-sonnet-5 \
  --resume-trajectory
```

| Run mode | Step 1 | Step 2 | Step 3 | Later steps |
|---|---|---|---|---|
| default | fresh | fresh | fresh | fresh |
| `--resume-trajectory` | fresh | resume | resume | resume |

`agent.resume_trajectory` is a run/job setting, not a task field. Harbor keeps
the prior live agent state and invokes the agent's native resume behavior.
Agents without the `capabilities.resume` capability fail before Step 1 rather
than silently receiving fresh sessions.

`--load-trajectory` seeds the first session from a previous native trajectory.
It composes with resume as `(load, resume, resume, ...)`, compared with
`(load, fresh, fresh, ...)` when resume is disabled.

HoloSkill Gym must record both load/resume settings and must not infer context
continuity merely from a shared filesystem.

## The per-step `workdir/`

Files under `steps/{name}/workdir/` are uploaded into the container's `WORKDIR`
before that step's agent runs. Use this for fixtures, configuration, seed data,
and other step-local inputs.

The filesystem is shared across steps. Files produced by Step N remain visible
to Step N+1, but a later step's upload can overwrite earlier agent work. Use
non-colliding names or preserve/rename earlier state in setup when required.

### Reserved `workdir/setup.sh`

If present, `setup.sh` runs after the step's workdir files are uploaded and
before the agent starts:

- current directory: the task `WORKDIR`;
- user: the step's effective agent user;
- non-zero exit: record `exception_info`, skip agent and verifier, and abort
  remaining steps;
- visibility: the script remains in `WORKDIR` unless it removes itself.

Example self-removal:

```bash
#!/usr/bin/env bash
set -euo pipefail

# Prepare the step.

rm -- "$0"
```

## Early stopping with `min_reward`

`min_reward` gates later steps on the current step's verifier output:

- Scalar: `min_reward = 1.0` checks `rewards["reward"]`.
- Mapping: `min_reward = { correctness = 0.8, style = 0.5 }` checks every
  declared dimension and stops if any value is below threshold or missing.

A missing reward key or missing `verifier_result` is treated as negative
infinity for gating. When verification is globally disabled,
`min_reward` is ignored. Agent crashes and setup failures abort independently
of the reward threshold.

The trial-level reward is derived from the steps that actually ran.

## Trial-level reward strategy

The optional root `multi_step_reward_strategy` controls rollup. Multi-step tasks
default to `"mean"`.

| Strategy | Behavior |
|---|---|
| `mean` | For each reward key seen in any verified step, calculate the mean over steps that produced a verifier result. A missing key contributes zero; a step with no verifier result is excluded from the denominator. |
| `final` | Use the last executed step's complete verifier result. Earlier reward signals are discarded. |

Use `final` when the final step is an end-to-end verifier whose reward mapping
already represents the whole task. If early stopping fires, `final` uses the
aborted step's result, not the task author's nominal final step.

Normalized evidence must retain per-step verifier results as well as the
trial-level rollup so aggregation does not destroy learning signal.

## Per-step artifacts

Artifact collection runs once after each step's verification. Harbor writes to
`steps/{name}/artifacts/` using this ordered union:

1. root task-level `artifacts`;
2. trial-level artifacts from `TrialConfig`;
3. `steps[].artifacts` for the current step.

```toml
# Collected after every step.
artifacts = ["/app/greet.sh"]

[[steps]]
name = "document"
# Collected only for this step, in addition to task-level artifacts.
artifacts = ["/app/README.md"]
```

After the trial, `steps/document/artifacts/` contains both files, while an
earlier step contains only `greet.sh`.

For tamper-sensitive evidence and sidecar timing, also read the artifact and
separate-verifier rules in
[Harbor task and agentic-environment structure](harbor-task-structure.md).

## Mixed verifier environments

Each step can override the trial-level verifier mode:

```toml
[[steps]]
name = "build"
# Inherits the trial-level mode (shared by default).

[[steps]]
name = "grade"

[steps.verifier.environment]
docker_image = "my-org/grading-image:latest"
```

Resolution order:

1. Explicit `[steps.verifier].environment_mode` wins.
2. A step-level `[steps.verifier.environment]` with no explicit mode implies
   `separate`.
3. Otherwise the step inherits the trial-level resolution.

Tests are validated against the effective verifier environment's operating
system. A Linux agent may therefore use a Windows grading environment, or the
reverse, provided the applicable `test.sh` or `test.bat` exists.

## Worked example

Harbor's comprehensive example is
[`examples/tasks/hello-multi-step-advanced/`](https://github.com/harbor-framework/harbor/tree/main/examples/tasks/hello-multi-step-advanced).
It demonstrates per-step instructions and uploads, verifier environment
variables, healthchecks, reward gates, and per-step artifacts.

## HoloSkill Gym implementation notes

Before enabling multi-step production tasks:

- verify that the selected execution path is Harbor-native; current Verifiers
  v1 tasksets list multi-step support as a parity gap;
- give every step and attempt a stable evidence ID;
- retain per-step instructions, effective runtime policy, terminal status,
  rewards, metrics, artifact hashes, and timing;
- record whether agent context was fresh, loaded, or resumed;
- treat setup, healthcheck, environment, and verifier failures as
  infrastructure/phase failures rather than reward zero;
- ensure early-stopped trials cannot be confused with fully completed trials;
- make reward rollup explicit and deterministic.
