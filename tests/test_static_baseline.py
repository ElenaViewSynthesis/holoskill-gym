from __future__ import annotations

from pathlib import Path

from seagym.baselines import Checkpoint

from holoskill_gym.static_baseline import StaticSkillBaseline


def test_static_skill_baseline_injects_and_restores_frozen_skill(tmp_path) -> None:
    source = tmp_path / "initial.md"
    source.write_text("# Skill\n\nKeep this frozen.\n", encoding="utf-8")
    baseline = StaticSkillBaseline.from_config(
        name="static-control",
        config={"initial_skill_path": str(source)},
        models={},
        state_dir=tmp_path / "state",
        run_dir=tmp_path / "run",
        base_dir=None,
    )
    state = baseline.initialize(tmp_path / "run")
    checkpoint = baseline.save_checkpoint(state, tmp_path / "checkpoint")
    (baseline.state_dir / "best_skill.md").write_text("changed", encoding="utf-8")

    restored = baseline.load_checkpoint(Checkpoint(checkpoint.checkpoint_dir))

    restored_path = Path(restored.metadata["prompt_template_path"])
    assert restored_path == baseline.state_dir / "best_skill.md"
    assert restored_path.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
    assert restored.metadata["static_skill"] is True
