"""Deterministic code-optimization verification inside Harbor task environments."""

from __future__ import annotations

import hashlib
import io
import json
import os
import signal
import statistics
import subprocess
import tarfile
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from .metrics import (
    benchmark_cv,
    benchmark_speedup,
    correctness_gated_performance,
    latency_delta_pct,
    peak_memory_delta_pct,
    regression_indicator,
    throughput_delta_pct,
)
from .schemas import GateTaskScore
from .tasks import CodeOptTask, EditPolicyResult, verify_edit_policy
from .trajectory import (
    BenchmarkEvidence,
    DiffStatistics,
    EvidenceModel,
    PerformanceAggregates,
    PolicyEvidence,
    TerminalStatus,
)

VERIFIER_SCHEMA_VERSION = "holoskill-verifier-v1"
MAX_COMMAND_OUTPUT_BYTES = 256_000


class CommandExecution(EvidenceModel):
    label: str = Field(min_length=1)
    argv: list[str] = Field(min_length=1)
    exit_code: int | None = None
    timed_out: bool = False
    timeout_reason: str | None = None
    wall_time_seconds: float = Field(ge=0)
    stdout_path: str
    stderr_path: str
    launch_error: str | None = None


class VerifierResult(EvidenceModel):
    """Strict verifier output; reward zero and infrastructure failure are distinct."""

    schema_version: Literal["holoskill-verifier-v1"] = VERIFIER_SCHEMA_VERSION
    task_id: str = Field(min_length=1)
    correctness_before_pass: bool
    correctness_pass: bool
    edit_policy_pass: bool
    infra_valid: bool
    benchmark: BenchmarkEvidence = Field(default_factory=BenchmarkEvidence)
    performance: PerformanceAggregates = Field(default_factory=PerformanceAggregates)
    changed_files: list[str] = Field(default_factory=list)
    diff: DiffStatistics = Field(default_factory=DiffStatistics)
    patch_sha256: str | None = None
    policy: PolicyEvidence = Field(default_factory=PolicyEvidence)
    regression: bool = False
    timed_out: bool = False
    wall_time_seconds: float = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    terminal_status: TerminalStatus
    errors: list[str] = Field(default_factory=list)
    commands: list[CommandExecution] = Field(default_factory=list)
    artifact_paths: dict[str, str] = Field(default_factory=dict)

    @property
    def reward(self) -> float:
        return float(self.infra_valid and self.correctness_pass and self.edit_policy_pass)

    def reward_metrics(self) -> dict[str, float]:
        speedup = self.benchmark.speedup or 0.0
        return {
            "reward": self.reward,
            "correctness_pass": float(self.correctness_pass),
            "edit_policy_pass": float(self.edit_policy_pass),
            "infra_valid": float(self.infra_valid),
            "speedup": float(speedup),
            "forbidden_edit": float(self.policy.forbidden_edit),
            "tampering_detected": float(self.policy.tampering_detected),
            "regression": float(self.regression),
            "timeout": float(self.timed_out),
            "wall_time_seconds": self.wall_time_seconds,
            "tool_calls": float(self.tool_calls),
        }

    def to_gate_task_score(self) -> GateTaskScore:
        speedup = self.benchmark.speedup
        soft = 0.0
        if speedup is not None:
            soft = correctness_gated_performance(
                correctness_pass=self.correctness_pass,
                speedup=speedup,
            )
        return GateTaskScore(
            task_id=self.task_id,
            hard_score=self.reward,
            soft_score=soft,
            correctness_pass=self.correctness_pass,
            edit_policy_pass=self.edit_policy_pass,
            infra_valid=self.infra_valid,
            speedup=speedup,
            error="; ".join(self.errors) or None,
        )


@dataclass(frozen=True)
class VerifierConfig:
    benchmark_warmups: int = 1
    benchmark_samples: int = 5
    command_timeout_seconds: float | None = None
    process_group_grace_seconds: float = 1.0

    def __post_init__(self) -> None:
        if self.benchmark_warmups < 0:
            raise ValueError("benchmark_warmups must be non-negative")
        if self.benchmark_samples <= 0:
            raise ValueError("benchmark_samples must be positive")
        if self.command_timeout_seconds is not None and self.command_timeout_seconds <= 0:
            raise ValueError("command_timeout_seconds must be positive")
        if self.process_group_grace_seconds < 0:
            raise ValueError("process_group_grace_seconds must be non-negative")


