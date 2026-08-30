from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_required_harbor_override_is_bootstrapped() -> None:
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/bootstrap-vendor"), "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "v0.22.0 (4407eb5227a2ff4f0d3f16b2eb48849382fdf276)" in result.stdout
