#!/usr/bin/env python3
"""
Stage 1 (split) — chunk a small JSON list into batch files.

Reads a JSON array of items and writes one text file per batch (``batch_0.txt``,
``batch_1.txt``, ...) into the output folder, one item per line. The output
folder is what the ``score`` task's declarative ``map:`` block fans out over —
each batch file becomes one item handed to a concurrent clone.

stdlib only.

Usage:
    split.py --items items.json --out batches/ --batch-size 2
    split.py --selftest
"""

from __future__ import annotations  # portable across python3 (>=3.9)

import argparse
import json
import sys
from pathlib import Path


def split_batches(items: list[str], batch_size: int) -> list[list[str]]:
    """Chunk *items* into consecutive groups of at most *batch_size*."""
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]


def write_batches(batches: list[list[str]], out: Path) -> None:
    """Write each batch as ``batch_<i>.txt``, one item per line, into *out*."""
    out.mkdir(parents=True, exist_ok=True)
    for i, batch in enumerate(batches):
        (out / f"batch_{i}.txt").write_text("\n".join(batch) + "\n")


def run(args: argparse.Namespace) -> int:
    """Split ``--items`` into batch files under ``--out``. Returns batch count."""
    items = json.loads(args.items.read_text())
    if not isinstance(items, list):
        raise ValueError(f"{args.items} must contain a JSON array")
    batches = split_batches(items, args.batch_size)
    write_batches(batches, args.out)
    print(f"split.py: {len(items)} item(s) -> {len(batches)} batch(es) in {args.out}")
    return len(batches)


def _selftest() -> None:
    """Split a synthetic item list and assert batch contents."""
    items = ["a", "b", "c", "d", "e"]
    batches = split_batches(items, 2)
    assert batches == [["a", "b"], ["c", "d"], ["e"]], batches

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "batches"
        write_batches(batches, out)
        files = sorted(p.name for p in out.glob("batch_*.txt"))
        assert files == ["batch_0.txt", "batch_1.txt", "batch_2.txt"], files
        assert out.joinpath("batch_0.txt").read_text() == "a\nb\n"
        assert out.joinpath("batch_2.txt").read_text() == "e\n"
    print("split.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Split a JSON list into batch files.")
    parser.add_argument("--items", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        _selftest()
        return 0
    if not (args.items and args.out):
        parser.error("--items and --out are required")

    run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
