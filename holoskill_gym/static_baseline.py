"""Frozen-skill control and transfer-evaluation baseline."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from seagym.baselines import BaselineState, Checkpoint
from seagym.baselines.static import StaticBaseline

from .configuration import load_project_environment
from .state import skill_sha256


@dataclass
class StaticSkillBaseline(StaticBaseline):
    """Inject one immutable skill while retaining SEAGym's no-update control."""

    initial_skill_path: Path | None = None

    @classmethod
    def from_config(
        cls,
        *,
        name: str,
        config: dict[str, Any],
        models: dict[str, Any],
        state_dir: Path,
        run_dir: Path,
        base_dir: Path | None,
    ) -> StaticSkillBaseline:
        del models, run_dir
        load_project_environment(config.get("env_file"))
        value = config.get("initial_skill_path")
        if value in (None, ""):
            raise ValueError("StaticSkillBaseline requires initial_skill_path")
        path = Path(str(value))
        if not path.is_absolute() and base_dir is not None:
            path = base_dir / path
        return cls(
            baseline_id=name,
            state_dir=state_dir,
            initial_skill_path=path.resolve(),
        )

    def initialize(self, run_dir: Path) -> BaselineState:
        del run_dir
        if self.initial_skill_path is None:
            raise ValueError("initial_skill_path is required")
        skill = self.initial_skill_path.read_text(encoding="utf-8")
        self.state_dir.mkdir(parents=True, exist_ok=True)
        skill_path = self.state_dir / "best_skill.md"
        if skill_path.exists() and skill_path.read_text(encoding="utf-8") != skill:
            raise ValueError("existing static skill differs from configured initial skill")
        skill_path.write_text(skill, encoding="utf-8")
        metadata = self._metadata(skill_path)
        (self.state_dir / "baseline_state.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return BaselineState(self.state_dir, metadata)

    def load_checkpoint(self, checkpoint: Checkpoint) -> BaselineState:
        state = super().load_checkpoint(checkpoint)
        skill_path = self.state_dir / "best_skill.md"
        if not skill_path.exists():
            raise FileNotFoundError("checkpoint does not contain best_skill.md")
        state.metadata.update(self._metadata(skill_path))
        return state

    def _metadata(self, skill_path: Path) -> dict[str, Any]:
        skill = skill_path.read_text(encoding="utf-8")
        return {
            "baseline_id": self.baseline_id,
            "type": self.__class__.__name__,
            "static_skill": True,
            "skill_sha256": skill_sha256(skill),
            "prompt_template_path": str(skill_path.resolve()),
        }
