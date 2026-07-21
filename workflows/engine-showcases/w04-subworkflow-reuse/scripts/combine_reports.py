#!/usr/bin/env python3
"""
Stage 3 (combine) — join the two cleaned quotes into one report.

stdlib only.

Usage:
    combine_reports.py --a clean_a.txt --b clean_b.txt --out results/report.txt
    combine_reports.py --selftest
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def run(a: Path, b: Path, out: Path) -> None:
    """Concatenate *a* and *b*, one line each, into *out*."""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(a.read_text().strip() + "\n" + b.read_text().strip() + "\n")
    print(f"combine_reports.py: {a} + {b} -> {out}")


def _selftest() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        a, b, out = Path(tmp) / "a.txt", Path(tmp) / "b.txt", Path(tmp) / "report.txt"
        a.write_text("HELLO WORLD\n")
        b.write_text("GOODBYE WORLD\n")
        run(a, b, out)
        assert out.read_text() == "HELLO WORLD\nGOODBYE WORLD\n", out.read_text()
    print("combine_reports.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Combine two cleaned quote files into a report.")
    parser.add_argument("--a", type=Path)
    parser.add_argument("--b", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        _selftest()
        return 0
    if not (args.a and args.b and args.out):
        parser.error("--a, --b and --out are required")

    run(args.a, args.b, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
