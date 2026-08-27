# Production experiment matrix

These configs define the gated Codex and Claude Code conditions, both frozen
static controls, the Codex gate-off ablation, and the two frozen-skill
cross-harness transfer directions. Every Harbor backend keeps
`n_concurrent: 1` for the first production run.

The configs intentionally do not fabricate benchmark packages. Before running
them, provision the trusted Harbor dataset at
`data/holoskill-codeopt-v1/{observer,private_gate}` with task directories whose
names match `tasks/task_index.json` and `tasks/skillopt_gate.json`. Runtime
inspection should report those missing paths until that external prerequisite
is present.

Run gated/static experiments with `seagym train`. Transfer configs are
read-only and must be invoked with `seagym eval --checkpoint` using the final
checkpoint from the named source harness. Their transfer delta is target-harness
checkpoint score minus the source run's `A_T` score for each matching view.
The source `metric_inputs.jsonl` path is explicit and its SHA-256 is written to
the metric result. A missing source run reports `applicable: false` rather than
inventing a comparison.

No low-cost ablation is included: the optimizer policy is 35B-only, so that row
would be identical to the primary condition.
