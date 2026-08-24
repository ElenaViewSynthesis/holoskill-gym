import pytest
from pydantic import ValidationError

from holoskill_gym.tasks import CodeOptTask, verify_edit_policy


def task() -> CodeOptTask:
    return CodeOptTask(
        task_id="prefix-cache-1",
        repo_url="https://example.invalid/repo.git",
        commit="a" * 40,
        objective="Improve prefix cache throughput.",
        language="python",
        runtime="python3.12",
        setup_argv=["python", "-m", "pip", "install", "-e", ".[test]"],
        test_argv=["python", "-m", "pytest", "-q"],
        benchmark_argv=["python", "bench.py", "--json"],
        benchmark_metric="requests_per_second",
        optimization_direction="maximize",
        timeout_seconds=900,
        forbidden_globs=["tests/**", "benchmarks/**"],
        max_changed_files=2,
    )


def test_forbidden_files_and_change_limit_invalidate_solution() -> None:
    forbidden = verify_edit_policy(task(), ["src/cache.py", "tests/test_cache.py"])
    assert forbidden.passed is False
    assert forbidden.forbidden_files == ["tests/test_cache.py"]

    too_many = verify_edit_policy(task(), ["a.py", "b.py", "c.py"])
    assert too_many.passed is False
    assert too_many.too_many_files is True


def test_task_requires_pinned_commit_and_argument_arrays() -> None:
    data = task().model_dump()
    data["commit"] = "main"
    with pytest.raises(ValidationError, match="full 40-character"):
        CodeOptTask.model_validate(data)
    with pytest.raises(ValidationError):
        CodeOptTask.model_validate({**task().model_dump(), "test_argv": []})


def test_changed_paths_must_be_repository_relative() -> None:
    with pytest.raises(ValueError, match="repository-relative"):
        verify_edit_policy(task(), ["../outside.txt"])
