# SkillOpt decision: one canary, then optional

## Decision

Keep SkillOpt in the required path for exactly one Codex production-path
canary. That canary exercises the checked-in synthetic task suite and proves
the integration, not benchmark quality. Once its artifacts pass verifier,
privacy, resume, and audit checks, move SkillOpt behind an optional optimizer
adapter. Claude credentials and runs stay deferred.

## What SkillOpt is useful for

- It supplies a concrete private acceptance gate rather than promoting a skill
  from observer metrics.
- Its bounded proposal loop is a useful reference implementation for testing
  skill mutation, rejection, checkpointing, and rollback behavior.
- The gated/static/gate-off conditions make the first canary scientifically
  legible and expose accidental evaluator authority.
- It provides a compatibility target while HoloSkill's provider-neutral
  proposal, evidence, verifier, and state contracts stabilize.

## What becomes a headache

- A gated update adds reflection and proposal calls, then evaluates both the
  current and candidate skills on the private gate. That increases cost,
  latency, credentials, and failure modes.
- Pinned SkillOpt, SEAGym, and Harbor versions create a wider compatibility and
  patch-maintenance surface than the core executor needs.
- Two state machines—SEAGym checkpoints and SkillOpt promotion state—make crash
  recovery and audit reasoning harder.
- The private gate needs its own trusted tasks and leakage boundary. On a tiny
  synthetic suite it can validate wiring, but it cannot justify production
  optimization claims.
- SkillOpt's optimizer-client assumptions are less valuable once proposal,
  validation, gate, and transactional-state interfaces are project-owned.

## Adapter boundary after the canary

The core should depend on a small optimizer protocol: normalized evidence in;
a structured proposal plus safe call accounting out. `SkillOptHoloEngine`
remains one implementation selected by configuration. Static-skill execution
and future optimizers must run without importing or authenticating SkillOpt.

The next OpenAI-native implementation should be a separate adapter, after the
Codex CLI canary is green. The official OpenAI documentation positions the
Agents SDK for code-first orchestration involving agents, tools, handoffs,
guardrails, tracing, or sandbox execution. The future adapter should reuse the
existing Harbor sandbox and HoloSkill evidence/verifier contracts instead of
creating a second task runtime. See the
[official Agents SDK guidance](https://developers.openai.com/api/docs/libraries#use-the-agents-sdk).

Implementation order:

1. Freeze the provider-neutral optimizer and gate protocols with contract
   tests.
2. Make `skillopt` an optional dependency and config-selected adapter.
3. Add a credential-gated OpenAI Agents SDK prototype that emits the same
   proposal and usage schemas; do not alter Harbor isolation or verifier
   authority.
4. Compare static, SkillOpt-gated, and new-adapter artifacts on the same canary
   tasks before considering trusted external production repositories.
