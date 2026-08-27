from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from holoskill_gym.tasks import CodeOptTask
from holoskill_gym.verifier import (
    MAX_COMMAND_OUTPUT_BYTES,
    VerifierConfig,
    run_command,
    verifier_result_from_trajectory,
    verify_code_optimization,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "repositories"
SOLUTIONS = ROOT / "fixtures" / "solutions"


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _repository(tmp_path: Path, name: str) -> tuple[Path, str]:
    repo = tmp_path / name
    shutil.copytree(FIXTURES / name, repo)
    _git(repo, "init", "--quiet")
    _git(repo, "config", "user.name", "HoloSkill Fixture")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "add", ".")
    _git(repo, "commit", "--quiet", "-m", "fixture baseline")
    return repo, _git(repo, "rev-parse", "HEAD")


def _task(repo: Path, commit: str, *, direction: str, metric: str) -> CodeOptTask:
    return CodeOptTask(
        task_id=repo.name,
        repo_url=str(repo),
        commit=commit,
        objective="Improve the deterministic benchmark without changing behavior.",
        language="python",
        runtime="python",
        setup_argv=[],
        test_argv=[sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        benchmark_argv=[sys.executable, "benchmark.py"],
        benchmark_metric=metric,
        optimization_direction=direction,
        timeout_seconds=10,
        forbidden_globs=["tests/**", "benchmark.py", ".git/**"],
        max_changed_files=2,
    )


@pytest.mark.parametrize(
    ("name", "solution", "direction", "metric"),
    [
        (
            "minimize_comparisons",
            "minimize_comparisons_workload.py",
            "minimize",
            "latency_comparison_units",
        ),
        (
            "maximize_throughput",
            "maximize_throughput_workload.py",
            "maximize",
            "throughput_units",
        ),
    ],
)
def test_verifier_executes_checked_in_repository_fixtures(
    tmp_path,
    name,
    solution,
    direction,
    metric,
) -> None:
    repo, commit = _repository(tmp_path, name)
    shutil.copyfile(SOLUTIONS / solution, repo / "src" / "workload.py")
    task = _task(repo, commit, direction=direction, metric=metric)

    result = verify_code_optimization(
        task,
        repo_path=repo,
        artifact_dir=tmp_path / f"{name}-artifacts",
        config=VerifierConfig(benchmark_warmups=1, benchmark_samples=3),
    )

    assert result.infra_valid is True
    assert result.correctness_before_pass is True
    assert result.correctness_pass is True
    assert result.edit_policy_pass is True
    assert result.terminal_status == "success"
    assert result.benchmark.before_samples
    assert result.benchmark.after_samples
    assert result.benchmark.speedup is not None
    assert result.benchmark.speedup > 1
    assert result.changed_files == ["src/workload.py"]
    assert result.diff.files_changed == 1
    assert result.patch_sha256 is not None
    assert Path(result.artifact_paths["verifier_result"]).exists()
    assert result.reward_metrics()["infra_valid"] == 1

    trajectory = SimpleNamespace(
        refs={"extra": {"holoskill_gym": {"verifier_result": result.model_dump(mode="json")}}}
    )
    gate_score = verifier_result_from_trajectory(trajectory).to_gate_task_score()
    assert gate_score.correctness_pass is True
    assert gate_score.edit_policy_pass is True
    assert gate_score.speedup == result.benchmark.speedup


def test_protected_edit_fails_before_final_tests(tmp_path) -> None:
    repo, commit = _repository(tmp_path, "minimize_comparisons")
    test_file = repo / "tests" / "test_workload.py"
    test_file.write_text(test_file.read_text() + "\n# tampered\n", encoding="utf-8")
    task = _task(
        repo,
        commit,
        direction="minimize",
        metric="latency_comparison_units",
    )

    result = verify_code_optimization(
        task,
        repo_path=repo,
        artifact_dir=tmp_path / "policy-artifacts",
        config=VerifierConfig(benchmark_warmups=0, benchmark_samples=1),
    )

    assert result.infra_valid is True
    assert result.edit_policy_pass is False
    assert result.policy.forbidden_edit is True
    assert result.terminal_status == "policy_failure"
    assert all(command.label != "final_test" for command in result.commands)


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group lifecycle assertion")
def test_fake_executable_timeout_terminates_process_group_and_bounds_logs(tmp_path) -> None:
    executable = tmp_path / "fake_agent.py"
    executable.write_text(
        """from pathlib import Path
import subprocess
import sys
import time

child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
Path(sys.argv[1]).write_text(str(child.pid), encoding="utf-8")
sys.stdout.write("o" * 300_000)
sys.stdout.flush()
sys.stderr.write("e" * 300_000)
sys.stderr.flush()
time.sleep(60)
""",
        encoding="utf-8",
    )
    child_pid_path = tmp_path / "child.pid"

    result = run_command(
        [sys.executable, str(executable), str(child_pid_path)],
        cwd=tmp_path,
        timeout_seconds=0.5,
        artifact_dir=tmp_path / "artifacts",
        label="fake_agent",
        process_group_grace_seconds=0.1,
    )

    assert result.timed_out is True
    assert result.timeout_reason == "command exceeded 0.5 seconds"
    assert result.exit_code is not None
    assert Path(result.stdout_path).stat().st_size == MAX_COMMAND_OUTPUT_BYTES
    assert Path(result.stderr_path).stat().st_size == MAX_COMMAND_OUTPUT_BYTES
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 3
    while _process_is_live(child_pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert _process_is_live(child_pid) is False


def test_fake_executable_launch_failure_is_structured(tmp_path) -> None:
    result = run_command(
        [str(tmp_path / "missing-agent")],
        cwd=tmp_path,
        timeout_seconds=1,
        artifact_dir=tmp_path / "artifacts",
        label="missing_agent",
    )

    assert result.exit_code is None
    assert result.timed_out is False
    assert result.launch_error is not None
    assert result.launch_error.startswith("FileNotFoundError:")


def _process_is_live(pid: int) -> bool:
    stat_path = Path(f"/proc/{pid}/stat")
    try:
        state = stat_path.read_text(encoding="utf-8").split()[2]
    except (FileNotFoundError, IndexError, PermissionError):
        return False
    return state != "Z"
