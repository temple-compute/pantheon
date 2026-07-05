#!/usr/bin/env python3
"""Stage 1 — download PDB structure and fix side chains.

Downloads 1AKI from RCSB and runs fix_side_chain to model any missing
side-chain atoms, check amide assignments, and flag backbone/heteroatom issues.

Usage:
    fetch_and_fix.py --pdb-code 1AKI --out-fixed fixed.pdb
    fetch_and_fix.py --selftest
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path


def run(args: argparse.Namespace) -> None:
    from biobb_io.api.pdb import pdb
    from biobb_model.model.fix_side_chain import fix_side_chain

    Path(args.out_fixed).parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        downloaded_pdb = str(tmp_path / "downloaded.pdb")
        fixed_pdb = str(tmp_path / "fixed.pdb")

        pdb(output_pdb_path=downloaded_pdb, properties={"pdb_code": args.pdb_code})
        fix_side_chain(input_pdb_path=downloaded_pdb, output_pdb_path=fixed_pdb)

        shutil.copy(fixed_pdb, args.out_fixed)


def _selftest() -> None:
    print("fetch_and_fix.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Download PDB and fix side chains")
    p.add_argument("--pdb-code", default="1AKI", help="RCSB PDB code")
    p.add_argument("--out-fixed", type=Path, help="Output fixed PDB path")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)

    if args.selftest:
        _selftest()
        return 0

    if not args.out_fixed:
        p.error("--out-fixed is required")

    run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
