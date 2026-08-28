"""Durable, hash-verified method state for SkillOpt/Holo baselines."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .schemas import GateDecision, OptimizerUsage

STATE_SCHEMA_VERSION = "1"


class StateIntegrityError(RuntimeError):
    """Raised when persisted skill bytes do not match state metadata."""


class SkillOptState(BaseModel):
    """Serializable state required to resume without an optimizer call."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = STATE_SCHEMA_VERSION
    skill_version: int = Field(default=0, ge=0)
    current_hash: str
    parent_hash: str | None = None
    skillopt_version: str
    skillopt_commit: str
    seagym_version: str
    seagym_commit: str
    holo_model_id: str
    optimizer_prompt_hash: str
    target_executor: str
    gate_mode: Literal["on", "off"]
    task_split_hashes: dict[str, str]
    accepted_count: int = Field(default=0, ge=0)
    rejected_count: int = Field(default=0, ge=0)
    cumulative_optimizer_usage: OptimizerUsage = Field(default_factory=OptimizerUsage)
    latest_update_status: str = "initialized"
    last_committed_update: int = Field(default=0, ge=0)
    best_score: float | None = None
    best_step: int = Field(default=0, ge=0)


class StateStore:
    """Persist deployed state through a replayable write-ahead transaction."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir.resolve()
        self.skill_path = self.state_dir / "best_skill.md"
        self.state_path = self.state_dir / "state.json"
        self.rejected_path = self.state_dir / "rejected_edits.jsonl"
        self.history_path = self.state_dir / "update_history.jsonl"
        self.transaction_path = self.state_dir / "pending_commit.json"

    def initialize(self, *, initial_skill: str, metadata: dict[str, Any]) -> SkillOptState:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        if self.state_path.exists() or self.skill_path.exists():
            return self.load()
        state = SkillOptState(current_hash=skill_sha256(initial_skill), **metadata)
        _atomic_write_text(self.skill_path, initial_skill)
        _atomic_write_text(self.rejected_path, "")
        _atomic_write_text(self.history_path, "")
        self._write_state(state)
        return state

    def load(self) -> SkillOptState:
        self._recover_pending_commit()
        return self._load_verified()

    def _load_verified(self) -> SkillOptState:
        try:
            state = SkillOptState.model_validate_json(self.state_path.read_text(encoding="utf-8"))
            skill = self.skill_path.read_text(encoding="utf-8")
        except (OSError, ValueError) as exc:
            raise StateIntegrityError(f"cannot load baseline state: {type(exc).__name__}") from exc
        actual = skill_sha256(skill)
        if actual != state.current_hash:
            raise StateIntegrityError(
                f"deployed skill hash mismatch: state={state.current_hash}, actual={actual}"
            )
        return state

    def read_skill(self) -> str:
        state = self.load()
        skill = self.skill_path.read_text(encoding="utf-8")
        if skill_sha256(skill) != state.current_hash:  # defensive against an intervening write
            raise StateIntegrityError("deployed skill changed while it was being read")
        return skill

    def commit(
        self,
        *,
        prior: SkillOptState,
        update_index: int,
        deployed_skill: str,
        status: str,
        optimizer_usage: OptimizerUsage,
        gate_decision: GateDecision | None,
        proposal_record: dict[str, Any] | None,
    ) -> SkillOptState:
        current = self.load()
        if (
            current.current_hash != prior.current_hash
            or current.last_committed_update != prior.last_committed_update
        ):
            raise StateIntegrityError("state changed since this update began")
        if update_index <= current.last_committed_update:
            raise StateIntegrityError(f"update {update_index} was already committed")

        current_skill = self.read_skill()
        changed = deployed_skill != current_skill
        accepted = bool(gate_decision and gate_decision.accepted and changed)
        rejected = bool(gate_decision and not gate_decision.accepted)
        cumulative = _add_usage(prior.cumulative_optimizer_usage, optimizer_usage)
        new_hash = skill_sha256(deployed_skill)
        next_state = prior.model_copy(
            update={
                "skill_version": prior.skill_version + int(changed),
                "current_hash": new_hash,
                "parent_hash": prior.current_hash if changed else prior.parent_hash,
                "accepted_count": prior.accepted_count + int(accepted),
                "rejected_count": prior.rejected_count + int(rejected),
                "cumulative_optimizer_usage": cumulative,
                "latest_update_status": status,
                "last_committed_update": update_index,
                "best_score": (gate_decision.candidate_score if accepted else prior.best_score),
                "best_step": update_index if accepted else prior.best_step,
            }
        )
        history = {
            "update_index": update_index,
            "status": status,
            "changed": changed,
            "skill_version": next_state.skill_version,
            "parent_hash": next_state.parent_hash,
            "current_hash": next_state.current_hash,
            "gate": None if gate_decision is None else gate_decision.model_dump(),
            "optimizer_usage": optimizer_usage.model_dump(),
        }
        history_content = _appended_jsonl(self.history_path, history)
        rejected_content = self.rejected_path.read_text(encoding="utf-8")
        if rejected and proposal_record is not None:
            rejected_content = _appended_jsonl(
                self.rejected_path, {"update_index": update_index, "proposal": proposal_record}
            )
        transaction = {
            "schema_version": "1",
            "prior_current_hash": prior.current_hash,
            "prior_last_committed_update": prior.last_committed_update,
            "deployed_skill": deployed_skill,
            "history_content": history_content,
            "rejected_content": rejected_content,
            "next_state": next_state.model_dump(mode="json"),
        }
        _atomic_write_text(
            self.transaction_path,
            json.dumps(transaction, indent=2, sort_keys=True) + "\n",
        )
        self._apply_transaction(transaction)
        _atomic_unlink(self.transaction_path)
        return next_state

    def _write_state(self, state: SkillOptState) -> None:
        _atomic_write_text(
            self.state_path,
            json.dumps(state.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        )

    def _recover_pending_commit(self) -> None:
        if not self.transaction_path.exists():
            return
        try:
            transaction = json.loads(self.transaction_path.read_text(encoding="utf-8"))
            if transaction.get("schema_version") != "1":
                raise ValueError("unsupported transaction schema")
            next_state = SkillOptState.model_validate(transaction["next_state"])
            current_state = SkillOptState.model_validate_json(
                self.state_path.read_text(encoding="utf-8")
            )
            prior_identity = (
                transaction["prior_current_hash"],
                int(transaction["prior_last_committed_update"]),
            )
            current_identity = (
                current_state.current_hash,
                current_state.last_committed_update,
            )
            next_identity = (next_state.current_hash, next_state.last_committed_update)
            if current_identity not in {prior_identity, next_identity}:
                raise ValueError("state does not match transaction endpoints")
            if skill_sha256(str(transaction["deployed_skill"])) != next_state.current_hash:
                raise ValueError("transaction skill hash mismatch")
        except (KeyError, OSError, TypeError, ValueError) as exc:
            raise StateIntegrityError(
                f"cannot recover pending state transaction: {type(exc).__name__}"
            ) from exc
        self._apply_transaction(transaction)
        _atomic_unlink(self.transaction_path)

    def _apply_transaction(self, transaction: dict[str, Any]) -> None:
        next_state = SkillOptState.model_validate(transaction["next_state"])
        _atomic_write_text(self.skill_path, str(transaction["deployed_skill"]))
        _atomic_write_text(self.history_path, str(transaction["history_content"]))
        _atomic_write_text(self.rejected_path, str(transaction["rejected_content"]))
        self._write_state(next_state)


def skill_sha256(skill: str) -> str:
    return hashlib.sha256(skill.encode("utf-8")).hexdigest()


def prompt_sha256(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _add_usage(left: OptimizerUsage, right: OptimizerUsage) -> OptimizerUsage:
    return OptimizerUsage(
        prompt_tokens=left.prompt_tokens + right.prompt_tokens,
        completion_tokens=left.completion_tokens + right.completion_tokens,
        total_tokens=left.total_tokens + right.total_tokens,
    )


def _appended_jsonl(path: Path, record: dict[str, Any]) -> str:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
    return existing + line


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        if hasattr(os, "O_DIRECTORY"):
            directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _atomic_unlink(path: Path) -> None:
    path.unlink()
    if hasattr(os, "O_DIRECTORY"):
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
