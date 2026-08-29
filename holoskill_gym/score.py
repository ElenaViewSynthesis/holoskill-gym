"""Terminal entry point for aggregating speedups under either mean.

    python -m holoskill_gym.score --run-dir results/runs/<run>
    python -m holoskill_gym.score --speedups 1.4 0.9 3.2 --statistic both

The geometric mean is this project's own aggregate; the harmonic mean is
AlgoTune's ``AlgoTune Score``. They are not interchangeable, so this command
prints both by default and reports their ratio: a harmonic mean well below the
geometric mean means the gain is concentrated in a few tasks rather than broad.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .metrics import geometric_mean_speedup, harmonic_mean_speedup

STATISTICS = ("harmonic", "geometric", "both")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m holoskill_gym.score",
        description="Aggregate per-task speedups under the harmonic or geometric mean.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--run-dir",
        type=Path,
        help="Run directory containing records/*.jsonl to read speedups from.",
    )
    source.add_argument(
        "--speedups",
        type=float,
        nargs="+",
        metavar="X",
        help="Explicit speedup values, for a quick check without a run.",
    )
    parser.add_argument(
        "--statistic",
        choices=STATISTICS,
        default="both",
        help="Which aggregate to report (default: both, plus their ratio).",
    )
    parser.add_argument(
        "--mercy-score",
        type=float,
        default=1.0,
        help=(
            "AlgoTune's floor for a failed or slower-than-baseline task; values "
            "below it are raised to it. Pass 0 to let a failure zero the "
            "aggregate (default: 1.0)."
        ),
    )
    parser.add_argument(
        "--view",
        default=None,
        help="Restrict to one evaluation view (for example train or id_test).",
    )
    parser.add_argument("--json", action="store_true", help="Emit the result as JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.mercy_score < 0:
        raise SystemExit("--mercy-score must be non-negative")

    if args.speedups is not None:
        speedups = list(args.speedups)
        source = "argv"
    else:
        speedups = _speedups_from_run(args.run_dir, view=args.view)
        source = str(args.run_dir)
        if not speedups:
            raise SystemExit(f"no correct, valid speedups found in {source}")

    report: dict[str, Any] = {
        "source": source,
        "view": args.view,
        "num_speedups": len(speedups),
        "mercy_score": args.mercy_score,
    }
    if args.statistic in ("harmonic", "both"):
        report["harmonic_mean"] = harmonic_mean_speedup(speedups, mercy_score=args.mercy_score)
    if args.statistic in ("geometric", "both"):
        report["geometric_mean"] = geometric_mean_speedup(speedups)
    if args.statistic == "both" and report["geometric_mean"] > 0:
        report["harmonic_over_geometric"] = report["harmonic_mean"] / report["geometric_mean"]

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    print(f"source        : {report['source']}")
    if args.view:
        print(f"view          : {args.view}")
    print(f"speedups      : {report['num_speedups']}")
    if "harmonic_mean" in report:
        print(f"harmonic mean : {report['harmonic_mean']:.4f}   (AlgoTune Score)")
    if "geometric_mean" in report:
        print(f"geometric mean: {report['geometric_mean']:.4f}   (project aggregate)")
    if "harmonic_over_geometric" in report:
        ratio = report["harmonic_over_geometric"]
        print(f"ratio H/G     : {ratio:.4f}")
        if ratio < 0.9:
            print("  note: harmonic well below geometric -- gains are concentrated,")
            print("        not broad. Check the per-task spread before claiming a win.")
    return 0


def _speedups_from_run(run_dir: Path, *, view: str | None) -> list[float]:
    """Collect speedups from correct, infrastructure-valid task records."""

    records_dir = run_dir / "records"
    if not records_dir.is_dir():
        raise SystemExit(f"no records directory under {run_dir}")
    speedups: list[float] = []
    for path in sorted(records_dir.rglob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if view is not None and row.get("view_name") != view:
                continue
            evidence = _evidence(row)
            if evidence is None or not evidence.get("correctness_pass"):
                continue
            if evidence.get("infra_valid") is False:
                continue
            speedup = (evidence.get("benchmark") or {}).get("speedup")
            if isinstance(speedup, int | float) and speedup > 0:
                speedups.append(float(speedup))
    return speedups


def _evidence(row: dict[str, Any]) -> dict[str, Any] | None:
    refs = row.get("refs")
    if not isinstance(refs, dict):
        return None
    extra = refs.get("extra")
    if not isinstance(extra, dict):
        return None
    project = extra.get("holoskill_gym")
    if not isinstance(project, dict):
        return None
    for key in ("verifier_result", "normalized_evidence"):
        candidate = project.get(key)
        if isinstance(candidate, dict):
            return candidate
    return None


if __name__ == "__main__":
    raise SystemExit(main())
