# Deterministic SkillOpt/Holo smoke

This fixture executes the two checked-in code-optimization repositories through
the production verifier. It exercises pinned baseline materialization,
correctness tests, repeated benchmarks, edit-policy checks, normalized ATIF
evidence, SEAGym rollout/reporting, bounded SkillOpt/Holo proposal, the
method-private gate, checkpointing, and observer evaluation without network
access, API credentials, Harbor capacity, Codex, or Claude Code.

The rollout identity is explicitly `deterministic-codeopt-fixture` with model
`deterministic-fixture-model`; reports must never label it as Codex or Claude.

From the repository root:

```bash
.venv-linux/bin/seagym train examples/holo_skillopt_deterministic/config.json
```

The first update replaces the single measurement with a median of three runs.
The private deterministic gate accepts it. The second proposal is a no-op.