@dataclass(frozen=True)
class _CapturedCommand:
    result: CommandExecution
    stdout: bytes
    stderr: bytes


def run_command(
    argv: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: float,
    artifact_dir: Path,
    label: str,
    process_group_grace_seconds: float = 1.0,
) -> CommandExecution:
    """Run shell-free and terminate the entire subprocess group on timeout."""

    return _run_command(
        argv,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        artifact_dir=artifact_dir,
        label=label,
        process_group_grace_seconds=process_group_grace_seconds,
    ).result


def verify_code_optimization(
    task: CodeOptTask,
    *,
    repo_path: Path,
    artifact_dir: Path,
    config: VerifierConfig | None = None,
) -> VerifierResult:
    """Compare the pinned commit with the agent-modified working tree."""

    started = time.monotonic()
    config = config or VerifierConfig()
    repo_path = repo_path.resolve()
    artifact_dir = artifact_dir.resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    timeout = config.command_timeout_seconds or float(task.timeout_seconds)
    commands: list[CommandExecution] = []
    errors: list[str] = []

    try:
        resolved_commit = _git_text(repo_path, "rev-parse", f"{task.commit}^{{commit}}")
        head_commit = _git_text(repo_path, "rev-parse", "HEAD")
    except RuntimeError as exc:
        return _failure_result(
            task,
            started=started,
            terminal_status="agent_error",
            infra_valid=False,
            errors=[str(exc)],
            artifact_dir=artifact_dir,
        )
    if resolved_commit != task.commit:
        return _failure_result(
            task,
            started=started,
            terminal_status="agent_error",
            infra_valid=False,
            errors=["repository did not resolve the pinned commit"],
            artifact_dir=artifact_dir,
        )

    tampering_detected = head_commit != task.commit
    with tempfile.TemporaryDirectory(prefix="holoskill-baseline-") as temporary:
        baseline_path = Path(temporary)
        try:
            _extract_git_archive(repo_path, task.commit, baseline_path)
        except RuntimeError as exc:
            return _failure_result(
                task,
                started=started,
                terminal_status="agent_error",
                infra_valid=False,
                errors=[str(exc)],
                artifact_dir=artifact_dir,
            )

        setup = _run_optional_command(
            task.setup_argv,
            cwd=baseline_path,
            timeout=timeout,
            artifact_dir=artifact_dir,
            label="baseline_setup",
            config=config,
        )
        if setup is not None:
            commands.append(setup.result)
            if not _command_succeeded(setup.result):
                return _failure_result(
                    task,
                    started=started,
                    terminal_status="timeout" if setup.result.timed_out else "agent_error",
                    infra_valid=False,
                    timed_out=setup.result.timed_out,
                    errors=[_command_failure("baseline setup", setup.result)],
                    commands=commands,
                    artifact_dir=artifact_dir,
                )

        baseline_test = _run_command(
            task.test_argv,
            cwd=baseline_path,
            timeout_seconds=timeout,
            artifact_dir=artifact_dir,
            label="baseline_test",
            process_group_grace_seconds=config.process_group_grace_seconds,
        )
        commands.append(baseline_test.result)
        if not _command_succeeded(baseline_test.result):
            return _failure_result(
                task,
                started=started,
                terminal_status=("timeout" if baseline_test.result.timed_out else "test_failure"),
                infra_valid=False,
                timed_out=baseline_test.result.timed_out,
                errors=[_command_failure("baseline correctness", baseline_test.result)],
                commands=commands,
                artifact_dir=artifact_dir,
            )

        before_samples, before_commands, benchmark_error = _measure_benchmark(
            task.benchmark_argv,
            cwd=baseline_path,
            timeout=timeout,
            artifact_dir=artifact_dir,
            label_prefix="baseline_benchmark",
            config=config,
        )
        commands.extend(before_commands)
        if benchmark_error:
            return _failure_result(
                task,
                started=started,
                terminal_status="benchmark_error",
                infra_valid=False,
                timed_out=any(command.timed_out for command in before_commands),
                errors=[benchmark_error],
                commands=commands,
                artifact_dir=artifact_dir,
            )

    changed_files = _changed_files(repo_path, task.commit)
    edit_policy = verify_edit_policy(task, changed_files)
    policy = PolicyEvidence(
        edit_policy_pass=edit_policy.passed and not tampering_detected,
        forbidden_edit=bool(edit_policy.forbidden_files),
        tampering_detected=tampering_detected,
        forbidden_files=edit_policy.forbidden_files,
    )
    diff, patch_sha, patch_path = _patch_evidence(
        repo_path,
        task.commit,
        changed_files,
        artifact_dir,
    )
    if not policy.edit_policy_pass:
        errors.append("edit policy failed before final verification")
        return _finalize_result(
            task=task,
            started=started,
            correctness_before_pass=True,
            correctness_pass=False,
            edit_policy=edit_policy,
            infra_valid=True,
            benchmark=BenchmarkEvidence(
                metric=task.benchmark_metric,
                direction=task.optimization_direction,
                before_samples=before_samples,
                before_aggregate=statistics.median(before_samples),
            ),
            performance=PerformanceAggregates(),
            changed_files=changed_files,
            diff=diff,
            patch_sha=patch_sha,
            policy=policy,
            terminal_status="policy_failure",
            errors=errors,
            commands=commands,
            artifact_dir=artifact_dir,
            patch_path=patch_path,
        )

    final_test = _run_command(
        task.test_argv,
        cwd=repo_path,
        timeout_seconds=timeout,
        artifact_dir=artifact_dir,
        label="final_test",
        process_group_grace_seconds=config.process_group_grace_seconds,
    )
    commands.append(final_test.result)
    correctness_pass = _command_succeeded(final_test.result)
    if not correctness_pass:
        errors.append(_command_failure("final correctness", final_test.result))
        return _finalize_result(
            task=task,
            started=started,
            correctness_before_pass=True,
            correctness_pass=False,
            edit_policy=edit_policy,
            infra_valid=not final_test.result.timed_out,
            benchmark=BenchmarkEvidence(
                metric=task.benchmark_metric,
                direction=task.optimization_direction,
                before_samples=before_samples,
                before_aggregate=statistics.median(before_samples),
            ),
            performance=PerformanceAggregates(),
            changed_files=changed_files,
            diff=diff,
            patch_sha=patch_sha,
            policy=policy,
            terminal_status="timeout" if final_test.result.timed_out else "test_failure",
            errors=errors,
            commands=commands,
            artifact_dir=artifact_dir,
            patch_path=patch_path,
            timed_out=final_test.result.timed_out,
        )

    after_samples, after_commands, benchmark_error = _measure_benchmark(
        task.benchmark_argv,
        cwd=repo_path,
        timeout=timeout,
        artifact_dir=artifact_dir,
        label_prefix="final_benchmark",
        config=config,
    )
    commands.extend(after_commands)
    if benchmark_error:
        errors.append(benchmark_error)
        return _finalize_result(
            task=task,
            started=started,
            correctness_before_pass=True,
            correctness_pass=True,
            edit_policy=edit_policy,
            infra_valid=False,
            benchmark=BenchmarkEvidence(
                metric=task.benchmark_metric,
                direction=task.optimization_direction,
                before_samples=before_samples,
                after_samples=after_samples,
                before_aggregate=statistics.median(before_samples),
            ),
            performance=PerformanceAggregates(),
            changed_files=changed_files,
            diff=diff,
            patch_sha=patch_sha,
            policy=policy,
            terminal_status="benchmark_error",
            errors=errors,
            commands=commands,
            artifact_dir=artifact_dir,
            patch_path=patch_path,
            timed_out=any(command.timed_out for command in after_commands),
        )

    before = statistics.median(before_samples)
    after = statistics.median(after_samples)
    speedup = benchmark_speedup(
        before=before,
        after=after,
        direction=task.optimization_direction,
    )
    benchmark = BenchmarkEvidence(
        metric=task.benchmark_metric,
        direction=task.optimization_direction,
        before_samples=before_samples,
        after_samples=after_samples,
        before_aggregate=before,
        after_aggregate=after,
        speedup=speedup,
        coefficient_of_variation=benchmark_cv(after_samples),
    )
    performance = _performance_aggregates(task.benchmark_metric, before, after)
    return _finalize_result(
        task=task,
        started=started,
        correctness_before_pass=True,
        correctness_pass=True,
        edit_policy=edit_policy,
        infra_valid=True,
        benchmark=benchmark,
        performance=performance,
        changed_files=changed_files,
        diff=diff,
        patch_sha=patch_sha,
        policy=policy,
        terminal_status="success",
        errors=errors,
        commands=commands,
        artifact_dir=artifact_dir,
        patch_path=patch_path,
    )


