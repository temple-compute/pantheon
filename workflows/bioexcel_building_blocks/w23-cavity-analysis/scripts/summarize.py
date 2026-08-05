#!/usr/bin/env python3
"""
Stage 3 (summarize) -- fan-in. Rank the models by their best cavity.

Reads the map's gathered folder (one numbered slot per ``analyze`` clone) and
writes the three sorted summaries the source workflow produces, ported from
``create_summary``/``sort_summary`` (cavity_analysis.py:155-241, 360-393):

    summary_by_volume.yml      models ordered by their largest cavity
    summary_by_drug_score.yml  models ordered by their most druggable cavity
    summary_by_score.yml       models ordered by their best-scoring cavity

Each is the *same* data in a different order: every model that kept at least one
cavity, with the fpocket metrics of the cavities that survived filtering. Three
orderings exist because the three metrics disagree, and which one matters
depends on what the cavity is for.

Usage:
    summarize.py --results analyze.gathered/ --out results/
    summarize.py --selftest
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

# (filename stem, fpocket metric) for each ordering the source workflow emits.
ORDERINGS = (
    ("summary_by_volume", "volume"),
    ("summary_by_drug_score", "druggability_score"),
    ("summary_by_score", "score"),
)


def best_metric(model_summary: dict, metric: str) -> float:
    """
    The best value of *metric* across a model's surviving cavities.

    Missing metrics sort last rather than raising: fpocket occasionally omits a
    score for a degenerate cavity, and losing the whole summary over one such
    cavity would be worse than ranking it bottom.
    """
    values = [
        pocket[metric]
        for name, pocket in model_summary.items()
        if name.startswith("pocket") and isinstance(pocket, dict) and metric in pocket
    ]
    return max(values) if values else float("-inf")


def collect(results: Path) -> tuple[dict, list[dict]]:
    """
    Walk the gathered slots. Returns ``(summary, attempted)``.

    ``summary`` maps model name -> its surviving cavities and their metrics.
    Models that kept no cavity are omitted, matching the source's
    ``if len(filtered_pocket_names) > 0`` guard.
    """
    summary: dict = {}
    attempted: list[dict] = []

    for slot in sorted(results.iterdir(), key=lambda p: p.name):
        if not slot.is_dir():
            continue
        for analyzed in [slot, *(p for p in slot.iterdir() if p.is_dir())]:
            status_path = analyzed / "status.json"
            if not status_path.exists():
                continue
            status = json.loads(status_path.read_text())
            attempted.append(status)

            pockets = status.get("pockets") or []
            all_metrics_path = analyzed / "summary.json"
            if not status.get("analyzed") or not pockets or not all_metrics_path.exists():
                break

            all_metrics = json.loads(all_metrics_path.read_text())
            model_summary = {
                name: all_metrics[name] for name in pockets if name in all_metrics
            }
            if model_summary:
                model_summary["pockets"] = pockets
                summary[status["model"]] = model_summary
            break

    return summary, attempted


def sort_summary(summary: dict, metric: str) -> dict:
    """Order models best-first by their best cavity's *metric*."""
    return dict(
        sorted(summary.items(), key=lambda item: best_metric(item[1], metric), reverse=True)
    )


def run(args: argparse.Namespace) -> dict:
    """Write the three sorted summaries plus a run report."""
    summary, attempted = collect(args.results)
    args.out.mkdir(parents=True, exist_ok=True)

    for stem, metric in ORDERINGS:
        (args.out / f"{stem}.yml").write_text(
            yaml.dump(sort_summary(summary, metric), sort_keys=False)
        )

    report = {
        "models_analyzed": len(attempted),
        "models_with_pockets": len(summary),
        "models_failed": sum(1 for s in attempted if not s.get("analyzed")),
        "total_pockets": sum(len(v["pockets"]) for v in summary.values()),
        "best_by": {
            metric: next(iter(sort_summary(summary, metric)), None)
            for _, metric in ORDERINGS
        },
        "failures": [
            {"model": s.get("model"), "stage": s.get("stage"), "error": s.get("error")}
            for s in attempted
            if not s.get("analyzed")
        ],
    }
    (args.out / "cavity_report.json").write_text(json.dumps(report, indent=2) + "\n")

    print(
        f"summarize.py: {report['models_with_pockets']}/{report['models_analyzed']} "
        f"model(s) with cavities, {report['total_pockets']} pocket(s) total"
    )
    return report


def _selftest() -> None:
    """Summarize a synthetic gathered tree, including a failed and an empty model."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        results = tmpdir / "analyze.gathered"

        def make_slot(index: int, status: dict, metrics: dict | None) -> None:
            slot = results / str(index)
            slot.mkdir(parents=True)
            (slot / "status.json").write_text(json.dumps(status))
            if metrics is not None:
                (slot / "summary.json").write_text(json.dumps(metrics))

        make_slot(
            0,
            {"model": "cluster0", "analyzed": True, "pockets": ["pocket1", "pocket2"]},
            {
                "pocket1": {"score": 0.9, "druggability_score": 0.2, "volume": 300},
                "pocket2": {"score": 0.1, "druggability_score": 0.8, "volume": 900},
                "pocket9": {"score": 9.9, "druggability_score": 9.9, "volume": 9999},
            },
        )
        make_slot(
            1,
            {"model": "cluster1", "analyzed": True, "pockets": ["pocket1"]},
            {"pocket1": {"score": 0.5, "druggability_score": 0.5, "volume": 5000}},
        )
        # Kept no cavity -> omitted from the summaries entirely.
        make_slot(2, {"model": "cluster2", "analyzed": True, "pockets": []}, {})
        # Failed outright -> counted as a failure, not a silent disappearance.
        make_slot(
            3,
            {"model": "cluster3", "analyzed": False, "stage": "fpocket_run", "error": "boom"},
            None,
        )

        out = tmpdir / "results"
        report = run(argparse.Namespace(results=results, out=out))

        assert report["models_analyzed"] == 4, report
        assert report["models_with_pockets"] == 2, report
        assert report["models_failed"] == 1, report
        assert report["total_pockets"] == 3, report

        by_volume = yaml.safe_load((out / "summary_by_volume.yml").read_text())
        by_drug = yaml.safe_load((out / "summary_by_drug_score.yml").read_text())
        by_score = yaml.safe_load((out / "summary_by_score.yml").read_text())

        # cluster1's single cavity is the largest (5000) and cluster0's best
        # score is the highest (0.9): the orderings genuinely disagree.
        assert list(by_volume) == ["cluster1", "cluster0"], by_volume
        assert list(by_score) == ["cluster0", "cluster1"], by_score
        assert list(by_drug) == ["cluster0", "cluster1"], by_drug
        assert report["best_by"]["volume"] == "cluster1"
        assert report["best_by"]["score"] == "cluster0"

        # Only the cavities that survived filtering are carried through --
        # pocket9 was in fpocket's summary but not in the kept list.
        assert set(by_volume["cluster0"]) == {"pocket1", "pocket2", "pockets"}, by_volume
        assert "cluster2" not in by_volume and "cluster3" not in by_volume

    print("summarize.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize gathered cavity analyses.")
    parser.add_argument("--results", type=Path, help="the map's gathered folder")
    parser.add_argument("--out", type=Path, help="output folder for the summaries")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        _selftest()
        return 0
    if not (args.results and args.out):
        parser.error("--results and --out are required")

    run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
