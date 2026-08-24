"""Validated, shell-safe code-optimization task contracts."""

from __future__ import annotations

import fnmatch
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class CodeOptTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1)
    repo_url: str = Field(min_length=1)
    commit: str
    objective: str = Field(min_length=1)
    language: str = Field(min_length=1)
    runtime: str = Field(min_length=1)
    setup_argv: list[str]
    test_argv: list[str] = Field(min_length=1)
    benchmark_argv: list[str] = Field(min_length=1)
    benchmark_metric: str = Field(min_length=1)
    optimization_direction: Literal["minimize", "maximize"]
    timeout_seconds: int = Field(gt=0)
    forbidden_globs: list[str] = Field(default_factory=list)
    max_changed_files: int = Field(default=12, ge=0)
    tags: list[str] = Field(default_factory=list)

    @field_validator("commit")
    @classmethod
    def require_full_commit(cls, value: str) -> str:
        if not _COMMIT_RE.fullmatch(value):
            raise ValueError("commit must be a full 40-character lowercase SHA-1")
        return value

    @field_validator("setup_argv", "test_argv", "benchmark_argv")
    @classmethod
    def require_safe_argv(cls, value: list[str]) -> list[str]:
        if any(not isinstance(item, str) or not item or "\x00" in item for item in value):
            raise ValueError("command arguments must be non-empty strings without NUL bytes")
        return value


class EditPolicyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    changed_files: list[str]
    forbidden_files: list[str]
    too_many_files: bool


def verify_edit_policy(task: CodeOptTask, changed_files: list[str]) -> EditPolicyResult:
    """Check repository-relative changed paths without invoking a shell."""

    normalized: list[str] = []
    for path in changed_files:
        candidate = path.replace("\\", "/").removeprefix("./")
        if candidate.startswith(("/", "../")) or candidate == "..":
            raise ValueError(f"changed file must be repository-relative: {path}")
        normalized.append(candidate)
    forbidden = sorted(
        {
            path
            for path in normalized
            if any(fnmatch.fnmatchcase(path, pattern) for pattern in task.forbidden_globs)
        }
    )
    too_many = len(set(normalized)) > task.max_changed_files
    return EditPolicyResult(
        passed=not forbidden and not too_many,
        changed_files=sorted(set(normalized)),
        forbidden_files=forbidden,
        too_many_files=too_many,
    )
