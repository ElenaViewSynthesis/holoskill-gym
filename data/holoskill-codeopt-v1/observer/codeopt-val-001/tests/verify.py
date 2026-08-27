#!/usr/bin/env python3
"""HoloSkill verifier: correctness, edit policy, and before/after benchmark.

Writes /logs/verifier/reward.json. Baseline performance is measured in
this same container against the pristine module shipped in
/tests/baseline/, so the comparison never depends on a number recorded
on different hardware.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

APP = Path("/app")
OUT = Path("/logs/verifier/reward.json")
MODULE = "src/serialization.py"
METRIC = 'serialize_latency_units'
DIRECTION = 'minimize'
PROTECTED = ("tests/", "benchmark.py", "task.toml", ".git/")


def run(cmd: list[str], cwd: Path, timeout: int = 300):
    return subprocess.run(
        cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout
    )


def changed_files() -> list[str]:
    proc = run(["git", "status", "--porcelain"], APP)
    names = []
    for line in proc.stdout.splitlines():
        entry = line[3:].strip()
        if entry:
            names.append(entry)
    return sorted(names)


def benchmark(cwd: Path) -> float | None:
    proc = run(["python3", "benchmark.py"], cwd)
    if proc.returncode != 0:
        return None
    try:
        return float(json.loads(proc.stdout)[METRIC])
    except (ValueError, KeyError, json.JSONDecodeError):
        return None


def main() -> int:
    result = {
        "reward": 0.0,
        "correctness_pass": 0.0,
        "edit_policy_pass": 0.0,
        "infra_valid": 0.0,
        "speedup": 0.0,
        "forbidden_edit": 0.0,
        "tampering_detected": 0.0,
        "regression": 0.0,
        "timeout": 0.0,
    }

    changed = changed_files()
    result["changed_files"] = changed
    forbidden = [c for c in changed if c.startswith(PROTECTED)]
    result["forbidden_edit"] = float(bool(forbidden))
    result["edit_policy_pass"] = float(not forbidden)
    if forbidden:
        result["forbidden_files"] = forbidden

    tests = run(["python3", "-m", "pytest", "tests/", "-q"], APP)
    result["correctness_pass"] = float(tests.returncode == 0)
    result["tests_returncode"] = tests.returncode

    after = benchmark(APP)

    # Baseline: pristine module in a scratch copy of the same tree.
    baseline_value = None
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp) / "app"
        shutil.copytree(APP, scratch, ignore=shutil.ignore_patterns(".git"))
        shutil.copyfile(Path("/tests/baseline") / Path(MODULE).name,
                        scratch / MODULE)
        baseline_value = benchmark(scratch)

    if after is None or baseline_value is None or after <= 0 or baseline_value <= 0:
        result["error"] = "benchmark did not produce a usable measurement"
        OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return 1

    result["infra_valid"] = 1.0
    result["benchmark_before"] = baseline_value
    result["benchmark_after"] = after
    speedup = (
        after / baseline_value if DIRECTION == "maximize" else baseline_value / after
    )
    result["speedup"] = speedup
    result["regression"] = float(speedup < 1.0)
    result["reward"] = float(
        result["correctness_pass"] == 1.0 and result["edit_policy_pass"] == 1.0
    )
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
