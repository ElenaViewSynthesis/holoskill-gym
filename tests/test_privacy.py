from __future__ import annotations

from holoskill_gym.privacy import (
    load_known_secret_values,
    redact_sensitive_value,
    sanitize_failure_logs,
    scan_artifact_tree,
)


def test_known_secrets_are_loaded_consistently_without_mutating_environment(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OPENAI_API_KEY=opaque-openai-value\nHAI_API_KEY='opaque-holo-value'\n",
        encoding="utf-8",
    )
    environ = {"OPENAI_API_KEY": "environment-wins"}

    assert load_known_secret_values(env_file, environ=environ) == (
        "environment-wins",
        "opaque-holo-value",
    )
    assert environ == {"OPENAI_API_KEY": "environment-wins"}


def test_artifact_scan_reports_only_paths(tmp_path) -> None:
    secret = "sk-proj-secretvalue123456789"
    (tmp_path / "safe.json").write_text('{"status":"ok"}\n', encoding="utf-8")
    (tmp_path / "unsafe.json").write_text(secret, encoding="utf-8")

    findings = scan_artifact_tree(tmp_path, known_secret_values=[secret])

    assert findings == ["unsafe.json"]
    assert secret not in repr(findings)


def test_artifact_scan_catches_binary_and_chunk_spanning_secrets(tmp_path) -> None:
    (tmp_path / "binary.bin").write_bytes(b"\xff\xfesk-proj-secretvalue123456789")
    (tmp_path / "large.log").write_bytes(b"x" * 9 + b"\nBearer secret-value-12345")

    assert scan_artifact_tree(tmp_path, max_file_bytes=16) == ["binary.bin", "large.log"]


def test_nested_sensitive_keys_are_redacted_even_for_unshaped_values() -> None:
    value = {"nested": {"authorization": "opaque", "safe": "visible"}, "api_key": "short"}
    assert redact_sensitive_value(value) == {
        "nested": {"authorization": "[REDACTED]", "safe": "visible"},
        "api_key": "[REDACTED]",
    }


def test_failure_logs_are_bounded_redacted_and_keep_relative_paths(tmp_path) -> None:
    source = tmp_path / "jobs"
    log = source / "job" / "trial" / "trial.log"
    log.parent.mkdir(parents=True)
    secret = "sk-proj-secretvalue123456789"
    log.write_text("prefix\n" + secret + "\n" + "x" * 100, encoding="utf-8")
    (log.parent / "result.json").write_text(secret, encoding="utf-8")

    destination = tmp_path / "sanitized"
    written = sanitize_failure_logs(source, destination, max_log_bytes=80)

    assert written == ["job/trial/trial.log"]
    retained = (destination / written[0]).read_text(encoding="utf-8")
    assert secret not in retained
    assert len(retained.encode()) <= 80
    assert not (destination / "job/trial/result.json").exists()


def test_failure_logs_redact_exact_unshaped_secret_values(tmp_path) -> None:
    source = tmp_path / "jobs"
    log = source / "job" / "stderr.txt"
    log.parent.mkdir(parents=True)
    secret = "opaque-value-with-no-credential-shape"
    log.write_text(f"provider returned {secret}\n", encoding="utf-8")

    destination = tmp_path / "sanitized"
    sanitize_failure_logs(source, destination, known_secret_values=[secret])

    assert secret not in (destination / "job" / "stderr.txt").read_text(encoding="utf-8")
    assert scan_artifact_tree(destination, known_secret_values=[secret]) == []
