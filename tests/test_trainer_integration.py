from __future__ import annotations

import json
from pathlib import Path

import pytest
from seagym.cli import main as seagym_main
from seagym.utils import read_jsonl

from holoskill_gym.baseline import SkillOptHoloBaseline
from holoskill_gym.engine import SkillOptHoloEngine
from holoskill_gym.fakes import DeterministicHoloBackend

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "holo_skillopt_deterministic"


@pytest.fixture(scope="module")
def completed_run(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    workspace = tmp_path_factory.mktemp("trainer-integration")
    config_path = workspace / "config.json"
    config = json.loads((EXAMPLE / "config.json").read_text(encoding="utf-8"))
    config["experiment_id"] = "holo_skillopt_trainer_integration"
    config["task_dataset"]["path"] = str(EXAMPLE / "tasks" / "task_index.json")
    config["split_manifest"]["path"] = str(EXAMPLE / "splits" / "split.json")
    config["schedule"]["train_size"] = 1
    baseline = config["baseline"]["config"]
    baseline["initial_skill_path"] = str(EXAMPLE / "skills" / "initial_skill.md")
    baseline["skillopt_gate_path"] = str(EXAMPLE / "tasks" / "skillopt_gate.json")
    baseline["split_manifest_path"] = str(EXAMPLE / "splits" / "split.json")
    config["rollout_agent"]["config"]["fixture_root"] = str(ROOT / "fixtures")
    config["output"]["run_dir"] = str(workspace / "unused-config-run")
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    run_dir = workspace / "train-run"

    seagym_main(
        [
            "train",
            str(config_path),
            "--run-dir",
            str(run_dir),
            "--overwrite",
        ]
    )

    return config_path, run_dir


def test_completed_run_has_normalized_verifier_and_optimizer_cost_records(completed_run) -> None:
    _, run_dir = completed_run
    records = read_jsonl(run_dir / "records" / "metric_inputs.jsonl")
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    task_rows = [row for row in records if row.get("mode") != "update"]
    update_rows = [row for row in records if row.get("mode") == "update"]

    assert task_rows
    assert update_rows
    assert all(
        row["refs"]["extra"]["holoskill_gym"]["normalized_evidence"]["executor"]
        == "deterministic-codeopt-fixture"
        for row in task_rows
    )
    assert update_rows[0]["cost"] == {
        "input_tokens": 15,
        "output_tokens": 15,
        "total_tokens": 30,
    }
    assert metrics["candidate_acceptance_rate"]["value"] == 1.0
    assert metrics["gate_off_application_rate"]["private_gate_acceptance"] is False
    assert metrics["forbidden_edit_rate"]["value"] == 0.0
    assert metrics["reliability_rates"]["timeout_or_infra_failure_rate"] == 0.0
    assert metrics["correct_speedup_geomean"]["num_correct_runs"] > 0
    assert "tokens" not in metrics
    assert metrics["role_separated_spend"]["target"]["total_tokens"] == 0.0
    assert metrics["role_separated_spend"]["optimizer"]["total_tokens"] == 30.0
    assert "overall" not in metrics["role_separated_spend"]


def test_checkpoint_eval_never_invokes_optimizer_or_baseline_update(
    completed_run,
    monkeypatch,
    tmp_path,
) -> None:
    config_path, run_dir = completed_run

    def forbidden(*args, **kwargs):
        del args, kwargs
        raise AssertionError("checkpoint evaluation entered an optimizer/update path")

    monkeypatch.setattr(SkillOptHoloBaseline, "update", forbidden)
    monkeypatch.setattr(SkillOptHoloEngine, "reflect", forbidden)
    monkeypatch.setattr(DeterministicHoloBackend, "propose", forbidden)
    eval_dir = tmp_path / "eval-run"
    seagym_main(
        [
            "eval",
            str(config_path),
            "--checkpoint",
            str(run_dir / "checkpoints" / "final"),
            "--run-dir",
            str(eval_dir),
            "--overwrite",
        ]
    )

    update_path = eval_dir / "records" / "agent_updates.jsonl"
    assert not update_path.exists() or read_jsonl(update_path) == []
    records = read_jsonl(eval_dir / "records" / "metric_inputs.jsonl")
    assert records
    assert {row["mode"] for row in records} == {"checkpoint_eval"}


def test_final_checkpoint_resume_is_idempotent(completed_run) -> None:
    config_path, run_dir = completed_run
    stable_paths = [
        run_dir / "agent_state" / "skillopt_holo" / "state.json",
        run_dir / "agent_state" / "skillopt_holo" / "best_skill.md",
        run_dir / "metrics.json",
        run_dir / "reports" / "summary.md",
    ]
    before = {path: path.read_bytes() for path in stable_paths}
    updates_path = run_dir / "records" / "agent_updates.jsonl"
    metric_inputs_path = run_dir / "records" / "metric_inputs.jsonl"
    update_count = len(read_jsonl(updates_path))
    metric_input_count = len(read_jsonl(metric_inputs_path))

    seagym_main(
        [
            "train",
            str(config_path),
            "--run-dir",
            str(run_dir),
            "--resume",
        ]
    )

    assert len(read_jsonl(updates_path)) == update_count
    assert len(read_jsonl(metric_inputs_path)) == metric_input_count
    assert {path: path.read_bytes() for path in stable_paths} == before
