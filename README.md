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
| [todo.md](todo.md) | Implementation roadmap for the production data plane, plus the deferred executor backlog |
| [docs/skillopt_holo.md](docs/skillopt_holo.md) | Production architecture, evidence, verifier, metrics, experiment matrix, eval/resume, privacy, and limitations |
| [docs/docker-harbor-runtime.md](docs/docker-harbor-runtime.md) | Docker socket access, WSL integration, network phases, and running a task package end to end |
| [docs/harbor.md](docs/harbor.md) | What Harbor is, installing it, and running a dataset or a single task package from the CLI |
| [docs/verifiers-v1-harbor.md](docs/verifiers-v1-harbor.md) | Verifiers v1 to Harbor: taskset, reward, artifact and separate-grader contracts, and current parity gaps |
| [docs/harbor-task-structure.md](docs/harbor-task-structure.md) | Harbor task authoring: single-step layout, agentic runtime policy, verifier placement and reward output |
| [docs/harbor-multi-step-tasks.md](docs/harbor-multi-step-tasks.md) | Harbor's sequential multi-step task contract, documented as a future extension |

## Papers and upstream projects

The four components this project composes, with the citation each upstream
repository asks for.

| Component | Role here | Reference |
|---|---|---|
| **SEAGym** | Evaluator — checkpoints and measures, never accepts or rejects | [arXiv:2606.17546](https://arxiv.org/abs/2606.17546) |
| **SkillOpt** | Method — owns the private held-out acceptance gate | [arXiv:2605.23904](https://arxiv.org/abs/2605.23904) · [project page](https://microsoft.github.io/SkillOpt/) |
| **Harbor** | Execution — containerized task isolation and agent runs | [10.5281/zenodo.20953922](https://doi.org/10.5281/zenodo.20953922) · [tbench.ai](https://www.tbench.ai) |
| **AlgoTune** | Candidate external task source (154 optimization tasks) | [arXiv:2507.15887](https://arxiv.org/abs/2507.15887) · [algotune.io](https://algotune.io/) |

**On venues: none of these has one.** Every upstream citation is a preprint or a
software record, not a peer-reviewed conference or journal paper — SEAGym is an
arXiv `@misc` (cs.AI, 2026), SkillOpt and AlgoTune are both `@article` entries
whose `journal` field reads *"arXiv preprint"*, and Harbor is an `@software`
record with a Zenodo concept DOI. Any claim that one appeared at NeurIPS, ICLR,
ICML or similar would not be supported by what these repositories state about
themselves. Cite them as preprints.

```bibtex
@misc{zheng2026seagym,
  title = {SEAGym: An Evaluation Environment for Self-Evolving LLM Agents},
  author = {Zheng, Congjie and Xue, Chuanyi and Liang, Bin and Yang, Jun and Zhang, Changshui},
  year = {2026}, eprint = {2606.17546}, archivePrefix = {arXiv}, primaryClass = {cs.AI}
}

@article{yang2026skillopt,
  title = {SkillOpt: Executive Strategy for Self-Evolving Agent Skills},
  author = {Yang, Yifan and Gong, Ziyang and Huang, Weiquan and others},
  journal = {arXiv preprint arXiv:2605.23904}, year = {2026}
}

@software{Harbor_Framework,
  author = {{Harbor Framework Team}},
  title = {{Harbor: A framework for evaluating and optimizing agents and models in container environments}},
  year = {2026}, doi = {10.5281/zenodo.20953922}
}

@article{press2025algotune,
  title = {AlgoTune: Can Language Models Speed Up General-Purpose Numerical Programs?},
  author = {Press, Ori and Amos, Brandon and Zhao, Haoyu and others},
  journal = {arXiv preprint arXiv:2507.15887}, year = {2025},
  doi = {10.48550/arXiv.2507.15887}
}
```

Harbor's own citation records `version = {v0.16.1}`; this checkout pins
**v0.22.0**, so cite the version actually used rather than the one in the
upstream snippet.

## Vendored dependencies

| Path | Upstream | Pinned at |
|---|---|---|
| `reference/seagym` | [antropy-research/SEAGym](https://github.com/antropy-research/SEAGym) | `9e61e14` (main) |
| `reference/skillopt` | [microsoft/SkillOpt](https://github.com/microsoft/SkillOpt) | `v0.2.0` (`e4ea6a6`) |

```bash
git submodule update --init --recursive
bash scripts/apply-vendor-patches
```

The nested `reference/ace/kayba-ai/ace-eval` submodule is private or removed
upstream. Its initialization failure is expected and does not affect this
SkillOpt/Holo integration.

### Vendor patches

A submodule records a commit SHA, not file contents, so an edit inside
`reference/` cannot be committed here and would be lost on a fresh clone.
Patches live in `patches/` and are re-applied after every `git submodule
update`. `scripts/apply-vendor-patches` is idempotent, and `--check` reports
what is missing without writing anything.

| Patch | Target | Why | Upstream |
|---|---|---|---|
| `seagym-redaction-usage-keys.patch` | `reference/seagym` | `redact_sensitive()` matches `TOKEN` as a substring, so token *counts* such as `total_tokens` were written to run records as `<redacted>` | [SEAGym#2](https://github.com/antropy-research/SEAGym/pull/2) |
| `seagym-final-resume-idempotence.patch` | `reference/seagym` | Resuming an already-complete final checkpoint appended duplicate final evaluation rows and changed metrics | local pending upstream proposal |
| `harbor-codex-atif-pricing-fallback.patch` | `reference/seagym/reference/harbor` | Codex could emit no ATIF cost fields when the pricing lookup had no entry for the configured model, losing target-side token accounting | local pending upstream proposal |

Patches span two submodules at different depths, so `apply-vendor-patches`
resolves each target path itself. It also checks that Harbor's egress sidecar
scripts are LF: `entrypoint.sh` and `bin/network-policy` run inside a Linux
container, and a CRLF checkout breaks the shebang before the task starts.

Retire a patch by moving the submodule pin to a commit that already contains
the fix, then deleting the file. `reference/seagym/reference/harbor` is pinned
at `v0.15.0-33`, which predates Daytona `allowed_hosts` support added in
v0.17.0 — see [docs/docker-harbor-runtime.md](docs/docker-harbor-runtime.md).

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

The synthetic canary configs and neutral initial skill are committed under
[`examples/holo_skillopt_matrix/`](examples/holo_skillopt_matrix/README.md).
They cover gated and static Codex/Claude runs, gate-off, and both transfer
directions with first-run concurrency fixed at one. The checked-in Harbor
packages are synthetic integration canaries with oracle solutions, not a
production benchmark. Trusted production repositories remain external.

## Commands

Every command below is run from the repository root. Substitute your own config
path for the deterministic example.

### Version requirements

The runtime preflight is the authoritative check, and it spends nothing — it
validates Docker and credential presence without calling a model:

```bash
python -m holoskill_gym.preflight --check-only --condition codex-gated --json
```

A ready environment reports **Docker reachable** and Harbor, SEAGym and SkillOpt
**resolving from the pinned checkout** rather than from unrelated global
installs:

| Component | Required | Currently verified |
|---|---|---|
| Docker Engine | daemon reachable over the socket | **29.5.2**, `status: ready` |
| Harbor | the revision this repo pins, not a global build | **0.22.0** |
| SEAGym | vendored submodule, editable | **0.1.0** |
| SkillOpt | `v0.2.0` exactly (`skillopt==0.2.0` in `pyproject.toml`) | **0.2.0** |
| Python | `>=3.12` | 3.12 in CI |

`ready: true` with an empty `failures` list is the gate to clear before a paid
run. Confirm the import path too — it must point inside this checkout:

```bash
python -c "import harbor; print(harbor.__file__)"   # .../reference/seagym/reference/harbor/...
```

**Editable installs report stale versions.** Harbor is installed editable, so
after a submodule bump the code executed is the new checkout while
`importlib.metadata.version("harbor")` still reports whatever was resolved at
install time. A venv that has not been re-synced since the v0.22.0 bump will say
`0.15.0` while running v0.22.0. That matters beyond cosmetics: the run manifest
records package versions from this metadata, so an un-synced venv writes the
wrong Harbor version into the provenance of a paid run. Re-sync before citing a
result:

```bash
uv sync --frozen --extra dev
git -C reference/seagym/reference/harbor describe --tags   # the truth
```

### Inspect before you run

`seagym inspect` has four subcommands and none of them execute a rollout, so
all four are safe without credentials.

```bash
seagym inspect config <config.json>    # load and validate a config
seagym inspect runtime <config.json>   # check runtime deps a config needs
seagym inspect run <run-dir>           # summarize a finished run
seagym inspect env                     # print runtime paths
```

Run `inspect config` then `inspect runtime` before any credentialed run. They
catch an unresolvable class path or a missing executor dependency before
Harbor capacity or Holo tokens are spent.

### Train

```bash
seagym train <config.json>
seagym train <config.json> --run-name my-run --output-dir results/runs
seagym train <config.json> --resume
seagym train <config.json> --resume-from-checkpoint epoch_0001
```

`--resume` picks up the latest checkpoint in the run directory;
`--resume-from-checkpoint` names one explicitly. Committed SkillOpt updates are
not repeated on resume — `StateStore` rejects a duplicate update index.

Completed-final resume is integration-tested: no update or metric-input row is
repeated, and state, deployed skill, metrics, and the summary report stay
byte-identical. Intermediate-checkpoint recovery remains a roadmap item.

### Evaluate a frozen checkpoint

```bash
# a named checkpoint from an earlier run, written to a fresh output directory
seagym eval --checkpoint <run-dir>/checkpoints/final <config.json>

# re-evaluate the newest checkpoint in place, reusing the same run directory
seagym eval --checkpoint latest --run-dir <run-dir> <config.json>
```

`--checkpoint` takes `latest`, a filesystem path, or a bare name. A **bare
name is resolved inside the run directory this eval creates**, not the run you
took the checkpoint from, so it only works alongside `--run-dir`. Pass the path
form when evaluating an earlier run — `--checkpoint final --run-dir <run-dir>`
fails with `FileExistsError` because anything other than `latest` resets the
run directory first.

`eval` measures a saved skill on the config's final views and **never calls
the updater** — no SkillOpt reflection, no Holo proposal, no gate. That is what
makes it the right tool for:

- **Cross-harness transfer** — evolve with Codex, then evaluate the frozen
  skill under `claude_code_exec` by pointing `eval` at a config whose rollout
  agent differs. The skill must not change during transfer evaluation.
- **`A_0` versus final** — `<run-dir>/checkpoints/initial` against
  `<run-dir>/checkpoints/final` on the same held-out view is the headline
  comparison.
- **Re-scoring** an old checkpoint against a view added later, without
  retraining.

A training run writes `initial`, `final`, per-epoch (`epoch_0001`) and
per-evaluation (`E_1`, `E_2`) checkpoints; list them with
`ls <run-dir>/checkpoints/`.

Verified on the deterministic example: an eval run writes only `checkpoint_eval`
mode records, no `agent_updates.jsonl`, and zero `agent_update` rows.

Do not use `eval` for routine validation during training — the trainer already
runs update-validation, replay and final views itself.

An integration test replaces baseline update, SkillOpt reflection, and Holo
proposal generation with fail-fast sentinels, then runs checkpoint eval. The
eval completes with only `checkpoint_eval` records and no update artifact.

### Harbor tasks

Harbor owns checkout, isolation, CLI execution and timeouts. These commands
operate on a task package directly, outside SEAGym, and are how you develop or
debug a task before wiring it into a config.

```bash
harbor init --task "<org>/<name>"                 # scaffold a task package
harbor run -p <path/to/task> -a <agent> -m <model>  # run one task
```

Pre-populate defaults for a new task from a shared TOML template so a family of
tasks does not drift apart:

```bash
harbor tasks init "<task-name>" --metadata-template task-template.toml
```

### Running a registry dataset

Harbor ships a registry of **80 third-party benchmark datasets**, addressed as
`name@version` rather than by path. Harbor is built by the creators of
[Terminal-Bench](https://www.tbench.ai) and is the official harness for
Terminal-Bench 2.0, which is why the registry is dominated by agent benchmarks
adapted to a common task format.

```bash
harbor datasets list                                  # everything in the registry
harbor run --dataset algotune@1.0 -a oracle -y        # credential-free, applies reference solutions
harbor run --dataset algotune@1.0   --agent codex --model gpt-5.6-sol   --n-concurrent 1                                    # spends OPENAI_API_KEY
```

Start with `-a oracle` on a single task, exactly as with a local task package:
it proves the image builds and the verifier scores without spending a token.

**AlgoTune** (`algotune@1.0`) is the registry dataset closest to this project's
own objective: **154 algorithm-optimization tasks** where the goal is to beat a
reference implementation while producing identical output
([paper](https://arxiv.org/abs/2507.15887), [site](https://algotune.io/)).
Domains span linear algebra, signal processing, cryptography, graph algorithms,
optimization and scientific computing.

Its headline metric is the **AlgoTune Score — the harmonic mean of per-task
speedups**, with a "mercy score" of 1.0 for a solution that fails validation or
runs slower than baseline. That is *not* this project's
`correct_speedup_geomean`. The harmonic mean is dominated by its smallest
values, so it rewards broad improvement and punishes a single unimproved task
far harder than a geometric mean does. Compare the two with:

```bash
python -m holoskill_gym.score --run-dir results/runs/<run>          # both, plus ratio
python -m holoskill_gym.score --speedups 1.05 1.02 8.0 --statistic harmonic
python -m holoskill_gym.score --run-dir results/runs/<run> --view id_test --json
```

Both statistics are computed from the same speedups, and their **ratio H/G** is
the useful number: the harmonic mean is dominated by its *smallest* values while
the geometric mean is not, so the gap between them measures how evenly the gain
is spread.

| Speedups | Harmonic (H) | Geometric (G) | H/G | Reading |
|---|---:|---:|---:|---|
| 2.1, 2.3, 2.0, 2.2 | 2.14 | 2.15 | **0.999** | Broad — every task improved. |
| 1.05, 1.02, 8.0, 1.01 | 1.31 | 1.72 | **0.765** | Concentrated — one task carries the result. |
| 1.0, 1.0, 1.0, 1.0 | 1.00 | 1.00 | **1.000** | No change anywhere. |

Both of the first two rows could honestly be reported as "a solid speedup", and
only the second is misleading. **H/G near 1.0 means the win is real across the
set; well below 1.0 means one or two tasks are doing the work** and the skill
probably did not generalize — which is exactly the claim a skill-evolution run
is trying to make. `holoskill_gym.score` prints the ratio and warns below 0.9.

This is also why a spurious zero is more damaging under the harmonic mean: one
task scoring 0 sends the harmonic mean to 0 outright, while the geometric mean
merely drops. See the memory note below for how a zero can arrive without any
error being raised.

**Resources.** Every AlgoTune task declares `cpus = 8`, `memory = "16G"`, and a
3600 s agent and verifier timeout. **None of the 154 requires a GPU**, so no GPU
provider or extra credentials are needed. Some other registry benchmarks do —
`rexbench` declares GPUs in its task template, and `deveval`, `featurebench`,
`ml-dev-bench`, `mlgym-bench`, `researchcodebench` and `scienceagentbench`
document GPU requirements — so check before selecting one of those.

The full list of the 154 tasks, with problem sizes, is in
[docs/algotune-tasks.md](docs/algotune-tasks.md); the other 79 registry datasets
are in [docs/harbor-registry-datasets.md](docs/harbor-registry-datasets.md).

**Terminal-Bench 2.0** (`terminal-bench@2.0`, 89 tasks) runs with no adapter,
since Harbor is its official harness — 4 easy, 55 medium, 30 hard, no GPUs; see
[docs/terminal-bench-2-tasks.md](docs/terminal-bench-2-tasks.md). It is a
**general agent benchmark, not a code-optimization one**: its tasks are pass/fail
against their own verifiers and carry no before/after measurement, so they
produce no `speedup` and neither `correct_speedup_geomean` nor `algotune_score`
is defined over them. Useful here as a broad harness smoke test — it exercises
image build, network policy and verifier plumbing across far more varied
environments than the five synthetic canaries — but not as a task source for
skill evolution.

##### The ML-workload benchmarks

Three more registry datasets come up because they mention GPUs. None is a good
fit for skill evolution here, and the reasons differ:

| Dataset | Tasks | What it measures | Why it does not fit |
|---|---:|---|---|
| `mlgym-bench@1.0` | 12 (11 surfaced) | Training ML models from scratch — CV, RL, tabular, game theory | Continuous score, but the objective is *model quality*, not code speed. Computationally heavy; CC-BY-NC-4.0, so **non-commercial research only**. |
| `ml-dev-bench@1.0` | 33 | Real-world ML development workflows — dataset handling, debugging, finetuning | Workflow completion, not a measured before/after. |
| `rexbench@1.0` | 2 | Extending a research paper's codebase | Only 2 tasks public. Needs an **A100 40 GB**; oracle verification alone takes ~2.5 h for `cogs`, ~45 min for `othello`. |

All three are addressable by `--dataset`, so nothing needs installing — but all
three need a GPU-capable provider, and none produces the correctness-gated
speedup this project's reward is defined over. `rexbench` in particular is
poorly matched: two tasks cannot support a train/test split, and an A100 for
hours per trial is a different cost class from anything here.

**`scienceagentbench` is a different case: it is not in the registry at all.**
The Harbor tree vendors 87 adapters but the registry publishes 80 datasets, and
this is one of the gap entries — the adapter exists (`adapters/scienceagentbench/`
with `adapter.py`, `classify_tasks.py`, `llm_visual_judge.py`) but no dataset was
published from it. So `--dataset scienceagentbench@...` cannot resolve.

**You do not need to install it.** Doing so would mean running the adapter
yourself to generate task packages from the upstream benchmark, then vendoring
the output — real work, for a benchmark that scores scientific-analysis output
via an LLM visual judge rather than a measured speedup. That reward is neither
comparable to this project's nor reproducible in the way a benchmark harness
needs. AlgoTune remains the right candidate.

#### What a rollout costs, and how to estimate a run

Measured phase timings from AlgoTune runs on this machine. The point of the
table is that **the model is a minority of the wall time**:

| Phase | Oracle (base64) | Oracle (convolve2d) | Codex, paid (convolve2d) |
|---|---:|---:|---:|
| Environment setup (image build) | 10.7 m | 2.8 m | 2.1 m |
| Agent setup (Codex CLI install) | — | — | **3.3 m** |
| Agent execution | — | — | 2.4 m |
| Verifier (100 instances x 10 reps) | 0.7 m | 7.1 m | 3.3 m |
| **Total** | **11.4 m** | **9.9 m** | **11.2 m** |

Only ~2.4 of ~11 minutes is the agent working — roughly **20%**. The rest is
image build, installing the Codex CLI inside each fresh container, and
AlgoTune's interleaved timing protocol. Environment setup varies most: 10.7 m
for a first-ever build against 2.1 m once Docker's layers are warm. The verifier
varies by task, 0.7 m to 7.1 m.

**Estimating a gated run.** Rollouts, not tasks, are the unit — the private gate
scores both the current and the proposed skill on every gate task, so each gate
task costs two rollouts:

```text
rollouts = train + validation + test + (2 x gate tasks)
```

The canary config (1 train, 1 validation, 1 test, 2 gate tasks) is 5 distinct
tasks but **7 rollouts**, of which the gate is 4 — 57% of the run. At ~11-14 min
each, sequential under `n_concurrent: 1`, that is **~1.5-2.5 hours**.

Two levers if that is too slow. Pre-baking the Codex CLI into the task image
removes 3.3 m per rollout — ~23 minutes over seven, a fifth of the run, and it
also removes seven chances to hit the nvm/TLS flake that has already failed one
job here. Dropping to one gate task takes 7 rollouts to 5. Raising
`n_concurrent` is the tempting third option and the one to avoid: tasks declare
8 CPUs and 16 GB against a smaller ceiling, so parallelism buys another silent
OOM zero.

#### Pre-pull the base images before a paid run

Every image a run needs is pulled on demand, during the run. That is fine until
the pull fails partway through — a gated AlgoTune canary here lost 4 of its 5
task runs to a transient Docker credential-helper failure:

```text
#3 [internal] load metadata for docker.io/library/python:3.12-slim
#3 ERROR: error getting credentials - err: exit status 1
failed to solve: error getting credentials
```

Nothing was wrong with the code. The first rollout, which had already built its
image, scored 1.0; everything after it died at the `FROM` line. Pulling the
bases first turns that class of failure into a fast, free error before any
tokens are spent.

The image surface is small. **Both** the 154 AlgoTune tasks and the five
checked-in `holoskill-codeopt-v1` tasks build from the same base:

```bash
docker pull python:3.12-slim      # all 154 AlgoTune + all 5 checked-in tasks

# Only needed when a task phase uses network_mode = "allowlist", which builds
# Harbor's egress-control sidecar. The checked-in codeopt tasks do; AlgoTune
# tasks declare no per-phase policy and so do not.
docker pull gogost/gost:3.2.7-nightly.20260602

docker images | grep -E "python:3.12-slim|harbor-prebuilt"   # confirm
```

The sidecar is *built*, not pulled — it appears locally as
`harbor-prebuilt:harbor-docker-egress-control-sidecar--<hash>` and is
content-addressed, so a rebuilt image cannot go stale. Only its `gogost/gost`
base comes off the network.

The Codex agent itself is **not** a Docker pull. Harbor installs the CLI inside
each container over nvm/npm, which is why `agent_setup` costs ~3.3 min per
rollout and why a run can still fail on a network hiccup even with every image
cached — one job here died on
`fatal: unable to access 'https://github.com/nvm-sh/nvm.git/': GnuTLS, handshake
failed`. Pre-pulling does not protect against that; baking the CLI into the task
image would.

#### Check the memory ceiling before running a registry task

A task's `[environment]` block is a *declaration of need*, not a reservation.
Harbor will start the container anyway, and the shortfall surfaces during
verification, when peak memory is highest.

```bash
wsl -e bash -lc "docker info | grep -E 'Total Memory|CPUs'"   # what Docker can actually give
grep -E '^(cpus|memory)' <task>/task.toml                     # what the task asks for
```

On this machine Docker exposes **7.6 GiB and 16 CPUs**, so an AlgoTune task's
`cpus = 8` fits while its `memory = "16G"` cannot — roughly half of what the
task was calibrated against.

**The failure mode is quiet, which is the dangerous part.** An oracle run of
`algotune-base64-encoding` finished with `n_errored_trials: 0`,
`exception_info: null`, and `reward: 0.0`. The verifier ran for 41 s and
returned — it did not time out, and nothing raised. The cause is in
`verifier/test-stdout.txt`:

```text
../tests/test_outputs.py ./tests/test.sh: line 17:    62 Killed   pytest /tests/test_outputs.py -rA -s
```

`Killed` is the shell reporting SIGKILL, which inside a container means the OOM
killer. Three things then combine to turn a crash into a plausible-looking
score:

1. `test.sh` writes `echo 0 > /logs/verifier/reward.txt` **before** running
   anything, as a default.
2. The performance test is wrapped in `set +e`, so the kill does not abort the
   script.
3. Nothing ever overwrites the default, so Harbor reads a well-formed reward of
   `0`.

**The zero is not produced by the failure — it is the pre-seeded default that
never got replaced.**

The memory arithmetic explains the kill. `algotune-base64-encoding` declares
`algotune_problem_size = 49152`, and the solver's
`DEFAULT_PLAINTEXT_MULTIPLIER` is 2048, so one problem instance is
49,152 x 2,048 = 96 MiB of plaintext plus a 128 MiB Base64 copy — 224 MiB
resident per instance. AlgoTune's protocol generates **100 instances per task**:

| Instances resident | Memory |
|---:|---:|
| 1 | 0.2 GiB |
| 10 | 2.2 GiB |
| 100 | **21.9 GiB** |

against a 7.6 GiB ceiling. The problem size was calibrated on a machine with the
declared 16 GB; it is not survivable on half that.

Treat an oracle scoring 0.0 as an infrastructure failure until proven otherwise.
The oracle applies the reference solution, so it should score well by
construction — and under a harmonic mean a single spurious zero drags the whole
aggregate down far harder than under a geometric mean.

Mitigations, in order of preference:

1. **Raise the Docker VM's memory.** On Windows, set `memory=16GB` in
   `%UserProfile%\.wslconfig` and run `wsl --shutdown`.
2. **Pick a smaller task.** Problem sizes span 1 to 6,291,456; the small end
   isolates verifier memory from cold-build behaviour and is the right choice
   for a first smoke test.
3. **Run on a provider with the headroom** rather than locally — though note the
   Daytona caveat about egress under the current Harbor pin.

Harbor also publishes a task-authoring skill for coding agents:

```bash
npx skills add harbor-framework/harbor --skill create-task
```

Layout, `task.toml` fields, network policy and reward output are documented in
[docs/harbor-task-structure.md](docs/harbor-task-structure.md).

#### The checked-in task set

`data/holoskill-codeopt-v1` holds five tasks. Each targets one bottleneck family
on a single hot path, and every one is marked `benchmark_trust =
"synthetic_canary"` — they exist to exercise the pipeline end to end, **not** to
measure a skill's real quality.

| Task | Split | Bottleneck family | Metric | Direction | Difficulty |
|---|---|---|---|---|---|
| `codeopt-train-001` | train | prefix-caching | `encode_throughput_units` | maximize | medium |
| `codeopt-train-002` | train | async-batching | `scoring_throughput_units` | maximize | medium |
| `codeopt-val-001` | val | redundant-serialization | `serialize_latency_units` | minimize | hard |
| `codeopt-test-001` | test | concurrency-locking | `read_latency_units` | minimize | hard |
| `codeopt-gate-001` | **private gate** | allocation | `buffer_latency_units` | minimize | medium |

All five run credential-free under the `oracle` agent, which applies the
reference solution — that is what the `harbor-oracle` CI matrix does on every
push, proving each image builds, tests run, the benchmark measures and the
verifier writes a reward without spending a token.

**Note the limitation.** Five tasks means five *distinct* families, so no family
recurs between train and test. Nothing here tests whether a skill generalizes
within a family, which is the property the whole method depends on — a trusted
external task set needs several independent repositories per family, with test
repositories disjoint from train.

### Execution controls and network policy

`CliCodeOptRolloutAgent` executes nothing itself — Harbor owns checkout,
sandboxing, CLI invocation and timeouts. What the rollout config controls is
*how* the built-in Harbor agent is allowed to run, and those settings split into
two layers that behave very differently.

**Executor controls** are forwarded to the Harbor agent as `kwargs`. They shape
the model: `reasoning_effort`, and for Claude Code also `allowed_tools`,
`disallowed_tools`, `permission_mode`, `max_thinking_tokens`, `max_budget_usd`.
The accepted set is per executor, because Codex and Claude Code expose different
knobs. Getting one wrong costs tokens.

**Execution controls** are never handed to the agent. They are applied to the
SEAGym environment or asserted against the task package before the rollout
starts, and they are the containment boundary. Getting one wrong lets an agent
reach the network during grading, or lets raw provider transcripts land in a run
directory.

| Execution control | Effect |
|---|---|
| `agent_timeout_seconds` | Overrides `backend.agent_override_timeout_sec` for this rollout. |
| `verifier_timeout_seconds` | Overrides `backend.verifier_override_timeout_sec`. |
| `max_steps` | Agent step budget. Claude Code only — see below. |
| `agent_network_mode` | Asserted against `[agent].network_mode` in `task.toml`. |
| `verifier_network_mode` | Asserted against `[verifier].network_mode`. |
| `raw_log_retention` | `"none"` adds Harbor `--agent-exclude-logs` / `--verifier-exclude-logs` patterns so raw transcripts stay out of the run directory. |

#### Network policy is asserted, never set

This is the part worth being precise about. `agent_network_mode` and
`verifier_network_mode` do **not** configure Harbor. The task package's
`task.toml` is the single source of truth for network policy; the rollout config
only states what it believes that policy to be, and the run is refused when the
two disagree.

The consequence: **a SEAGym config can never widen a task's egress.** The only
thing it can do is fail closed. Four cases are rejected before any container
starts:

1. **An unknown mode.** Only `no-network`, `allowlist` and `public` are accepted.
2. **A declared/actual mismatch.** Config asks for `no-network` on the verifier
   but the task says `allowlist` — rejected. The converse is rejected too: a task
   *stricter* than the config asked for still means the run manifest would
   misdescribe the conditions, and silent divergence in either direction
   invalidates the result.
3. **A missing declaration.** A task that omits `[agent].network_mode` or
   `[verifier].network_mode` reads back as null, which never matches a requested
   mode. An undeclared phase is rejected rather than inheriting the
   `[environment]` baseline — whose effective default is `public`, which is
   exactly the case where a silent inherit would do the most damage.
4. **An uninspectable task.** No `local_path` and no `dataset_path` + `task_name`
   pair means the policy cannot be read at all. An unreadable or malformed
   `task.toml` is treated the same way: an unverifiable policy is a failed policy.

`[environment].network_mode` is deliberately *not* asserted. It governs image
build and container start, and task builds legitimately need `apt-get` and `pip`
egress. What this guard protects is grading containment — that the verifier phase
cannot reach the network, and that the agent phase reaches only what the task
declared.

The matrix configs all pair `"agent_network_mode": "allowlist"` with
`"verifier_network_mode": "no-network"`, matching the checked-in tasks, whose
`[agent].allowed_hosts` is limited to the model endpoints.

#### `max_steps` and `max_turns`

`max_steps` is this project's executor-neutral name for the agent step budget.
Claude Code's Harbor agent spells the same limit `max_turns`, so the rollout
agent bridges them: setting `max_steps` populates `max_turns`, and setting both
to different values is a configuration error rather than a silent
last-writer-wins.

**`max_steps` is rejected for `codex_exec`.** At the Harbor revision pinned
through SEAGym, the Codex agent exposes no step or turn cap, so accepting the key
would advertise a budget that nothing enforces. This is why the `claude_*`
configs carry `"max_steps": 50` and the `codex_*` configs carry none — the
asymmetry is deliberate, not an oversight. Codex runs are bounded by
`agent_timeout_seconds` instead.

#### Credential isolation

`from_config` also refuses to start when any of `HAI_API_KEY`, `HOLO_BASE_URL`
or `HOLO_OPTIMIZER_MODEL` would be exported into a target rollout. SkillOpt
drives the optimizer on the host; the target agent runs in Harbor's sandbox with
only its own provider key. Overlap is fatal rather than warned about, because it
would let the target read or bill the optimizer role and destroy the
`role_separated_spend` accounting.

All of the above is implemented and commented in
[`holoskill_gym/rollout_agent.py`](holoskill_gym/rollout_agent.py).

### Docker runtime for Harbor tasks

Harbor talks to the Docker Engine API over a socket and builds each task's own
image, so the process running it needs socket access and build permission.
Verify before a first run:

```bash
wsl -e bash -lc "docker version --format '{{.Server.Version}}'"   # daemon reachable in WSL
wsl -e bash -lc "ls -l /var/run/docker.sock"                      # srw-rw---- root docker
wsl -e bash -lc "id -nG | tr ' ' '
' | grep -x docker"           # you are in the group
```

If the daemon answers on Windows but not in WSL, enable this distro under
Docker Desktop → **Settings → Resources → WSL integration**, then **Apply &
restart**. If the socket is there but denied, add yourself to the group and
restart the distro — never reach for `sudo harbor`, which leaves job artifacts
your user cannot read:

```bash
sudo usermod -aG docker "$USER" && wsl --shutdown
```

Network policy is per phase. Task builds need egress for `apt-get` and `pip`,
the agent phase needs its model provider, and verification runs with
`no-network` so grading cannot depend on anything remote. Any `allowlist` phase
makes Harbor build an egress-control sidecar on first use, which is why an
initial run appears to pause shortly after starting.

Build and run the first repaired task through Docker Desktop using the oracle
agent, which applies the reference solution and needs no model credentials:

```bash
.venv-linux/bin/harbor run   -p data/holoskill-codeopt-v1/observer/codeopt-train-001   -e docker   -a oracle   --n-concurrent 1   -y
```

Start with `oracle`: it proves the image builds, tests run, the benchmark
measures and the verifier writes a reward, without spending a token. Swap in
`-a codex -m gpt-5.6-sol` with `OPENAI_API_KEY` set once it passes. Results land
in `jobs/<timestamp>/<task>__<id>/`; read `trial.log` first when a run fails.

Full setup, network-phase configuration and troubleshooting:
[docs/docker-harbor-runtime.md](docs/docker-harbor-runtime.md).

### Multi-step Harbor tasks

A multi-step task runs an ordered sequence of steps in one persistent
environment, declared as `[[steps]]` entries in `task.toml`.

```bash
harbor run -t <path/to/multi-step-task> -a claude-code -m <model>
harbor run -t <path/to/multi-step-task> -a claude-code -m <model> --resume-trajectory
```

By default every step starts a fresh agent conversation even though the
environment persists. `--resume-trajectory` continues the agent's native
session so each step arrives as a follow-up. It is a run setting, not a task
field, and an agent lacking the `capabilities.resume` capability fails before
step 1 rather than silently getting fresh sessions.

Multi-step is **not yet supported** by the Verifiers v1 Harbor adapter, so it
is not reachable from a SEAGym config today. See
[docs/harbor-multi-step-tasks.md](docs/harbor-multi-step-tasks.md).

### Storing runs and solutions

`jobs/` and `results/` are gitignored and Harbor rewrites them per run, so a
paid run's evidence is unrecoverable once the directory is cleaned. Two homes,
by kind of data:

- **Source belongs in git.** A solution worth keeping goes under `solutions/<task>/`
  with a `PROVENANCE.md` recording job, trial, model, reward, token counts and
  the `source_sha256`.
- **Metrics belong in a database.** `db/schema.sql` defines `tasks`, `runs`,
  `metrics` and `solutions` plus two views — `solution_leaderboard` and
  `agent_vs_oracle`, the latter being the comparison that says whether an agent
  beat the reference implementation and by how much.

```bash
docker run -d --name holoskill-pg   -e POSTGRES_USER=holoskill -e POSTGRES_PASSWORD=holoskill_local_dev   -e POSTGRES_DB=holoskill -p 5432:5432   -v holoskill-pgdata:/var/lib/postgresql/data --memory=512m postgres:17-alpine

docker exec -i holoskill-pg psql -U holoskill -d holoskill < db/schema.sql
scripts/ingest-run jobs/<job-name>              # parses reward, timings, solver source
scripts/ingest-run jobs/<job-name> --dry-run    # inspect without a database
```

`ingest-run` reads a Harbor job directory and extracts the durable facts. It
deliberately does **not** write complexity fields: nothing can derive a bound
from source automatically, so `time_complexity`, `space_complexity` and
`complexity_notes` are human annotations added afterwards and should be read as
documentation that can be wrong.

The database is local and its password is a development placeholder — it holds
run metadata and agent-authored source, not credentials, and `scan-artifacts`
still governs what may leave the machine.

### Checking CI status

`gh` is the tool for this; it is already installed and authenticated here.

```bash
gh run list --limit 5              # recent runs, with status and branch
gh run watch                       # live-follow the in-flight run
gh run view <id> --log-failed      # only the failing step's log, not the whole run
```

`gh run watch` blocks until the run finishes and **exits non-zero if it failed**,
so it composes into a script or a `&&` chain rather than needing to be read by a
human. `--log-failed` is the one to reach for first on a red run: it skips
straight to the failing step instead of paging through a passing job's output.

### Maintenance

```bash
bash scripts/apply-vendor-patches          # re-apply vendor patches
bash scripts/apply-vendor-patches --check  # report without writing; exits 1 if missing
python -m pytest -q                        # project test suite
python -m ruff check holoskill_gym tests
python -m ruff format --check holoskill_gym tests
python -m holoskill_gym.preflight --check-only --condition codex-static
python -m holoskill_gym.preflight --optimizer --structured   # spends HAI_API_KEY
scripts/scan-artifacts results/ jobs/
```

`--check-only` never calls a model and reports only credential presence.
`--optimizer --structured` sends one structured request and spends optimizer
tokens.


The production-path canary role split is configured like this (task and split paths
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

`holo3-1-35b-a3b` is the only **Holo** model used by this integration, and
`HoloBackendConfig` rejects other Holo IDs. It is not the only optimizer:
`optimizer_backend` selects between `holo_openai_compatible` and `openrouter`,
which are alternatives filling the same role behind the `ProposalBackend`
protocol. The OpenRouter adapter's parameters and model options are documented
in [docs/openrouter-inkling.md](docs/openrouter-inkling.md); it is proven on
`openai/gpt-5.6-luna` and rejects models that cannot satisfy the schema at
configuration time. Holo supports both reasoning and tool calls. For the
skill-mutation request specifically, the optimizer uses strict
`SkillUpdateProposal` JSON output followed by local semantic validation. This
keeps mutation deterministic and auditable; it is not a workaround for another
Holo model. Tool calling remains available to separate 35B workflows that need
tools. Codex/GPT-5.6-sol continues to own the target coding-agent rollouts
through Harbor.

### Credentials by run type

What each run actually needs. The optimizer and target roles are billed
separately and reported separately, so a gated run needs one credential per
role rather than one shared key.

| Run | Required credential | Provider |
|---|---|---|
| Codex static / target-only | `OPENAI_API_KEY` | OpenAI Platform |
| Codex + SkillOpt gated canary | `OPENAI_API_KEY` + `HAI_API_KEY` | OpenAI + H Company |
| Codex gate-off ablation | `OPENAI_API_KEY` + `HAI_API_KEY` | OpenAI + H Company |
| Claude static — deferred | `ANTHROPIC_API_KEY` | Anthropic |
| Claude + SkillOpt — deferred | `ANTHROPIC_API_KEY` + `HAI_API_KEY` | Anthropic + H Company |
| Codex → Claude transfer evaluation | `ANTHROPIC_API_KEY` | Anthropic |
| Claude → Codex transfer evaluation | `OPENAI_API_KEY` | OpenAI |
| Docker oracle, CI, unit tests | none | — |
| Future OpenAI Agents SDK adapter | `OPENAI_API_KEY` | OpenAI |

Three things follow from the shape of this table.

**Start at the bottom.** The Docker oracle, CI and unit tests need nothing, so
every structural failure — image build, verifier, reward emission, edit policy
— is reachable before a single token is spent. A task that fails under `-a
oracle` would fail under a real agent too, and cost money to discover it.

**A transfer evaluation needs only the target's credential**, not the
optimizer's. It replays a frozen skill under a different harness and never
calls the updater, so `HAI_API_KEY` is absent from both transfer rows by
design; needing it would mean the run was not read-only.

**`HAI_API_KEY` appears only where the gate runs.** It pays for optimizer
proposals, while the executor key pays for target rollouts. `separate_costs()`
keeps the two apart in reports and `CliCodeOptRolloutAgent` refuses to export
optimizer-only variables into a target sandbox, so the split is enforced rather
than merely documented.

Selecting `optimizer_backend: "openrouter"` substitutes `OPENROUTER_API_KEY`
for `HAI_API_KEY` in the optimizer role; every target-side requirement is
unchanged.

### Strict proposal-schema policy options

The current schema is intentionally small: diagnosis, bounded
add/delete/replace edits, expected effects, and risks. There are several safe
ways to make it stricter without weakening local validation:

1. **Dynamic enums (recommended next step).** Generate the request schema per
   training batch so `evidence_ids` can only contain IDs in that batch and
   `section` can only name headings in the current skill. Keep the same checks
   after parsing because schema compliance does not prove an edit is legal.
2. **Discriminated edit variants.** Replace nullable `old_text`/`new_text`
   combinations with separate `AddEdit`, `DeleteEdit`, and `ReplaceEdit`
   objects selected by the `operation` discriminator. This makes invalid field
   combinations unrepresentable in model output.
3. **Explicit no-op envelope.** Add a top-level `decision` of `edit` or `noop`.
   Require an empty edit list and a concise explanation for `noop`; require at
   least one edit for `edit`. This separates intentional abstention from a
   malformed empty proposal.
4. **Schema-level size bounds.** Add `maxItems`, string-length limits, and
   bounded rationale/effect/risk counts. Local token, character, edit-count,
   exact-match, leakage, and forbidden-content checks still remain mandatory.
5. **Two-phase tool-assisted proposal.** Allow 35B tools only in a separate,
   read-only evidence-gathering call, normalize its outputs into bounded
   evidence, then make a second call with tools disabled and strict
   `json_schema`. Never combine side-effecting tools with the mutation response.
6. **Versioned proposal envelope.** Add a schema version and policy-profile ID
   so historical proposals remain replayable when constraints evolve. Reject
   unknown versions and profiles rather than guessing compatibility.

The recommended progression is dynamic enums plus discriminated edit variants,
then an explicit no-op envelope. Native tool calls should remain a separate
evidence phase rather than becoming an alternative patch format.

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

Three serialization constraints are non-negotiable:

- ATIF's `extra` dictionaries are the only extension point for
  SEAGym/HoloSkill Gym data because the root schema forbids unknown fields.
- `reasoning_content` stays null; hidden Holo reasoning is never requested or
  persisted.
- Target and optimizer cost/usage remain separate; ATIF final metrics describe
  the target rollout, while optimizer accounting is namespaced method state.

Store bounded summaries and local artifact paths in `extra`, not complete
provider logs or transcripts.

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
SkillOpt is required for one gated Codex canary and becomes an optional adapter
afterward; the rationale and OpenAI Agents SDK follow-up are in
[the SkillOpt decision](docs/skillopt-decision.md).

## Computer-use agent models

The H Models API serves the 35B vision-language model used here for reasoning
and tool-capable workflows. The values below are read from `GET /v1/models`,
not copied from documentation, so they reflect what this account is actually
served.

| Model | Context | Max output | Features | Input / M | Output / M | Free tier |
|---|---|---|---|---|---|---|
| `holo3-1-35b-a3b` | 65,537 | 4,096 | reasoning, tools | $0.25 | $1.80 | yes, 10 req/min |

The model takes text and image input and returns text. There is no per-request
fee; cost is token-based only.

Two consequences are worth knowing before configuring a run:

- `HOLO_OPTIMIZER_MODEL` must remain `holo3-1-35b-a3b` whenever the Holo
  backend is selected; configuration rejects other Holo model IDs rather than
  silently changing model behavior. Selecting a different *optimizer* is done
  with `optimizer_backend`, not by changing this variable.
- The model emits a reasoning preamble that counts against `max_tokens`.
  Budget at least ~256 completion tokens or the answer is cut off before it
  starts.

Listing is not access. Only a real completion proves that a configured key can
use the model.

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

`scripts/holo` is intentionally broader than the SkillOpt mutation adapter. It
remains a general-purpose H Models client and retains its 122B aliases; choosing
one there does not change or bypass the 35B-only optimizer policy.

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
