# Verifiers v1 — Harbor integration

This document is the implementation reference for connecting HoloSkill Gym's
normalized verifier evidence to Harbor-backed tasks through Verifiers v1. It
supports roadmap Steps 2 and 3; it does not mark either step as implemented.

Related references:

- [Harbor multi-step tasks](harbor-multi-step-tasks.md)
- [Harbor task and agentic-environment structure](harbor-task-structure.md)
- [Implementation roadmap](../todo.md)

## Built-in Harbor tasksets

`verifiers` provides built-in Harbor support through `HarborTaskset`. For a
dataset already registered with Harbor, set the dataset name and inherit the
taskset implementation:

```python
import verifiers.v1 as vf
from verifiers.v1.tasksets.harbor import HarborConfig, HarborTask, HarborTaskset


class TerminalBench2Config(HarborConfig):
    # Use the same name registered in the Harbor registry.
    dataset: str = "terminal-bench/terminal-bench-2"


class TerminalBench2Taskset(
    HarborTaskset, vf.Taskset[HarborTask, TerminalBench2Config]
):
    pass
```

The dataset is loaded automatically.

## Custom task loading and pre-built images

Tasksets may customize `load()`. A common case is assigning pullable images to
tasks whose `task.toml` does not declare one:

```python
from pathlib import Path
from typing import Literal

import verifiers.v1 as vf
from verifiers.v1.tasksets.harbor import HarborConfig, HarborTask, HarborTaskset

IMAGE_TEMPLATE = "registry.example.com/openthoughts/{task}:latest"


class OpenThoughtsTBLiteConfig(HarborConfig):
    dataset: Literal["openthoughts/openthoughts-tblite"] = (
        "openthoughts/openthoughts-tblite"
    )
    # Use the pre-built image rather than building at runtime.
    ignore_dockerfile: bool = True


class OpenThoughtsTBLiteTaskset(
    HarborTaskset, vf.Taskset[HarborTask, OpenThoughtsTBLiteConfig]
):
    def load(self) -> list[HarborTask]:
        # Row data is frozen, so rebuild every task around an updated copy.
        return [
            HarborTask(
                task.data.model_copy(
                    update={
                        "image": IMAGE_TEMPLATE.format(
                            task=Path(task.data.task_dir).name
                        )
                    }
                ),
                task.config,
            )
            for task in super().load()
        ]
```

Build the task Dockerfile, push the image to a registry, and place the resulting
reference in the task's `image` field. On the Prime runtime, any pullable image
reference works. The first sandbox using a reference builds and caches the VM
form when needed; this can take about ten minutes and appears as `build` in the
evaluation dashboard. Later sandboxes using the same reference normally start
in seconds.

## Timeouts and resource multipliers

By default, Verifiers ignores the agent and verifier timeouts declared by a
Harbor task (`ignore_timeouts = true`). Harbor-authored limits assume Harbor's
own runtime, so applying them to a different inference stack can confound model
capability with inference speed.

Set `ignore_timeouts = false`, or pass
`--no-env.taskset.ignore-timeouts`, for a faithful comparison with Harbor's
declared limits. A taskset can then scale its timeouts and resources:

```toml
[env.taskset]
id = "MY_TASKSET"
ignore_timeouts = false
timeout_multiplier = 2.0
resource_multiplier = 2.0
```

- `timeout_multiplier` scales both agent and verifier timeouts.
- `resource_multiplier` scales CPU, memory, and disk allocations.

Use these only as explicit experimental settings and record their resolved
values in normalized evidence.

## Network policies

Harbor's effective agent network policy applies to Docker and Prime VM harness
runtimes. An `[agent].network_mode` override takes precedence over the
`[environment]` baseline. Harbor normalizes the legacy
`[environment].allow_internet` field into the current schema.

| Harbor mode | Effective task policy |
|---|---|
| `public` | Sets the task allowlist to `["*"]` while leaving evaluator policy intact. |
| `no-network` | Sets the task allowlist to `[]`; only framework routes remain. |
| `allowlist` | Sets the task allowlist to `allowed_hosts`. |

Trusted task and harness setup remains online. The policy begins immediately
before the agent phase and remains active through finalization and scoring.
Interception and MCP URLs are added automatically in allowlist and
framework-only modes.

