# Docker runtime for Harbor tasks

Everything needed to run a HoloSkill task package through Harbor's `docker`
environment without the sandbox denying access to the Docker socket.

Related references:

- [Harbor](harbor.md)
- [Harbor task and agentic-environment structure](harbor-task-structure.md)
- [Implementation roadmap](../todo.md)

Values below were read from this machine on 2026-08-28, not copied from
documentation.

## What Harbor needs from Docker

Harbor does not shell out to the `docker` CLI for orchestration. It talks to
the **Docker Engine API over a socket**, so the process running `harbor` needs
read/write access to that socket. Three things follow:

1. A reachable daemon endpoint (`DOCKER_HOST`, or the platform default).
2. Permission on the socket, which on Linux means group membership, not `sudo`.
3. Permission to *build*, not only to run: every task package has its own
   `environment/Dockerfile` that Harbor builds before the trial starts.

If any of these is missing the failure usually reads as
`permission denied while trying to connect to the Docker daemon socket` or
`Cannot connect to the Docker daemon`. Both are access problems, not task
problems.

## This machine: Windows + Docker Desktop + WSL

The project runs from WSL, while Docker Desktop runs on the Windows side. The
bridge is Docker Desktop's WSL integration, which exposes the daemon inside the
distro at the usual Unix socket path.

Verify all four before running anything:

```bash
# 1. Daemon reachable from the Windows side
docker version --format '{{.Server.Version}}'      # 29.5.2

# 2. Daemon reachable from inside WSL
wsl -e bash -lc "docker version --format '{{.Server.Version}}'"   # 29.5.2

# 3. The socket exists in the distro
wsl -e bash -lc "ls -l /var/run/docker.sock"
# srw-rw---- 1 root docker 0 ... /var/run/docker.sock

# 4. Your user is in the docker group, so no sudo is needed
wsl -e bash -lc "id -nG | tr ' ' '\n' | grep -x docker"           # docker
```

Step 3 shows the socket is owned `root:docker` with group read/write. Step 4 is
what turns that into access for you. If step 4 prints nothing:

```bash
sudo usermod -aG docker "$USER"
# then start a new WSL session -- group membership is read at login
wsl --shutdown
```

If step 2 fails but step 1 succeeds, the distro is not enabled for integration.
In Docker Desktop: **Settings → Resources → WSL integration**, enable this
distro, then **Apply & restart**. Confirm the daemon is set to start with the
Desktop app, or the socket will be absent after a reboot.

Do not work around a socket problem with `sudo harbor ...`. Running the harness
as root creates job artifacts your normal user cannot read afterwards.

### Windows-side alternative

If you run `harbor` from PowerShell instead of WSL, Docker Desktop exposes a
named pipe rather than a Unix socket:

```powershell
docker context ls
# desktop-linux *  Docker Desktop  npipe:////./pipe/dockerDesktopLinuxEngine
```

No extra configuration is needed there; the pipe's ACL already grants the
logged-in user. The rest of this document assumes WSL.

## The task image

Every package builds its own image. From
[`data/holoskill-codeopt-v1/observer/codeopt-train-001/environment/Dockerfile`](../data/holoskill-codeopt-v1/observer/codeopt-train-001/environment/Dockerfile):

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir pytest==8.3.3

WORKDIR /app
COPY repo/ /app/

RUN git init -q /app \
 && git -C /app config user.email "task@holoskill.invalid" \
 && git -C /app config user.name "HoloSkill Task" \
 && git -C /app add -A \
 && git -C /app commit -q -m "pinned baseline"
```

Two details matter operationally:

- **`git` is installed explicitly.** `python:3.12-slim` does not ship it, and
  the image commits a pinned baseline so the verifier can compute
  `git status --porcelain` to derive changed files for the edit-policy check.
  Without the install the build fails at `git init`.
- **The build needs network** for `apt-get` and `pip`, which is why the build
  phase is not `no-network`. See the next section.

## Network phases

Network policy is per phase, not per task. A single task legitimately needs
egress during the build, possibly during the agent phase, and none at all
during verification. `task.toml` sets each independently:

```toml
[environment]
network_mode = "allowlist"
allowed_hosts = ["deb.debian.org", "security.debian.org",
                 "registry.npmjs.org", "nodejs.org",
                 "raw.githubusercontent.com", "downloads.claude.ai"]

[agent]
network_mode = "allowlist"
allowed_hosts = ["api.openai.com", "api.anthropic.com"]

