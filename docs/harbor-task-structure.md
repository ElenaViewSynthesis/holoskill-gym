# Harbor task and agentic-environment structure

This document is the task-authoring and runtime-policy reference for HoloSkill
Gym's Harbor data plane. It covers single-step task layout, agentic environment
configuration, verifier placement, artifacts, and reward output. Multi-step
extensions are documented separately.

Related references:

- [Verifiers v1 — Harbor integration](verifiers-v1-harbor.md)
- [Harbor multi-step tasks](harbor-multi-step-tasks.md)
- [Implementation roadmap](../todo.md)

## Create and run a task

Initialize a task package with an organization/name identifier:

```bash
harbor init --task "<org>/<name>"
```

The single-step structure is:

```text
my-task/
├── instruction.md
├── task.toml
├── environment/
│   ├── Dockerfile
│   └── ...
├── solution/
│   ├── solve.sh
│   └── ...
└── tests/
    ├── test.sh
    └── ...
```

Run an agent against the task with:

```bash
harbor run -p "<path/to/task>" -a "<agent>" -m "<model>"
```

Harbor also publishes a task-creation skill:

```bash
npx skills add harbor-framework/harbor --skill create-task
```

For sequential instructions in one persistent environment, use the
[multi-step task structure](harbor-multi-step-tasks.md).

## Task files

### `instruction.md`

Contains the instruction presented to the agent. HoloSkill Gym installs the
checkpointed skill through Harbor's task-local prompt mechanism; it must not
mutate user-global Codex or Claude configuration.

### `task.toml`

Defines task identity, phase policy, environment resources, and arbitrary
metadata. Parameters live in their respective nested sections:

```toml
schema_version = "1.4"

[task]
name = "<org>/<name>"
version = "1.0.0"
description = "A short description of the task"
authors = [{ name = "Steve Jobs", email = "steve@apple.com" }]
keywords = ["optimization", "programming"]

[metadata]
difficulty_explanation = "Why this task has its assigned difficulty"
category = "programming"

[verifier]
timeout_sec = 120.0
env = { API_KEY = "${VERIFIER_API_KEY}" }
user = "root"

[agent]
timeout_sec = 120.0
user = "agent"

[solution]
env = { API_KEY = "${SOLUTION_API_KEY}" }

[environment]
network_mode = "no-network"
build_timeout_sec = 600.0
docker_image = "some-org/some-name:some-tag"
os = "linux"
cpus = 1
memory_mb = 2048
storage_mb = 10240
gpus = 0
gpu_types = ["H100", "A100"]
env = { SOME_ENV_VAR = "${SOME_ENV_VAR}" }

[environment.tpu]
type = "v6e"
topology = "2x4"

[[environment.mcp_servers]]
name = "mcp-server"
transport = "streamable-http"
url = "http://mcp-server:8000/mcp"

[environment.healthcheck]
command = "curl -f http://localhost:8080/health"
interval_sec = 5.0
timeout_sec = 30.0
retries = 3
```

Secrets must remain environment references. Never place real credentials in a
committed task file or normalized trace.

### Task and phase fields

| Field | Type/default | Meaning |
|---|---|---|
| `schema_version` | `string`, `"1.4"` | Harbor task schema version. |
| `multi_step_reward_strategy` | `"mean" \| "final" \| null`, `null` | Multi-step reward rollup; multi-step defaults to `mean`. |
| `task.name` | `string`, required | Package identifier in `org/name` form. |
| `task.version` | `string \| null` | Task version; new tasks default to `1.0.0`. |
| `task.description` | `string`, `""` | Human-readable task purpose. |
| `task.authors` | `list[Author]`, `[]` | Author names and optional emails. |
| `task.keywords` | `list[string]`, `[]` | Search and categorization keywords. |
| `metadata` | object | Arbitrary task-author metadata. |
| `source` | `string \| null`, `null` | Optional provenance identifier. |
| `agent.timeout_sec` | `number \| null`, `null` | Agent-phase timeout. |
| `agent.user` | `string \| int \| null`, `null` | Agent OS username or UID. |
| `agent.network_mode` | `no-network \| public \| allowlist \| null`, `null` | Optional dynamic agent-phase override. |
| `agent.allowed_hosts` | `list[string] \| null`, `null` | Agent-phase allowlist when that mode is selected. |
| `verifier.timeout_sec` | `number`, `600.0` | Verifier-phase timeout. |
| `verifier.user` | `string \| int \| null`, `null` | Verifier OS username or UID. |
| `verifier.env` | object, `{}` | Verifier environment variables. |
| `verifier.network_mode` | `no-network \| public \| allowlist \| null`, `null` | Optional dynamic verifier-phase override. |
| `verifier.allowed_hosts` | `list[string] \| null`, `null` | Verifier-phase allowlist. |
| `verifier.environment_mode` | `shared \| separate \| null`, `null` | Verifier placement. |
| `verifier.environment` | `EnvironmentConfig \| null`, `null` | Dedicated grading environment. |
| `solution.env` | object, `{}` | Oracle solution environment variables. |