def verifier_result_from_trajectory(trajectory: Any) -> VerifierResult | None:
    """Load only an explicit strict verifier result; never infer from success."""

    refs = trajectory.refs if isinstance(getattr(trajectory, "refs", None), Mapping) else {}
    extra = refs.get("extra") if isinstance(refs.get("extra"), Mapping) else {}
    project = extra.get("holoskill_gym") if isinstance(extra.get("holoskill_gym"), Mapping) else {}
    candidates: list[Any] = [project.get("verifier_result")]
    normalized = project.get("normalized_evidence")
    if isinstance(normalized, Mapping):
        normalized_extra = normalized.get("extra")
        if isinstance(normalized_extra, Mapping):
            normalized_project = normalized_extra.get("holoskill_gym")
            if isinstance(normalized_project, Mapping):
                candidates.append(normalized_project.get("verifier_result"))
    for candidate in candidates:
        if isinstance(candidate, Mapping):
            return VerifierResult.model_validate(candidate)

    result_path = refs.get("result_path")
    if isinstance(result_path, str) and "://" not in result_path:
        trial_dir = Path(result_path).resolve().parent
        for path in (
            trial_dir / "verifier" / "holoskill_verifier.json",
            trial_dir / "logs" / "verifier" / "holoskill_verifier.json",
        ):
            if path.exists():
                return VerifierResult.model_validate_json(path.read_text(encoding="utf-8"))
    return None