[verifier]
network_mode = "no-network"
```

| Phase | Mode | Why |
|---|---|---|
| `[environment]` | allowlist | `apt-get` and `pip` during build; the agent CLI's own installer may need npm/nodejs |
| `[agent]` | allowlist | the coding agent calls its model provider |
| `[verifier]` | `no-network` | grading must not depend on anything remote, and a task must not be able to phone out during scoring |

### The egress-control sidecar

`allowlist` is not enforced by Docker. Docker networking is all-or-nothing: a
container either has a network or it does not. To allow *some* hosts, Harbor
runs a second container beside the task and forces the task's traffic through
it.

The first time any phase uses `allowlist`, you will see this and it takes a
minute:

```text
Building Docker image harbor-prebuilt:harbor-docker-egress-control-sidecar--<hash>
```

That is the most common reason a first run appears to stall immediately after
starting. The image is cached afterwards, so later runs skip it.

How it works, from
`reference/seagym/reference/harbor/src/harbor/environments/docker/harbor-docker-egress-control-sidecar/`:

- The image is [GOST](https://github.com/go-gost/gost) 3.2.7, pinned by digest,
  running as a **transparent proxy** on port 12345.
- `entrypoint.sh` installs an `nftables` ruleset named `gost_egress` that
  redirects the task's outbound traffic into that proxy. This is why the
  sidecar is granted `NET_ADMIN` and `NET_RAW` in
  `docker-compose-egress-control.yaml` — without those capabilities it cannot
  install the ruleset and the run fails before the task starts.
- Matching is by **hostname, not IP**, via TLS SNI sniffing
  (`sniffing: true` in `gost.yaml`). That is what makes
  `allowed_hosts = ["api.openai.com"]` meaningful for a host behind a CDN whose
  addresses change.
- The allowlist is a file, `/opt/egress-sidecar/allowlist.txt`, re-read every
  second (`reload: 1s`). Per-phase policy switching therefore needs no
  container restart: Harbor rewrites the file between the agent and verifier
  phases and the proxy picks it up.
- Readiness is a healthcheck on a marker file, polled every second up to 30
  times, so the sidecar has roughly 30 seconds to come up before the trial
  fails.

Two operational consequences:

- **A host missing from the allowlist fails as a connection error inside the
  task**, not as a Harbor error. If a build dies on `apt-get` or an agent
  cannot reach its provider, check `allowed_hosts` before suspecting
  credentials.
- **`no-network` everywhere avoids the sidecar entirely**, which is faster and
  simpler — but it will fail any task whose image needs `apt-get` or `pip` at
  build time, which includes all five packages here.

### Allowlist enforcement and the vendored Harbor pin

Daytona enforces `allowed_hosts` from **Harbor v0.17.0 onward**. Support landed
in [#2147](https://github.com/harbor-framework/harbor/pull/2147) (`60d4374d`,
2026-07-02): `_network_kwargs()` emits `domain_allow_list` when hostnames are
present and `network_allow_list` for CIDRs, clearing the opposing field when
switching between them. Hostname allowlisting is therefore supported directly,
not approximated by address ranges.

**This repository pins `f7110f1a` (2026-06-23, `v0.15.0-33`), which predates
that fix by nine days.** Until the pin moves, on this checkout only:

| `network_mode` | `-e docker` | `-e daytona` (at our pin) |
|---|---|---|
| `no-network` | blocked | blocked |
| `allowlist` | enforced by the sidecar | **degrades to public egress** |

The degradation is silent — same task config, both runs succeed, only
containment differs — so a task validated locally under Docker would run
remotely with weaker containment and nothing in the trial output would say so.

Two ways to resolve, in order of preference:

1. **Move the pin to v0.17.0 or later** (upstream is at v0.22.0). This is the
   real fix and removes the divergence entirely. It is a submodule bump plus
   re-verification of the three vendor patches against the newer tree.
2. **Until then**, either accept public egress for Daytona runs and record it
   in the run manifest, or set those phases to `no-network` and pre-bake
   dependencies into the snapshot.

The egress-control sidecar described above remains Docker-specific in every
version; Daytona enforces policy through its own API rather than a sidecar.

### Daytona strategies: Direct and DinD

DinD = Docker-in-Docker. Harbor's Daytona environment has two strategies,
chosen by whether the task needs one container or several.

**`_DaytonaDirect`** — "the original single-container behavior." Harbor asks
Daytona for one sandbox, and the task runs in it. Simple, and enough for our
five packages, which are each a single image.

**`_DaytonaDinD`** — for multi-container tasks. From its own docstring:

```text
Local machine (harbor CLI)
  └── Daytona Sandbox (DinD VM, docker:28.3.3-dind)
        ├── dockerd (Docker daemon)
        └── docker compose
              ├── main        ← agent runs here
              ├── mcp-server  ← sidecar services
              └── ...
