# Deterministic SkillOpt/Holo smoke

This fixture exercises SEAGym rollout, bounded SkillOpt/Holo proposal, the
method-private gate, checkpointing, observer evaluation, and reporting without
network access, API credentials, Harbor capacity, Codex, or Claude Code.

From the repository root:

```bash
.venv-linux/bin/seagym train examples/holo_skillopt_deterministic/config.json
```

The first update replaces the single measurement with a median of three runs.
The private deterministic gate accepts it. The second proposal is a no-op.
