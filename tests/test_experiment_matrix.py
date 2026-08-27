from __future__ import annotations

import json
from pathlib import Path

from seagym.config import load_experiment_context

ROOT = Path(__file__).resolve().parents[1]
MATRIX_ROOT = ROOT / "examples" / "holo_skillopt_matrix"


def test_production_matrix_configs_load_and_keep_first_run_serial() -> None:
    matrix = json.loads((MATRIX_ROOT / "matrix.json").read_text(encoding="utf-8"))

    assert matrix["first_run_n_concurrent"] == 1
    assert all("low_cost" not in condition["id"] for condition in matrix["conditions"])
    for condition in matrix["conditions"]:
        config_path = MATRIX_ROOT / condition["config"]
        context = load_experiment_context(config_path)
        raw = context.config.raw
        assert raw["backend"]["name"] == "harbor"
        assert raw["backend"]["n_concurrent"] == 1
        assert "correct_speedup_geomean" in raw["metrics"]["primary"]
        assert "reliability_rates" in raw["metrics"]["primary"]
        assert "role_separated_spend" in raw["metrics"]["primary"]
        assert raw["metrics"]["cost"] == []
        assert all(
            Path(task.source["dataset_path"])
            .as_posix()
            .endswith("data/holoskill-codeopt-v1/observer")
            for task in context.task_index.tasks.values()
        )


def test_matrix_conditions_preserve_gate_and_transfer_semantics() -> None:
    configs = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in (MATRIX_ROOT / "configs").glob("*.json")
    }

    assert configs["codex_gated"]["baseline"]["config"]["gate_mode"] == "on"
    assert configs["claude_gated"]["baseline"]["config"]["gate_mode"] == "on"
    assert configs["codex_gate_off"]["baseline"]["config"]["gate_mode"] == "off"
    assert configs["codex_static"]["baseline"]["class_path"].endswith(":StaticSkillBaseline")
    assert configs["claude_static"]["baseline"]["class_path"].endswith(":StaticSkillBaseline")
    for name in ("codex_to_claude_transfer", "claude_to_codex_transfer"):
        transfer = configs[name]
        assert transfer["baseline"]["class_path"].endswith(":StaticSkillBaseline")
        executors = transfer["metrics"]["cross_harness_transfer"]
        assert executors["source_executor"] != executors["evaluation_executor"]
        assert "candidate_acceptance_rate" not in transfer["metrics"]["primary"]
