#!/usr/bin/env python3
"""
Stage 3 (rank) — turn OpenDDE predictions into a ranked shortlist.

Untars the predictions archive, finds every
``<job>_summary_confidence_sample_<n>.json`` OpenDDE wrote, keeps the best
sample per job (highest ``ranking_score``) and writes ``top_hits.csv`` sorted
best-first.

Ranking note (see README): OpenDDE has no affinity head. We sort by ``iptm``
(interface confidence, descending), tie-breaking on ``ranking_score``. This is
a structural-confidence proxy for "does this ligand sit in a well-defined
pose", NOT a binding-affinity prediction.

stdlib only.

Usage:
    rank.py --predictions predictions.tar.gz --out top_hits.csv
    rank.py --selftest
"""

import argparse
import csv
import json
import sys
import tarfile
import tempfile
from pathlib import Path

_MARKER = "_summary_confidence_sample_"


def _num(value: object) -> float | None:
    """Coerce *value* to float, or None if it isn't a number."""
    if isinstance(value, bool):
        return None
    return float(value) if isinstance(value, (int, float)) else None


def collect_hits(pred_dir: Path) -> list[dict[str, object]]:
    """Scan *pred_dir* for OpenDDE summaries; keep the best sample per job."""
    best: dict[str, dict[str, object]] = {}
    for summary in sorted(pred_dir.rglob(f"*{_MARKER}*.json")):
        if summary.name.startswith("._"):  # macOS tar AppleDouble sidecar
            continue
        job, _, sample = summary.stem.partition(_MARKER)
        data = json.loads(summary.read_text())
        hit = {
            "ligand": job,
            "iptm": _num(data.get("iptm")),
            "ranking_score": _num(data.get("ranking_score")),
            "ptm": _num(data.get("ptm")),
            "plddt": _num(data.get("plddt")),
            "has_clash": data.get("has_clash"),
            "cif": next(
                (
                    p.name
                    for p in summary.parent.glob(f"{job}_sample_{sample}.cif")
                ),
                None,
            ),
        }
        prev = best.get(job)
        score = hit["ranking_score"]
        prev_score = prev["ranking_score"] if prev else None
        if prev is None or (
            isinstance(score, float)
            and (not isinstance(prev_score, float) or score > prev_score)
        ):
            best[job] = hit
    return list(best.values())


def _sort_key(hit: dict[str, object]) -> tuple[float, float]:
    """Best first: highest iptm, then highest ranking_score."""
    iptm = hit["iptm"]
    score = hit["ranking_score"]
    return (
        -(iptm if isinstance(iptm, float) else -1.0),
        -(score if isinstance(score, float) else -1.0),
    )


def rank(predictions: Path, out: Path) -> int:
    """Untar *predictions*, rank the hits, write *out* CSV. Returns row count."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        extracted = Path(tmp)
        with tarfile.open(predictions) as tar:
            tar.extractall(extracted, filter="data")  # safe extraction
        hits = collect_hits(extracted)

    hits.sort(key=_sort_key)
    columns = [
        "rank",
        "ligand",
        "iptm",
        "ranking_score",
        "ptm",
        "plddt",
        "has_clash",
        "cif",
    ]
    with out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        for i, hit in enumerate(hits, start=1):
            writer.writerow({"rank": i, **hit})
    return len(hits)


def _selftest() -> None:
    """Build a fake predictions archive and assert ranking + CSV output."""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        src = d / "predictions"
        # (job, sample, iptm, ranking_score)
        fake = [
            ("weak", 0, 0.30, 0.35),
            ("strong", 0, 0.60, 0.70),
            ("strong", 1, 0.90, 0.95),  # best sample for "strong"
            ("mid", 0, 0.60, 0.65),  # ties "strong"-s0 on iptm, loses on score
        ]
        for job, sample, iptm, score in fake:
            pdir = src / job / "seed_101" / "predictions"
            pdir.mkdir(parents=True, exist_ok=True)
            (pdir / f"{job}_sample_{sample}.cif").write_text("data_x\n")
            (pdir / f"._{job}{_MARKER}{sample}.json").write_bytes(b"\xa3junk")
            (pdir / f"{job}{_MARKER}{sample}.json").write_text(
                json.dumps(
                    {
                        "iptm": iptm,
                        "ranking_score": score,
                        "ptm": 0.8,
                        "plddt": 80.0,
                        "has_clash": 0.0,
                    }
                )
            )
        archive = d / "predictions.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(src, arcname=".")

        out = d / "top_hits.csv"
        n = rank(archive, out)
        assert n == 3, n
        rows = list(csv.DictReader(out.open()))
        order = [r["ligand"] for r in rows]
        assert order == ["strong", "mid", "weak"], order
        assert rows[0]["iptm"] == "0.9", rows[0]  # best sample kept
        assert rows[0]["cif"] == "strong_sample_1.cif", rows[0]
        assert rows[0]["rank"] == "1", rows[0]
    print("rank.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rank OpenDDE predictions.")
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        _selftest()
        return 0
    if not (args.predictions and args.out):
        parser.error("--predictions and --out are required")

    n = rank(args.predictions, args.out)
    print(f"rank.py: wrote {n} ranked hits to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
