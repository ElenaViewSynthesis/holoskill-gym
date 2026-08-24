"""Fail-closed split validation for method-private and observer-only tasks."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class LeakageError(ValueError):
    """Raised when task evidence crosses an allowed split boundary."""


@dataclass(frozen=True)
class LeakageGuard:
    """Own the exact task IDs visible to SkillOpt reflection and its private gate."""

    train_ids: frozenset[str]
    gate_ids: frozenset[str]
    observer_ids: dict[str, frozenset[str]]

    def __post_init__(self) -> None:
        if not self.train_ids:
            raise LeakageError("skillopt_train must contain at least one task")
        if not self.gate_ids:
            raise LeakageError("skillopt_gate must contain at least one task")
        named = {
            "skillopt_train": self.train_ids,
            "skillopt_gate": self.gate_ids,
            **self.observer_ids,
        }
        names = list(named)
        for index, left_name in enumerate(names):
            for right_name in names[index + 1 :]:
                # Replay intentionally revisits exposed training tasks. It is still
                # observer-only and can never enter update(), but overlap with train
                # is an expected forgetting diagnostic rather than leakage.
                if {left_name, right_name} == {"skillopt_train", "seagym_replay"}:
                    continue
                overlap = named[left_name] & named[right_name]
                if overlap:
                    preview = ", ".join(sorted(overlap)[:3])
                    raise LeakageError(
                        f"split overlap between {left_name} and {right_name}: {preview}"
                    )

    @classmethod
    def from_files(cls, *, split_manifest_path: Path, gate_path: Path) -> LeakageGuard:
        manifest = _load_json(split_manifest_path)
        if not isinstance(manifest, dict):
            raise LeakageError("split manifest must be a JSON object")
        train_ids = _ids_for_keys(manifest, "skillopt_train", "train")
        observer_ids: dict[str, frozenset[str]] = {}
        aliases = {
            "seagym_update_val": ("seagym_update_val", "val", "validation"),
            "seagym_test_id": ("seagym_test_id", "test", "test_id"),
            "seagym_test_ood": ("seagym_test_ood", "test_ood", "ood"),
            "seagym_replay": ("seagym_replay", "replay"),
        }
        for canonical, keys in aliases.items():
            values = _ids_for_keys(manifest, *keys, required=False)
            if values:
                observer_ids[canonical] = values
        return cls(
            train_ids=train_ids,
            gate_ids=_extract_task_ids(_load_json(gate_path), source=gate_path),
            observer_ids=observer_ids,
        )

    def assert_training_batch(self, *, task_ids: list[str], view_name: str, mode: str) -> None:
        if view_name != "train" or mode != "train":
            raise LeakageError(
                f"SkillOpt update accepts only train/train batches, got {view_name}/{mode}"
            )
        supplied = frozenset(task_ids)
        if not supplied:
            raise LeakageError("SkillOpt update received an empty training batch")
        unknown = supplied - self.train_ids
        if unknown:
            preview = ", ".join(sorted(unknown)[:3])
            raise LeakageError(f"update batch contains non-training task IDs: {preview}")

    def assert_gate_ids(self, task_ids: list[str]) -> None:
        supplied = frozenset(task_ids)
        if supplied != self.gate_ids:
            missing = sorted(self.gate_ids - supplied)
            extra = sorted(supplied - self.gate_ids)
            raise LeakageError(f"private gate task mismatch; missing={missing}, extra={extra}")

    def split_hashes(self) -> dict[str, str]:
        values = {
            "skillopt_train": self.train_ids,
            "skillopt_gate": self.gate_ids,
            **self.observer_ids,
        }
        return {name: _hash_ids(task_ids) for name, task_ids in sorted(values.items())}


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LeakageError(f"cannot load split data from {path}: {type(exc).__name__}") from exc


def _ids_for_keys(data: dict[str, Any], *keys: str, required: bool = True) -> frozenset[str]:
    containers = [data]
    for wrapper in ("splits", "views"):
        value = data.get(wrapper)
        if isinstance(value, dict):
            containers.append(value)
    for container in containers:
        for key in keys:
            if key in container:
                return _extract_task_ids(container[key], source=key)
    if required:
        raise LeakageError(f"split manifest is missing one of: {', '.join(keys)}")
    return frozenset()


def _extract_task_ids(data: Any, *, source: object) -> frozenset[str]:
    if isinstance(data, dict):
        for key in ("task_ids", "tasks", "records"):
            if key in data:
                return _extract_task_ids(data[key], source=source)
    if isinstance(data, list):
        ids: list[str] = []
        for item in data:
            value = item.get("task_id") if isinstance(item, dict) else item
            if not isinstance(value, str) or not value.strip():
                raise LeakageError(f"invalid task ID in {source}")
            ids.append(value)
        if len(ids) != len(set(ids)):
            raise LeakageError(f"duplicate task IDs in {source}")
        return frozenset(ids)
    raise LeakageError(f"expected task ID list in {source}")


def _hash_ids(task_ids: frozenset[str]) -> str:
    payload = json.dumps(sorted(task_ids), separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()