Concrete task/runtime allowlists combine, as do blocklists. Framework-only
access on either side takes precedence. Concrete allowlists cannot be combined
with blocklists. Docker framework routes take precedence over deny rules;
ordinary Prime deny rules remain unchanged and may block a matching route.
Restricted Harbor tasks require Docker or a Prime VM. Prime also accepts
host-level entries.

## Artifacts and collect hooks

Verifiers reads `artifacts = [...]` and `[[verifier.collect]]` from
`task.toml`. Collect hooks execute in the agent's box during task finalization:
after the agent phase and before collection. Declared paths and the
`/logs/artifacts/` convention directory are carried into the grading box and
restored at their original paths. There is no path translation.

Verifiers deliberately differs from `harbor run` in two places:

1. A failing collect hook fails the rollout. Harbor logs the failure and
   continues because the output is observational there; in Verifiers, the
   output is grading input and a silently missing file could grade stale state.
2. An artifact `destination` has no effect. Harbor uses it to position a file
   in a host trial directory. Verifiers has no equivalent trial directory—the
   trace is the record—and `destination` never changes verifier-side placement.

The normalized HoloSkill record should retain artifact paths and hashes, not
embed unbounded artifact bodies.

## Separate verifier environments

`[verifier].environment_mode = "separate"` grades in a second box that the
agent never touched. Under the Harbor environment, task finalization follows
this sequence:

1. Run the solver in the task environment.
2. Collect declared artifacts and `/logs/artifacts/` while that environment is
   alive.
3. Tear down the solver environment.
4. Provision a fresh grading environment.
5. Restore artifacts at their original paths.
6. Stage fresh tests and run the verifier.
7. Record verifier rewards and metrics on the solver trace.

The grading runtime derives from the solver runtime policy unless
`--env.verifier-runtime.*` selects another. A network-restricted verifier on
Prime requires `vm = true`. Infrastructure failures are retried according to
`--env.verifier-retries`; an unreachable grading box must never be represented
as reward zero.

The primary score is read from `/logs/verifier/reward.json`:

- A finite number is a scalar reward.
- An object must contain only finite numbers.
- If the object has a `reward` key, that value is the score and the remaining
  keys are metrics.
- Without a `reward` key, every key is recorded as a separate reward.
- Missing or invalid JSON falls back to `/logs/verifier/reward.txt`.

The verifier image follows Harbor resolution rules: use a declared
`[verifier.environment]`; otherwise use a fresh copy of `[environment]`.

A declared separate verifier environment needs a pullable `docker_image` when
run through Verifiers. Harbor can build a verifier image from
`tests/Dockerfile`, but Verifiers does not build images. Build and publish it in
advance. `ignore_dockerfile` grades in the agent image instead and warns because
that is not the environment declared by the task.

Under any non-Harbor environment, a separate-verifier task refuses to grade in
the agent's box. `ignore_separate_verifier = true` explicitly forces shared
grading, trading isolation for one sandbox per task.

## Current Verifiers parity gaps

Verifiers v1 does not yet have full Harbor parity. The notable missing features
are:

- switching to a different verifier-phase network policy for a shared verifier;
  a separate verifier's own policy is supported;
- building a verifier image from `tests/Dockerfile` when a declared
  `[verifier.environment]` has no `docker_image`;
- sidecar services and their artifact/collect-hook flow;
- Harbor multi-step tasks.

The last two are Harbor capabilities documented in the related references, but
must not be presented as supported by the current Verifiers taskset until its
implementation gains parity.

## HoloSkill Gym implementation contract

For roadmap Step 2, the adapter should consume the Harbor/Verifiers trace and
produce one bounded, deterministic evidence record per task attempt. At a
minimum it must distinguish:

- agent failure, verifier failure, infrastructure failure, and valid reward
  zero;
- shared and separate verifier modes;
- configured versus effective timeouts, resources, and network policy;
- reward dimensions and auxiliary metrics;
- artifact declarations, collection failures, restored paths, and hashes;
- task, attempt, checkpoint, executor, model, repository commit, and skill
  identity.

For roadmap Step 3, task materialization must preserve Harbor's task schema and
security boundary. HoloSkill-specific fields belong in namespaced metadata or
normalized evidence, not in a forked task format.
