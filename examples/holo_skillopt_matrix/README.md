# Synthetic canary matrix

These configs define the gated Codex and Claude Code conditions, frozen static
controls, the Codex gate-off ablation, and two frozen-skill cross-harness
transfer directions. Every Harbor backend keeps `n_concurrent: 1` for the
first production-path canary.

The checked-in Harbor packages under `data/holoskill-codeopt-v1/` are small,
synthetic, single-module tasks with included oracle solutions. They validate
Docker, executor, verifier, network-policy, checkpoint, and gate integration;
they are not a production benchmark and must not support production-quality or
model-ranking claims. Trusted production repositories remain external.

The immediate sequence is one Codex static canary followed by exactly one
Codex SkillOpt-gated canary. Claude credentials and Claude runs are deferred.
After that first gated canary, SkillOpt becomes an optional optimizer adapter,
not a required part of the execution path. See
[`docs/skillopt-decision.md`](../../docs/skillopt-decision.md).

Run gated/static experiments with `seagym train`. Transfer configs are
read-only and must be invoked with `seagym eval --checkpoint` using the final
checkpoint from the named source harness. Their transfer delta is target-harness
checkpoint score minus the source run's `A_T` score for each matching view.
The source `metric_inputs.jsonl` path is explicit and its SHA-256 is written to
the metric result. A missing source run reports `applicable: false` rather than
inventing a comparison.

No low-cost ablation is included: the optimizer policy is 35B-only, so that row
would be identical to the primary condition.