### Environment fields

| Field | Type/default | Meaning |
|---|---|---|
| `environment.build_timeout_sec` | `number`, `600.0` | Environment build timeout. |
| `environment.docker_image` | `string \| null`, `null` | Pullable pre-built image reference. |
| `environment.os` | `linux \| windows`, `linux` | Target container OS. |
| `environment.cpus` | `integer \| null`, `null` | Requested CPU count. |
| `environment.memory_mb` | `integer \| null`, `null` | Requested memory in MiB. |
| `environment.storage_mb` | `integer \| null`, `null` | Requested disk space in MiB. |
| `environment.gpus` | `integer \| null`, `null` | Requested GPU count. |
| `environment.gpu_types` | `list[string] \| null`, `null` | Acceptable GPU types. |
| `environment.tpu.type` | `string` | TPU alias or canonical GKE accelerator label. |
| `environment.tpu.topology` | `string` | Required positive `NxM`/`NxMxK` topology. |
| `environment.network_mode` | `no-network \| public \| allowlist \| null` | Environment network baseline; effective default is `public`. |
| `environment.allowed_hosts` | `list[string] \| null`, `null` | Baseline allowlist. |
| `environment.allow_internet` | `boolean \| null`, `null` | Deprecated compatibility field. |
| `environment.env` | object, `{}` | Host-resolved variables; `${VAR}` and `${VAR:-default}` are supported. |
| `environment.mcp_servers` | list, `[]` | Agent-visible MCP server definitions. |
| `environment.skills_dir` | `string \| null`, `null` | Skills copied into the agent's configuration directory. |

A task allocates one TPU slice per pod. Its chip count is the product of the
topology dimensions. TPU support depends on the environment provider and is
currently associated with GKE-capable runtimes.

### Healthcheck fields

| Field | Type/default | Meaning |
|---|---|---|
| `environment.healthcheck.command` | `string` | Exit zero means healthy. |
| `interval_sec` | `number`, `5.0` | Interval after the start period. |
| `timeout_sec` | `number`, `30.0` | Timeout for one check. |
| `start_period_sec` | `number`, `0.0` | Grace period before failures count. |
| `start_interval_sec` | `number`, `5.0` | Check interval during the grace period. |
| `retries` | `integer`, `3` | Consecutive failures before failure. |

### Metadata templates

Pre-populate task defaults from a TOML template:

```bash
harbor tasks init "<task-name>" --metadata-template task-template.toml
```

Template sections override Harbor defaults; unspecified values retain their
normal defaults.

## Network policy

Network control has three layers:

1. Baselines applied when an environment starts and restored between phases.
2. Optional agent/verifier phase overrides active only during the phase.
3. Run-time host merges from the CLI.

| Field | Layer | Application |
|---|---|---|
| `[environment].network_mode` | baseline | Agent environment start and shared-verifier baseline. |
| `[verifier.environment].network_mode` | baseline | Separate-verifier environment start. |
| `[steps.verifier.environment].network_mode` | baseline | Per-step separate-verifier start. |
| `[agent].network_mode`, `[steps.agent].network_mode` | override | Matching `agent.run()` only. |
| `[verifier].network_mode`, `[steps.verifier].network_mode` | override | Matching `verify()` only. |
| `--allow-environment-host` | runtime merge | Adds to `environment.extra_allowed_hosts`. |
| `--allow-agent-host` | runtime merge | Adds to agent-phase hosts. |

Verifier baseline selection:

- shared verifier: top-level `[environment]`;
- separate verifier: `[verifier.environment]` when declared, otherwise a copy
  of `[environment]`.

