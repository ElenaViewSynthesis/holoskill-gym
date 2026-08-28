from __future__ import annotations

from holoskill_gym.privacy import scan_artifact_tree


def test_artifact_scan_reports_only_paths(tmp_path) -> None:
    secret = "sk-proj-secretvalue123456789"
    (tmp_path / "safe.json").write_text('{"status":"ok"}\n', encoding="utf-8")
    (tmp_path / "unsafe.json").write_text(secret, encoding="utf-8")

    findings = scan_artifact_tree(tmp_path, known_secret_values=[secret])

    assert findings == ["unsafe.json"]
    assert secret not in repr(findings)


def test_artifact_scan_skips_binary_files(tmp_path) -> None:
    (tmp_path / "binary.bin").write_bytes(b"\xff\xfesk-proj-secretvalue123456789")

    assert scan_artifact_tree(tmp_path) == []