def write_verifier_result(result: VerifierResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _run_command(
    argv: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: float,
    artifact_dir: Path,
    label: str,
    process_group_grace_seconds: float,
) -> _CapturedCommand:
    command = [str(item) for item in argv]
    if not command or any(not item or "\x00" in item for item in command):
        raise ValueError("argv must contain non-empty strings without NUL bytes")
    cwd = cwd.resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = artifact_dir / f"{label}.stdout.log"
    stderr_path = artifact_dir / f"{label}.stderr.log"
    started = time.monotonic()
    timed_out = False
    timeout_reason = None
    launch_error = None
    exit_code: int | None = None
    stdout = b""
    stderr = b""
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=os.name != "nt",
            creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            timeout_reason = f"command exceeded {timeout_seconds:g} seconds"
            _terminate_process_group(
                process,
                grace_seconds=process_group_grace_seconds,
            )
            stdout, stderr = process.communicate()
        exit_code = process.returncode
    except OSError as exc:
        launch_error = f"{type(exc).__name__}: {exc}"
    wall_time = time.monotonic() - started
    stdout_path.write_bytes(stdout[:MAX_COMMAND_OUTPUT_BYTES])
    stderr_path.write_bytes(stderr[:MAX_COMMAND_OUTPUT_BYTES])
    return _CapturedCommand(
        result=CommandExecution(
            label=label,
            argv=command,
            exit_code=exit_code,
            timed_out=timed_out,
            timeout_reason=timeout_reason,
            wall_time_seconds=wall_time,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            launch_error=launch_error,
        ),
        stdout=stdout,
        stderr=stderr,
    )


def _terminate_process_group(process: subprocess.Popen[bytes], *, grace_seconds: float) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        process.terminate()
    else:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=grace_seconds)
        return
    except subprocess.TimeoutExpired:
        pass
    if os.name == "nt":
        process.kill()
    else:
        os.killpg(process.pid, signal.SIGKILL)


def _run_optional_command(
    argv: Sequence[str],
    *,
    cwd: Path,
    timeout: float,
    artifact_dir: Path,
    label: str,
    config: VerifierConfig,
) -> _CapturedCommand | None:
    if not argv:
        return None
    return _run_command(
        argv,
        cwd=cwd,
        timeout_seconds=timeout,
        artifact_dir=artifact_dir,
        label=label,
        process_group_grace_seconds=config.process_group_grace_seconds,
    )