`network_mode` accepts:

- `public`;
- `no-network`;
- `allowlist`, with `allowed_hosts`.

An empty or omitted allowlist denies all egress. Entries are exact hostnames,
IPv4/IPv6 literals or CIDRs, or supported leading wildcard hostnames such as
`*.example.com`; they are not URLs, ports, paths, or bracketed IPv6 strings.
Hostnames are exact, so `ubuntu.com` does not automatically allow
`ask.ubuntu.com`. For portability, list both the apex and wildcard form if both
are required.

Legacy `allow_internet = false` maps to `no-network` only when the current
`network_mode` is absent.

If a phase override differs from its baseline, the provider must implement
`dynamic_network_policy` or Harbor rejects the task. Prefer a separate verifier
environment when the grader needs a different baseline. Runtime host flags on a
`public` baseline are ignored with a warning.

For HoloSkill code-optimization tasks, the production default should be
`no-network` during agent execution. Any exception must be explicit, minimal,
and recorded in evidence.

## Environment definition

Harbor does not require one universal file under `environment/`; requirements
depend on the selected environment provider. `DockerEnvironment` accepts:

- `[environment].docker_image`;
- `environment/Dockerfile`; or
- `environment/docker-compose.yaml`.

When neither Dockerfile nor compose file is present, other files under
`environment/` are uploaded to the container workdir at startup. Use
`--force-build` only when a Dockerfile exists and rebuilding instead of pulling
is intentional. Many cloud sandbox providers support Dockerfile-defined images
but not Docker Compose.

`[environment].os` defaults to Linux. Windows tasks use Windows paths and
`test.bat`/`solve.bat`; Harbor adapts command execution, file transfer, and
script discovery.

### Reserved runtime paths

| Linux path | Purpose |
|---|---|
| `/logs/verifier/` | Reward files and verifier logs. |
| `/logs/agent/` | Agent-owned runtime logs and trajectories. |
| `/logs/artifacts/` | Conventional agent-to-verifier artifact publication directory. |
| `/solution/` | Oracle solution uploaded by Harbor. |
| `/tests/` | Verifier tests uploaded or supplied by the grading image. |

Windows containers use equivalent paths under `C:/`. Harbor downloads
`/logs/` after the run for debugging and analysis.

## Oracle solution

`solution/` is optional. Linux tasks use `solution/solve.sh`; Windows tasks use
`solve.bat`. Harbor copies it into `/solution` and executes it from the task
workdir when using the Oracle agent. Without a solution, the Oracle cannot
sanity-check the task.

The solution must never be exposed to the evaluated agent.

## Tests and reward output

Linux tasks require `tests/test.sh`; Windows tasks require `test.bat`. Other
test dependencies may live beside the entrypoint. For shared verification,
Harbor uploads the directory to `/tests` and invokes the script from the task
workdir. Use absolute paths to avoid workdir ambiguity.

The verifier must write a reward file:

| File | Format | Meaning |
|---|---|---|
| `/logs/verifier/reward.txt` | One finite number | Scalar score, commonly `1` or `0`. |
| `/logs/verifier/reward.json` | Finite number or object of finite numbers | Scalar/multidimensional rewards and metrics. |

Harbor reads JSON first and falls back to text. A robust shell wrapper preserves
the test command's status:

```bash
#!/usr/bin/env bash
set -uo pipefail

if uvx pytest /tests/test.py; then
  printf '%s\n' 1 > /logs/verifier/reward.txt
else
  printf '%s\n' 0 > /logs/verifier/reward.txt
fi
```

For HoloSkill Gym, reward zero is valid only after successful infrastructure
and verifier execution. Missing, malformed, non-finite, timed-out, or
unreachable grading must be classified separately.

## Shared and separate verifier environments

Shared verification (the default) runs tests in the agent's environment. This
is fast but exposes tests/dependencies and inherits agent modifications.

Use a dedicated grading environment for clean or private verification:

```toml
[verifier]
environment_mode = "separate"

[verifier.environment]
docker_image = "my-org/grading-image:latest"
cpus = 2
memory_mb = 1024
network_mode = "no-network"
```

Resolution rules:

