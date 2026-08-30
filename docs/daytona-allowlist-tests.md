# Daytona allowlist tests

The 15 tests that pin Harbor's Daytona egress-allowlist behaviour. They live in
the **vendored Harbor suite**, not in this project:

```text
reference/seagym/reference/harbor/tests/unit/environments/test_daytona.py
```

That file holds 139 tests in total; these are the ones whose names carry
`allowlist`. Run them from this venv — Harbor's async tests need
`pytest-asyncio`, which is declared in this project's `dev` extra:

```bash
uv run pytest reference/seagym/reference/harbor/tests/unit/environments/test_daytona.py -q
uv run pytest reference/seagym/reference/harbor/tests/unit/environments/ -q -k allowlist
```

## The tests

| # | Line | Test | What it pins |
|---:|---:|---|---|
| 1 | 290 | `compose_mode_disables_allowlist_and_dynamic_policy` | Compose mode cannot express an allowlist, and dynamic policy is disabled with it. |
| 2 | 835 | `direct_image_params_include_allowlist_network` | The policy actually reaches the sandbox creation parameters on the image path. |
| 3 | 856 | `direct_image_params_include_ipv4_allowlist_network` | Same, for the IPv4-literal form. |
| 4 | 876 | `direct_snapshot_params_include_allowlist_network` | Same, via the snapshot path rather than a fresh image. |
| 5 | 890 | `direct_snapshot_params_include_ipv4_allowlist_network` | IPv4 form on the snapshot path. |
| 6 | 927 | `compose_mode_rejects_allowlist` | Compose mode **refuses** an allowlist rather than silently ignoring it. |
| 7 | 939 | `legacy_network_override_rejected_with_allowlist` | The legacy network override cannot be used to bypass an allowlist. |
| 8 | 978 | `unsupported_ip_allowlist_shapes_rejected_when_translated` | Malformed or unsupported IP shapes are rejected during translation. |
| 9 | 998 | `malformed_phase_allowlist_rejected_at_start` | A bad per-phase allowlist fails **at start**, not part-way through a run. |
| 10 | 1018 | `ipv6_allowlist_rejected_by_capabilities` | IPv6 is refused where the provider cannot enforce it. |
| 11 | 1028 | `ipv6_phase_allowlist_rejected_by_capabilities` | Same check applied per phase. |
| 12 | 1040 | `valid_phase_allowlist_permits_start` | The positive case: a well-formed phase allowlist is accepted. |
| 13 | 1057 | `mixed_allowlist_rejected_on_runtime_switch` | Mixed address families are refused on a runtime policy switch. |
| 14 | 1072 | `ipv4_allowlist_supported_on_runtime_switch` | IPv4 allowlists survive a runtime switch. |
| 15 | 1191 | `runtime_switch_clears_stale_allowlist_fields` | A switch leaves no stale rules behind. |

Four more allowlist tests covering Daytona sit in the cross-provider network
policy suite rather than this file — `daytona_wildcard_allowlist_includes_apex_and_subdomains`,
`daytona_ipv4_allowlist_allows_only_ipv4_literals`,
`daytona_allowlist_to_allowlist_runtime_switch` and
`daytona_allowlist_to_public_runtime_switch`. Which suite a count came from
changes the number, so state the file when quoting one.

## What the shape of this list tells you

**Eleven of the fifteen assert a refusal.** Only 2–5, 12 and 14 check that a
valid policy is applied; the rest check that an invalid, unsupported or
bypass-shaped one is rejected. That is the same fail-closed posture this project
takes in `_validate_task_network_policy`, and it is not a coincidence — these
tests exist upstream because the pre-v0.17.0 behaviour **silently degraded to
public egress** instead of refusing, which is exactly the defect that kept
Daytona unusable here until the vendored Harbor was bumped to v0.22.0.

Tests 6, 9 and 15 are the ones worth reading if you only read three:

- **6** is the difference between "cannot" and "will not". A mode that cannot
  express a policy must refuse it, not accept and drop it.
- **9** moves the failure to the earliest possible point. A malformed policy
  discovered mid-run has already leaked whatever it was meant to contain.
- **15** covers the case that silent-degradation bugs actually live in: state
  left over from a previous policy after a switch.

## Relationship to this project's own checks

These verify that **Harbor** enforces a policy the task declares. This project's
`_validate_task_network_policy` verifies something different and complementary:
that the *experiment config* cannot claim a policy the task does not declare. A
config here can only fail closed, never widen egress.

Neither helps if the task declares nothing. The vendored AlgoTune tasks omit
`[agent].network_mode` and `[verifier].network_mode` entirely, so they inherit
the environment baseline — effectively `public` — and none of these 15 tests is
engaged. Adding per-phase policy to the task packages is what makes them apply.

`holoskill_gym/preflight.py` adds a third layer: it blocks a Daytona run unless
the vendored Harbor checkout descends from the commit that fixed the allowlist
(`DAYTONA_ALLOWLIST_FIX`), verified by **git ancestry rather than a version
string** — because an editable install can report a stale version while running
newer code.
