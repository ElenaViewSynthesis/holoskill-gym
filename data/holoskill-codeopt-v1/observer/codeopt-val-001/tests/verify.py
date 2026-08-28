#!/usr/bin/env python3
"""Generated Harbor verifier for one HoloSkill code-optimization canary."""

from __future__ import annotations

import hashlib
import json
import shutil
import statistics
import subprocess
import tempfile
import time
from pathlib import Path

APP = Path("/app")
LOG_DIR = Path("/logs/verifier")
REWARD_PATH = LOG_DIR / "reward.json"
DETAIL_PATH = LOG_DIR / "holoskill_verifier.json"
PATCH_PATH = LOG_DIR / "changes.patch"
UNTRACKED_PATH = LOG_DIR / "untracked_manifest.json"
TASK_ID = "codeopt-val-001"
MODULE = "src/serialization.py"
METRIC = "serialize_latency_units"
DIRECTION = "minimize"
PROTECTED = ("tests/", "benchmark.py", "task.toml", ".git/")
MAX_LOG_CHARS = 256_000


def run(label: str, cmd: list[str], cwd: Path, timeout: int = 300):
    started = time.monotonic()
    timed_out = False
    launch_error = None
    exit_code = None
    stdout = ""
    stderr = ""
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        exit_code = proc.returncode
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = _text(exc.stdout)
        stderr = _text(exc.stderr)
    except OSError as exc:
        launch_error = type(exc).__name__
        stderr = launch_error

    stdout_path = LOG_DIR / f"{label}.stdout.log"
    stderr_path = LOG_DIR / f"{label}.stderr.log"
    stdout_path.write_text(stdout[:MAX_LOG_CHARS], encoding="utf-8")
    stderr_path.write_text(stderr[:MAX_LOG_CHARS], encoding="utf-8")
    record = {
        "label": label,
        "argv": cmd,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "timeout_reason": f"command exceeded {timeout} seconds" if timed_out else None,
        "wall_time_seconds": time.monotonic() - started,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "launch_error": launch_error,
    }
    return record, stdout


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def changed_files() -> list[str]:
    proc = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(APP),
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    names = []
    for line in proc.stdout.splitlines():
        entry = line[3:].strip()
        if " -> " in entry:
            entry = entry.split(" -> ", 1)[1]
        if entry:
            names.append(entry)
    return sorted(set(names))


def patch_evidence(changed: list[str]):
    patch = subprocess.run(
        ["git", "diff", "--binary", "HEAD"],
        cwd=str(APP),
        capture_output=True,
        timeout=30,
        check=True,
    ).stdout
    PATCH_PATH.write_bytes(patch)
    untracked = [path for path in changed if not (APP / path).exists() or _is_untracked(path)]
    UNTRACKED_PATH.write_text(json.dumps(untracked, indent=2) + "\n", encoding="utf-8")

    files_changed = insertions = deletions = 0
    numstat = subprocess.run(
        ["git", "diff", "--numstat", "HEAD"],
        cwd=str(APP),
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    ).stdout
    for line in numstat.splitlines():
        added, removed, *_ = line.split("\t")
        files_changed += 1
        if added.isdigit():
            insertions += int(added)
        if removed.isdigit():
            deletions += int(removed)
    files_changed = max(files_changed, len(changed))
    return (
        {"files_changed": files_changed, "insertions": insertions, "deletions": deletions},
        hashlib.sha256(patch + UNTRACKED_PATH.read_bytes()).hexdigest(),
    )


def _is_untracked(path: str) -> bool:
    proc = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", path],
        cwd=str(APP),
        capture_output=True,
        timeout=30,
    )
    return proc.returncode != 0


def benchmark(label: str, cwd: Path, commands: list[dict]):
    command, stdout = run(label, ["python3", "benchmark.py"], cwd)
    commands.append(command)
    if command["exit_code"] != 0 or command["timed_out"] or command["launch_error"]:
        return None, []
    try:
        payload = json.loads(stdout)
        aggregate = float(payload[METRIC])
        timings = [float(value) for value in payload.get("samples", [])]
        if DIRECTION == "maximize":
            samples = [1.0 / value for value in timings if value > 0]
        else:
            samples = [value * 1000.0 for value in timings if value > 0]
        return aggregate, samples
    except (TypeError, ValueError, KeyError, json.JSONDecodeError, ZeroDivisionError):
        return None, []


def coefficient_of_variation(samples: list[float]) -> float | None:
    if not samples:
        return None
    mean = statistics.fmean(samples)
    return statistics.pstdev(samples) / mean if mean > 0 else None


