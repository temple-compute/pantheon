#!/usr/bin/env python3
"""
Stage 3 (rank) — turn Boltz-2 predictions into a ranked shortlist.

Untars the predictions archive produced by the GPU stage, finds every
``affinity_*.json`` Boltz-2 wrote, joins it with the sibling
``confidence_*.json``, and writes ``top_hits.csv`` sorted best-first.

Ranking note (see README): Boltz-2's affinity is a reliable *ranking* signal,
not a calibrated ΔG. We sort by ``affinity_probability_binary`` (descending —
likelihood the ligand binds), tie-breaking on ``affinity_pred_value``
(ascending). The absolute numbers are not kcal/mol.

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


def _num(value: object) -> float | None:
    """Coerce *value* to float, or None if it isn't a number."""
    return float(value) if isinstance(value, (int, float)) else None


def collect_hits(pred_dir: Path) -> list[dict[str, object]]:
    """Scan *pred_dir* for Boltz-2 affinity outputs and return hit rows."""
    hits: list[dict[str, object]] = []
    for affinity_file in sorted(pred_dir.rglob("affinity_*.json")):
        ligand = affinity_file.stem[len("affinity_"):]
        data = json.loads(affinity_file.read_text())

        # Confidence lives in a sibling confidence_*.json (model 0 if several).
        confidence: float | None = None
        siblings = sorted(affinity_file.parent.glob("confidence_*.json"))
        if siblings:
            cdata = json.loads(siblings[0].read_text())
            confidence = _num(cdata.get("confidence_score"))

        hits.append(
            {
                "ligand": ligand,
                "affinity_pred_value": _num(data.get("affinity_pred_value")),
                "affinity_probability_binary": _num(
                    data.get("affinity_probability_binary")
                ),
                "confidence_score": confidence,
            }
        )
    return hits


def _sort_key(hit: dict[str, object]) -> tuple[float, float]:
    """Best first: highest binder probability, then lowest predicted value."""
    prob = hit["affinity_probability_binary"]
    val = hit["affinity_pred_value"]
    prob_f = prob if isinstance(prob, float) else -1.0
    val_f = val if isinstance(val, float) else float("inf")
    return (-prob_f, val_f)


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
        "affinity_probability_binary",
        "affinity_pred_value",
        "confidence_score",
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
        for name, prob, val in [
            ("weak", 0.10, -5.0),
            ("strong", 0.90, -9.0),
            ("mid", 0.50, -7.0),
        ]:
            rec = src / name
            rec.mkdir(parents=True)
            (rec / f"affinity_{name}.json").write_text(
                json.dumps(
                    {
                        "affinity_pred_value": val,
                        "affinity_probability_binary": prob,
                    }
                )
            )
            (rec / f"confidence_{name}.json").write_text(
                json.dumps({"confidence_score": prob})
            )
        archive = d / "predictions.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(src, arcname=".")

        out = d / "top_hits.csv"
        n = rank(archive, out)
        assert n == 3, n
        rows = list(csv.DictReader(out.open()))
        order = [r["ligand"] for r in rows]
        assert order == ["strong", "mid", "weak"], order  # prob descending
        assert rows[0]["rank"] == "1", rows[0]
        assert rows[0]["confidence_score"] == "0.9", rows[0]
    print("rank.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rank Boltz-2 predictions.")
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
