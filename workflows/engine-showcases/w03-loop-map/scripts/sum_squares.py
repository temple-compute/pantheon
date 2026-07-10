#!/usr/bin/env python3
"""
Stage 2 (gather) — sum the squares produced by a bounded range map.

The `iterate` task's `map:` block runs a fixed number of clones (`range: 5`,
no upstream collection), one per iteration index `0..4`, each writing its
index squared to `square.txt`. Clone outputs land under
`iterate.gathered/<i>/square.txt`. This stage walks that folder and sums them:
0**2 + 1**2 + 2**2 + 3**2 + 4**2 == 30.

stdlib only.

Usage:
    sum_squares.py --results iterate.gathered/ --out results/total.txt
    sum_squares.py --selftest
"""

from __future__ import annotations  # portable across python3 (>=3.9)

import argparse
import sys
from pathlib import Path


def collect_squares(results: Path) -> list[int]:
    """Read one integer per ``<i>/square.txt`` under *results*, in index order."""
    squares = []
    for clone_dir in sorted(
        (p for p in results.iterdir() if p.is_dir()),
        key=lambda p: int(p.name) if p.name.isdigit() else p.name,
    ):
        squares.append(int((clone_dir / "square.txt").read_text().split()[0]))
    return squares


def run(args: argparse.Namespace) -> int:
    """Sum every clone's square.txt under ``--results`` into ``--out``. Returns the total."""
    squares = collect_squares(args.results)
    total = sum(squares)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(f"{total}\n")
    print(f"sum_squares.py: {squares} -> total {total} -> {args.out}")
    return total


def _selftest() -> None:
    """Build synthetic gathered clone folders and assert the sum."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        results = Path(tmp) / "iterate.gathered"
        for i, n in enumerate([0, 1, 4, 9, 16]):
            clone = results / str(i)
            clone.mkdir(parents=True)
            (clone / "square.txt").write_text(f"{n}\n")

        out = Path(tmp) / "results" / "total.txt"
        total = run(argparse.Namespace(results=results, out=out))
        assert total == 30, total
        assert out.read_text().strip() == "30"
    print("sum_squares.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sum a bounded range map's squared outputs.")
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