def write_outputs(detail: dict) -> None:
    DETAIL_PATH.write_text(json.dumps(detail, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    benchmark_data = detail["benchmark"]
    rewards = {
        "reward": float(
            detail["infra_valid"]
            and detail["correctness_pass"]
            and detail["edit_policy_pass"]
        ),
        "correctness_pass": float(detail["correctness_pass"]),
        "edit_policy_pass": float(detail["edit_policy_pass"]),
        "infra_valid": float(detail["infra_valid"]),
        "speedup": float(benchmark_data.get("speedup") or 0.0),
        "forbidden_edit": float(detail["policy"]["forbidden_edit"]),
        "tampering_detected": float(detail["policy"]["tampering_detected"]),
        "regression": float(detail["regression"]),
        "timeout": float(detail["timed_out"]),
        "wall_time_seconds": float(detail["wall_time_seconds"]),
        "tool_calls": float(detail["tool_calls"]),
    }
    REWARD_PATH.write_text(json.dumps(rewards, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    started = time.monotonic()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    commands: list[dict] = []
    timed_out = False
    infra_valid = True

    try:
        changed = changed_files()
        diff, patch_sha = patch_evidence(changed)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        changed = []
        diff = {"files_changed": 0, "insertions": 0, "deletions": 0}
        patch_sha = hashlib.sha256(b"").hexdigest()
        infra_valid = False
        errors.append(f"patch evidence failed: {type(exc).__name__}")

    forbidden = [path for path in changed if path.startswith(PROTECTED)]
    edit_policy_pass = not forbidden

    final_test, _ = run("final_test", ["python3", "-m", "pytest", "tests/", "-q"], APP)
    commands.append(final_test)
    correctness_pass = final_test["exit_code"] == 0 and not final_test["timed_out"]
    timed_out = timed_out or final_test["timed_out"]
    after, after_samples = benchmark("after_benchmark", APP, commands)

    before = None
    before_samples: list[float] = []
    correctness_before_pass = False
    with tempfile.TemporaryDirectory() as temporary:
        baseline = Path(temporary) / "app"
        shutil.copytree(APP, baseline, ignore=shutil.ignore_patterns(".git"))
        shutil.copyfile(Path("/tests/baseline") / Path(MODULE).name, baseline / MODULE)
        baseline_test, _ = run(
            "baseline_test",
            ["python3", "-m", "pytest", "tests/", "-q"],
            baseline,
        )
        commands.append(baseline_test)
        correctness_before_pass = (
            baseline_test["exit_code"] == 0 and not baseline_test["timed_out"]
        )
        timed_out = timed_out or baseline_test["timed_out"]
        before, before_samples = benchmark("before_benchmark", baseline, commands)

    if before is None or after is None or before <= 0 or after <= 0:
        infra_valid = False
        errors.append("benchmark did not produce finite positive measurements")
        speedup = None
    else:
        speedup = after / before if DIRECTION == "maximize" else before / after

    benchmark_data = {
        "metric": METRIC,
        "direction": DIRECTION,
        "before_samples": before_samples,
        "after_samples": after_samples,
        "before_aggregate": before,
        "after_aggregate": after,
        "speedup": speedup,
        "coefficient_of_variation": coefficient_of_variation(after_samples),
    }
    performance = {
        "latency_before": before if DIRECTION == "minimize" else None,
        "latency_after": after if DIRECTION == "minimize" else None,
        "latency_delta_pct": (
            100.0 * (after - before) / before
            if DIRECTION == "minimize" and before and after is not None
            else None
        ),
        "throughput_before": before if DIRECTION == "maximize" else None,
        "throughput_after": after if DIRECTION == "maximize" else None,
        "throughput_delta_pct": (
            100.0 * (after - before) / before
            if DIRECTION == "maximize" and before and after is not None
            else None
        ),
        "peak_memory_before": None,
        "peak_memory_after": None,
        "peak_memory_delta_pct": None,
    }

    if timed_out:
        terminal_status = "timeout"
    elif not infra_valid:
        terminal_status = "benchmark_error"
    elif not edit_policy_pass:
        terminal_status = "policy_failure"
    elif not correctness_pass:
        terminal_status = "test_failure"
    else:
        terminal_status = "success"

    detail = {
        "schema_version": "holoskill-verifier-v1",
        "task_id": TASK_ID,
        "correctness_before_pass": correctness_before_pass,
        "correctness_pass": correctness_pass,
        "edit_policy_pass": edit_policy_pass,
        "infra_valid": infra_valid,
        "benchmark": benchmark_data,
        "performance": performance,
        "changed_files": changed,
        "diff": diff,
        "patch_sha256": patch_sha,
        "policy": {
            "edit_policy_pass": edit_policy_pass,
            "forbidden_edit": bool(forbidden),
            "tampering_detected": bool(forbidden),
            "forbidden_files": forbidden,
        },
        "regression": speedup is not None and speedup < 1.0,
        "timed_out": timed_out,
        "wall_time_seconds": time.monotonic() - started,
        "tool_calls": 0,
        "terminal_status": terminal_status,
        "errors": errors,
        "commands": commands,
        "artifact_paths": {
            "verifier_result": str(DETAIL_PATH),
            "patch": str(PATCH_PATH),
            "untracked_manifest": str(UNTRACKED_PATH),
        },
    }
    write_outputs(detail)
    return 0 if infra_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
