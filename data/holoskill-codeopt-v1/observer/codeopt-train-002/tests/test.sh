#!/usr/bin/env bash
# Verifier entrypoint. Emits /logs/verifier/reward.json.
set -uo pipefail
mkdir -p /logs/verifier
python3 /tests/verify.py
status=$?
if [ ! -s /logs/verifier/reward.json ]; then
  # verify.py could not report; record an infrastructure failure rather
  # than letting a missing file read as a zero score.
  printf '%s\n' '{"reward": 0, "infra_valid": 0, "error": "verifier produced no reward"}' \
    > /logs/verifier/reward.json
fi
exit $status
