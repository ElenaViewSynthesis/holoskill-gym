# Harbor

Harbor is a framework from the creators of Terminal-Bench for evaluating and
optimizing agents and language models. You can use Harbor to:

- Evaluate arbitrary agents like Claude Code, OpenHands, Codex CLI, and more.
- Build and share your own benchmarks and environments.
- Conduct experiments in thousands of environments in parallel through
  providers like Daytona, Modal, LangSmith, Blaxel, Novita Sandbox, and
  Tensorlake.
- Generate rollouts for RL optimization.

Check out the Harbor Cookbook for end-to-end examples and guides.

Related references:

- [Harbor task and agentic-environment structure](harbor-task-structure.md)
- [Harbor multi-step tasks](harbor-multi-step-tasks.md)
- [Verifiers v1 — Harbor integration](verifiers-v1-harbor.md)
- [Agents and executor bindings](../agents.md)

## Installation

```bash
uv tool install harbor
```

or

```bash
pip install harbor
```

## Example: Running Terminal-Bench-2.0

Harbor is the official harness for Terminal-Bench-2.0:

```bash
export ANTHROPIC_API_KEY=<YOUR-KEY>
harbor run --dataset terminal-bench@2.0 \
   --agent claude-code \
   --model anthropic/claude-opus-4-1 \
   --n-concurrent 4
```

This will launch the benchmark locally using Docker. To run it on a cloud
provider (like Daytona) pass the `--env` flag as below:

```bash
export ANTHROPIC_API_KEY=<YOUR-KEY>
export DAYTONA_API_KEY=<YOUR-KEY>
harbor run --dataset terminal-bench@2.0 \
   --agent claude-code \
   --model anthropic/claude-opus-4-1 \
   --n-concurrent 100 \
   --env daytona
```

To see all supported agents, and other options run:

```bash
harbor run --help
```

To explore all supported third party benchmarks (like SWE-Bench and Aider
Polyglot) run:

```bash
harbor datasets list
```

To evaluate an agent and model on one of these datasets, you can use the
following command:

```bash
harbor run -d "<dataset@version>" -m "<model>" -a "<agent>"
```

## Notes against the pinned checkout

Verified against the Harbor vendored at
`reference/seagym/reference/harbor`:

- `dataset` is the canonical subcommand name; `datasets` is registered as a
  hidden alias, so both `harbor dataset list` and `harbor datasets list` work.
- `--dataset`, `--agent`, `--model`, `--n-concurrent` and `--env` all exist,
  as do the `-d`, `-a`, `-m` and `-n` short forms.
- Every cloud provider named above ships a backend module under
  `src/harbor/environments/`: `daytona/`, `modal.py`, `langsmith.py`,
  `blaxel.py`, `novita.py`, `tensorlake.py`. Others are present too, including
  `docker/`, `e2b.py`, `ec2.py` and `gke.py`.

## How HoloSkill Gym uses Harbor

This project does not call `harbor run` during an experiment. SEAGym owns the
loop and reaches Harbor through `CliCodeOptRolloutAgent`, which selects a
built-in Harbor agent (`codex` or `claude-code`) and lets Harbor own checkout,
isolation, CLI execution, timeouts, network policy and ATIF production. See
[agents.md](../agents.md).

`harbor run` is still the right tool for **developing and debugging a task
package** before wiring it into a SEAGym config:

```bash
harbor run -p data/holoskill-codeopt-v1/observer/codeopt-train-001 \
   -a codex \
   -m gpt-5.6-sol
```

The backend and concurrency a SEAGym run uses are set in its config rather than
on the command line:

```json
{"backend": {"name": "harbor", "env": "docker", "n_concurrent": 1}}
```

`env` accepts the same provider names as `--env`. Keep `n_concurrent` at 1 for
a first production run.
