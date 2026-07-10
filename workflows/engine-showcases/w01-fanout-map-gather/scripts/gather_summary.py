#!/usr/bin/env python3
"""
Stage 3 (gather) — aggregate the mapped stage's per-batch folders into one.

The ``score`` task's ``map:`` block runs one clone per batch and writes each
clone's output under ``score.gathered/<i>/scored/`` (``count.txt`` +
``upper.txt``). This stage walks that gathered folder, sums the per-batch word
counts, concatenates the uppercased text, and writes a single combined
``summary.json`` + ``combined_upper.txt``.

stdlib only.

Usage:
    gather_summary.py --results score.gathered/ --out results/summary/
    gather_summary.py --selftest
"""

from __future__ import annotations  # portable across python3 (>=3.9)

import argparse
import json
import sys
from pathlib import Path


def collect(results: Path) -> list[dict]:
    """Read one record per ``<i>/scored/{count,upper}.txt`` under *results*."""
    batches: list[dict] = []
    for batch_dir in sorted(
        (p for p in results.iterdir() if p.is_dir()),
        key=lambda p: int(p.name) if p.name.isdigit() else p.name,
    ):
        scored = batch_dir / "scored"
        count = int((scored / "count.txt").read_text().split()[0])
        upper = (scored / "upper.txt").read_text()
        batches.append({"index": batch_dir.name, "words": count, "upper": upper})
    return batches


def write_summary(batches: list[dict], out: Path) -> int:
    """Write the combined summary.json + combined_upper.txt into *out*. Returns total words."""
    out.mkdir(parents=True, exist_ok=True)
    total = sum(b["words"] for b in batches)
    (out / "summary.json").write_text(
        json.dumps(
            {
                "total_words": total,
                "batches": [{"index": b["index"], "words": b["words"]} for b in batches],
            },
            indent=2,
        )
    )
    (out / "combined_upper.txt").write_text("".join(b["upper"] for b in batches))
    return total


def run(args: argparse.Namespace) -> int:
    """Gather all batch results under ``--results`` into ``--out``. Returns total words."""
    batches = collect(args.results)
    total = write_summary(batches, args.out)
    print(f"gather_summary.py: {len(batches)} batch(es), {total} total word(s) -> {args.out}")
    return total


def _selftest() -> None:
    """Build synthetic gathered batch folders and assert the aggregate."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        results = Path(tmp) / "score.gathered"
        for i, (word, count) in enumerate([("apple", 1), ("banana", 1), ("cherry pie", 2)]):
            scored = results / str(i) / "scored"
            scored.mkdir(parents=True)
            (scored / "count.txt").write_text(f"{count}\n")
            (scored / "upper.txt").write_text(word.upper() + "\n")

        out = Path(tmp) / "summary"
        total = run(argparse.Namespace(results=results, out=out))
        assert total == 4, total

        data = json.loads((out / "summary.json").read_text())
        assert data["total_words"] == 4, data
        assert len(data["batches"]) == 3, data

        combined = (out / "combined_upper.txt").read_text()
        assert combined == "APPLE\nBANANA\nCHERRY PIE\n", combined
    print("gather_summary.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate mapped batch results.")
    parser.add_argument("--results", type=Path)
    parser.add_argument("--out", type=Path)
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
