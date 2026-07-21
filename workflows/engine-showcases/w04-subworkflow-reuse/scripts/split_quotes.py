#!/usr/bin/env python3
"""
Stage 1 (split) — split a two-line quotes file into one file per line.

stdlib only.

Usage:
    split_quotes.py --quotes examples/quotes.txt --out-a quote_a.txt --out-b quote_b.txt
    split_quotes.py --selftest
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def run(quotes: Path, out_a: Path, out_b: Path) -> None:
    """Write the first line of *quotes* to *out_a*, the second to *out_b*."""
    lines = quotes.read_text().splitlines()
    line_a, line_b = lines[0], lines[1]
    out_a.parent.mkdir(parents=True, exist_ok=True)
    out_b.parent.mkdir(parents=True, exist_ok=True)
    out_a.write_text(line_a + "\n")
    out_b.write_text(line_b + "\n")
    print(f"split_quotes.py: {out_a} <- {line_a!r}, {out_b} <- {line_b!r}")


def _selftest() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        quotes = Path(tmp) / "quotes.txt"
        quotes.write_text("  hello world  \n  goodbye world  \n")
        out_a, out_b = Path(tmp) / "a.txt", Path(tmp) / "b.txt"
        run(quotes, out_a, out_b)
        assert out_a.read_text().strip() == "hello world", out_a.read_text()
        assert out_b.read_text().strip() == "goodbye world", out_b.read_text()
    print("split_quotes.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Split a two-line quotes file in two.")
    parser.add_argument("--quotes", type=Path)
    parser.add_argument("--out-a", type=Path, dest="out_a")
    parser.add_argument("--out-b", type=Path, dest="out_b")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        _selftest()
        return 0
    if not (args.quotes and args.out_a and args.out_b):
        parser.error("--quotes, --out-a and --out-b are required")

    run(args.quotes, args.out_a, args.out_b)
    return 0


if __name__ == "__main__":
    sys.exit(main())