```

The remote sandbox is itself a Docker host — `docker:28.3.3-dind`, running its
own `dockerd` inside. Harbor then runs `docker compose` within that sandbox to
bring up several containers.

The reason it exists: Daytona's API hands you one sandbox, but a task may need
a service graph — the agent container plus an MCP server, a database, a mock
API. Rather than asking the provider for a multi-container primitive it does
not offer, Harbor nests a whole Docker host inside the single sandbox it can
get, then uses ordinary compose inside it.

Two operational details from `environments/daytona/environment.py`:

- Harbor starts `dockerd` itself, because the DinD image entrypoint is not run
  by Daytona, then waits up to `_DOCKER_DAEMON_TIMEOUT_SEC = 60` for the daemon
  to accept connections. A DinD trial that fails in the first minute is usually
  this, not the task.
- The DinD sandbox is created with `network_block_all=False` regardless of task
  policy, because the daemon needs network to pull images. Combined with the
  allowlist gap above, a DinD task on Daytona has the weakest containment of
  any path documented here.

## Running a task

Harbor is installed in the project environment, not globally, so that the CLI
and SEAGym use the same pinned API version:

```bash
wsl -e bash -lc "cd /mnt/c/Users/proxi/Documents/codex-6/cua-holo && .venv-linux/bin/harbor --version"
# 0.15.0
```

Build and run the first repaired task through Docker Desktop with the reference
solution, which needs no model credentials:

```bash
.venv-linux/bin/harbor run \
  -p data/holoskill-codeopt-v1/observer/codeopt-train-001 \
  -e docker \
  -a oracle \
  --n-concurrent 1 \
  -y
```

| Flag | Meaning |
|---|---|
| `-p` | path to the task package |
| `-e docker` | environment type; also `daytona`, `e2b`, `apple-container` |
| `-a oracle` | the oracle agent applies `solution/solve.sh` instead of calling a model |
| `--n-concurrent 1` | one trial at a time; keep this for a first run |
| `-y` | auto-confirm, so the run does not block on a prompt |

**Start with `-a oracle`.** It proves the image builds, the tests run, the
benchmark measures, and the verifier writes a reward — without spending a
token or needing a provider key. If oracle fails, a real agent would have
failed for the same reason and cost money to discover it.

Once oracle passes, swap in a real executor and its credential:

```bash
export OPENAI_API_KEY=...
.venv-linux/bin/harbor run \
  -p data/holoskill-codeopt-v1/observer/codeopt-train-001 \
  -e docker -a codex -m gpt-5.6-sol --n-concurrent 1 -y
```

## Where results land

`harbor run` writes to `jobs/<timestamp>/<task>__<id>/`:

| Path | Contents |
|---|---|
| `config.json` | the resolved agent and environment configuration |
| `trial.log` | build and execution log; read this first when a run fails |
| `verifier/` | `reward.json` / `reward.txt` from `tests/test.sh` |
| `agent/` | agent-owned logs and trajectory |
| `artifacts/` | files published from `/logs/artifacts/` |

`jobs/` is run output and should stay out of version control.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `permission denied ... docker daemon socket` | user not in `docker` group | `sudo usermod -aG docker "$USER"`, then `wsl --shutdown` |
| `Cannot connect to the Docker daemon` from WSL only | WSL integration off for this distro | Docker Desktop → Settings → Resources → WSL integration |
| Socket missing after reboot | Desktop not started | start Docker Desktop, or enable start-on-login |
| Build fails at `git init` | image lacks `git` | `apt-get install git` in the task Dockerfile |
| Build fails at `apt-get` / `pip` | build phase has no egress | give `[environment]` an `allowlist` with the needed hosts |
| Run stalls just after starting | egress-control sidecar building | wait; it is cached after the first run |
| Verifier cannot reach a host | `[verifier] network_mode = "no-network"` | intended — grading is offline by design |

## Relationship to a SEAGym run

`harbor run` is for developing and debugging one package. A SEAGym experiment
never calls it: the backend and concurrency come from the experiment config
instead, and SEAGym drives Harbor through `CliCodeOptRolloutAgent`.

```json
{"backend": {"name": "harbor", "env": "docker", "n_concurrent": 1}}
```

`env` takes the same values as `-e`. The same Docker access requirements apply,
because it is the same daemon doing the work.