| `environment_mode` | `[verifier.environment]` | Result |
|---|---|---|
| omitted | omitted | shared |
| omitted | present | separate |
| `shared` | omitted | shared |
| `shared` | present | validation error |
| `separate` | omitted | separate, using a fresh copy of `[environment]` |
| `separate` | present | separate, using the declared verifier environment |

Harbor-native separate verifier images may be built from the applicable
`tests/` directory. The image itself must provide `/tests/test.sh` or
`C:/tests/test.bat`; Harbor does not upload the tests at runtime in this mode.

```text
my-task/
├── task.toml
├── instruction.md
├── environment/
│   └── Dockerfile
└── tests/
    ├── Dockerfile
    ├── test.sh
    └── grader.py
```

When running through Verifiers v1, declared verifier images must instead be
pre-built and pullable; see its
[current parity gaps](verifiers-v1-harbor.md#current-verifiers-parity-gaps).

## Transfer into a separate verifier

Harbor transfers these inputs from the solver environment into the fresh
grader at the same absolute paths:

- `/logs/artifacts/`;
- task-level artifacts;
- trial-level artifacts;
- current step artifacts.

Parent directories are created automatically. `/logs/agent/` and
`/logs/verifier/` are not transferred implicitly. To grade a trajectory,
declare it explicitly:

```toml
artifacts = ["/logs/agent/trajectory.json"]
```

The separate verifier then reads the same path. Artifact declarations are part
of the grading interface and should be hashed in normalized evidence.

## Sidecar artifacts and collect hooks

Harbor-native Docker Compose tasks can collect evidence from sidecar services.
This is not yet supported by the current Verifiers v1 Harbor adapter.

Select a service on an artifact entry:

```toml
artifacts = [
  "/app/output.json",
  { source = "/var/log/api/requests.log", service = "api" },
]
```

Run a snapshot command after the agent phase and then collect its output:

```toml
[[verifier.collect]]
service = "postgres"
command = "pg_dump -U postgres app > /tmp/dump.sql"
timeout_sec = 60.0

artifacts = [{ source = "/tmp/dump.sql", service = "postgres" }]
```

Commands targeting `main` run with Bash. Sidecar commands use POSIX `sh -c`
because arbitrary service images may not contain Bash. Invoke Bash explicitly
only when the image supplies it, or package a script in the image.

### Trust boundary

- Sidecar evidence is trustworthy only when the agent could not gain code
  execution or filesystem access in that service. Network reachability alone is
  not filesystem access, but task authors must secure the service.
- Hooks targeting `main` execute in the agent-controlled environment; their
  output is agent-influenceable and unsuitable for tamper-sensitive signals.
- In a single-step trial and the final step of a multi-step trial, Harbor stops
  `main` before sidecar collection so leftover agent processes cannot interfere.
- Earlier multi-step collection happens while `main` remains live. Treat that
  evidence as agent-influenceable and place tamper-sensitive sidecar grading on
  the final step.

All services share one flat artifacts base. Equal or nested source paths from
different services collide. Harbor warns at load time and keeps the first
claimant during collection, recording skips in `manifest.json`. Avoid overlap;
sidecar sources must be absolute paths.

Sidecar artifacts require a compose-capable provider. Harbor lists Docker and
several hosted providers; portability must be verified for the runtime selected
by the experiment.

## Agentic-environment implementation contract

Production HoloSkill tasks should follow these rules:

1. Pin and record the repository commit before agent execution.
2. Use a fresh Harbor-managed task environment for each attempt.
3. Run baseline correctness and benchmarks before modifications.
4. Install the checkpointed skill through task-local Harbor configuration.
5. Default the agent phase to `no-network`; declare narrow exceptions.
6. Protect tests, benchmarks, `.git`, task metadata, and verifier code.
7. Compute the patch from the pinned commit before final verification.
8. Prefer a separate verifier for tamper-sensitive correctness and benchmark
   evidence.
9. Produce explicit finite reward/metric fields and distinguish all
   infrastructure failures from valid zero scores.
10. Collect only declared, bounded artifacts and record their hashes and source
    paths.
11. Preserve Harbor's canonical ATIF/task formats; place project extensions
    under `extra.holoskill_gym` or namespaced metadata.
12. Record effective environment, resources, timeouts, network policy, users,
    executor/model identity, and verifier mode for reproducibility.

These rules are implementation requirements for roadmap Steps 2 and 3, not a
claim that the production Harbor tasksets already exist.