def _measure_benchmark(
    argv: Sequence[str],
    *,
    cwd: Path,
    timeout: float,
    artifact_dir: Path,
    label_prefix: str,
    config: VerifierConfig,
) -> tuple[list[float], list[CommandExecution], str | None]:
    commands: list[CommandExecution] = []
    samples: list[float] = []
    total = config.benchmark_warmups + config.benchmark_samples
    for index in range(total):
        phase = "warmup" if index < config.benchmark_warmups else "sample"
        ordinal = index + 1 if phase == "warmup" else index - config.benchmark_warmups + 1
        captured = _run_command(
            argv,
            cwd=cwd,
            timeout_seconds=timeout,
            artifact_dir=artifact_dir,
            label=f"{label_prefix}_{phase}_{ordinal:03d}",
            process_group_grace_seconds=config.process_group_grace_seconds,
        )
        commands.append(captured.result)
        if not _command_succeeded(captured.result):
            return samples, commands, _command_failure(label_prefix, captured.result)
        try:
            value = _parse_benchmark_value(captured.stdout)
        except ValueError as exc:
            return samples, commands, f"{label_prefix} produced invalid output: {exc}"
        if phase == "sample":
            samples.append(value)
    return samples, commands, None


def _parse_benchmark_value(stdout: bytes) -> float:
    text = stdout.decode("utf-8", errors="replace").strip()
    if not text:
        raise ValueError("empty stdout")
    line = text.splitlines()[-1].strip()
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        payload = line
    if isinstance(payload, Mapping):
        payload = payload.get("value")
    if isinstance(payload, bool):
        raise TypeError("boolean benchmark value")
    try:
        value = float(payload)
    except (TypeError, ValueError) as exc:
        raise ValueError("last line must be a number or a JSON object with value") from exc
    if not value > 0 or not value < float("inf"):
        raise ValueError("benchmark value must be finite and positive")
    return value


def _extract_git_archive(repo_path: Path, commit: str, destination: Path) -> None:
    completed = subprocess.run(
        ["git", "archive", "--format=tar", commit],
        cwd=repo_path,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("cannot materialize pinned baseline commit")
    try:
        with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:") as archive:
            archive.extractall(destination, filter="data")
    except tarfile.TarError as exc:
        raise RuntimeError("pinned baseline archive is invalid") from exc


def _git_text(repo_path: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_path,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed")
    return completed.stdout.strip()


def _changed_files(repo_path: Path, commit: str) -> list[str]:
    tracked = _git_text(repo_path, "diff", "--name-only", commit, "--").splitlines()
    untracked = _git_text(
        repo_path,
        "ls-files",
        "--others",
        "--exclude-standard",
    ).splitlines()
    return sorted(set(filter(None, tracked + untracked)))


def _patch_evidence(
    repo_path: Path,
    commit: str,
    changed_files: Sequence[str],
    artifact_dir: Path,
) -> tuple[DiffStatistics, str, Path]:
    completed = subprocess.run(
        ["git", "diff", "--binary", commit, "--"],
        cwd=repo_path,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("cannot compute repository patch")
    untracked = set(_git_text(repo_path, "ls-files", "--others", "--exclude-standard").splitlines())
    untracked_hashes: dict[str, str] = {}
    insertions = 0
    deletions = 0
    for line in _git_text(repo_path, "diff", "--numstat", commit, "--").splitlines():
        parts = line.split("\t", 2)
        if len(parts) >= 2:
            insertions += int(parts[0]) if parts[0].isdigit() else 0
            deletions += int(parts[1]) if parts[1].isdigit() else 0
    for relative in sorted(untracked):
        path = repo_path / relative
        if path.is_file():
            content = path.read_bytes()
            untracked_hashes[relative] = hashlib.sha256(content).hexdigest()
            insertions += content.count(b"\n") + int(bool(content and not content.endswith(b"\n")))
    manifest = json.dumps(untracked_hashes, sort_keys=True, separators=(",", ":")).encode()
    patch_sha = hashlib.sha256(completed.stdout + b"\0" + manifest).hexdigest()
    patch_path = artifact_dir / "changes.patch"
    patch_path.write_bytes(completed.stdout)
    (artifact_dir / "untracked_manifest.json").write_text(
        json.dumps(untracked_hashes, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return (
        DiffStatistics(
            files_changed=len(set(changed_files)),
            insertions=insertions,
            deletions=deletions,
        ),
        patch_sha,
        patch_path,
    )


def _performance_aggregates(
    metric: str,
    before: float,
    after: float,
) -> PerformanceAggregates:
    lowered = metric.lower()
    if any(token in lowered for token in ("latency", "runtime", "duration", "time")):
        return PerformanceAggregates(
            latency_before=before,
            latency_after=after,
            latency_delta_pct=latency_delta_pct(before=before, after=after),
        )
    if any(token in lowered for token in ("throughput", "ops", "requests")):
        return PerformanceAggregates(
            throughput_before=before,
            throughput_after=after,
            throughput_delta_pct=throughput_delta_pct(before=before, after=after),
        )
    if "memory" in lowered:
        return PerformanceAggregates(
            peak_memory_before=before,
            peak_memory_after=after,
            peak_memory_delta_pct=peak_memory_delta_pct(before=before, after=after),
        )
    return PerformanceAggregates()


def _finalize_result(
    *,
    task: CodeOptTask,
    started: float,
    correctness_before_pass: bool,
    correctness_pass: bool,
    edit_policy: EditPolicyResult,
    infra_valid: bool,
    benchmark: BenchmarkEvidence,
    performance: PerformanceAggregates,
    changed_files: Sequence[str],
    diff: DiffStatistics,
    patch_sha: str,
    policy: PolicyEvidence,
    terminal_status: TerminalStatus,
    errors: Sequence[str],
    commands: Sequence[CommandExecution],
    artifact_dir: Path,
    patch_path: Path,
    timed_out: bool = False,
) -> VerifierResult:
    result_path = artifact_dir / "holoskill_verifier.json"
    result = VerifierResult(
        task_id=task.task_id,
        correctness_before_pass=correctness_before_pass,
        correctness_pass=correctness_pass,
        edit_policy_pass=edit_policy.passed and not policy.tampering_detected,
        infra_valid=infra_valid,
        benchmark=benchmark,
        performance=performance,
        changed_files=sorted(set(changed_files)),
        diff=diff,
        patch_sha256=patch_sha,
        policy=policy,
        regression=(
            bool(benchmark.speedup) and regression_indicator(speedup=float(benchmark.speedup)) == 1
        ),
        timed_out=timed_out,
        wall_time_seconds=time.monotonic() - started,
        terminal_status=terminal_status,
        errors=list(errors),
        commands=list(commands),
        artifact_paths={
            "verifier_result": str(result_path),
            "patch": str(patch_path),
            "untracked_manifest": str(artifact_dir / "untracked_manifest.json"),
        },
    )
    write_verifier_result(result, result_path)
    return result


def _failure_result(
    task: CodeOptTask,
    *,
    started: float,
    terminal_status: TerminalStatus,
    infra_valid: bool,
    errors: Sequence[str],
    artifact_dir: Path,
    timed_out: bool = False,
    commands: Sequence[CommandExecution] = (),
) -> VerifierResult:
    result_path = artifact_dir / "holoskill_verifier.json"
    result = VerifierResult(
        task_id=task.task_id,
        correctness_before_pass=False,
        correctness_pass=False,
        edit_policy_pass=False,
        infra_valid=infra_valid,
        policy=PolicyEvidence(edit_policy_pass=False),
        timed_out=timed_out,
        wall_time_seconds=time.monotonic() - started,
        terminal_status=terminal_status,
        errors=list(errors),
        commands=list(commands),
        artifact_paths={"verifier_result": str(result_path)},
    )
    write_verifier_result(result, result_path)
    return result


def _command_succeeded(command: CommandExecution) -> bool:
    return command.exit_code == 0 and not command.timed_out and command.launch_error is None


def _command_failure(label: str, command: CommandExecution) -> str:
    if command.timed_out:
        return f"{label} timed out"
    if command.launch_error:
        return f"{label} could not launch: {command.launch_error}"
    return f"{label} exited with status {command.exit_code}"
