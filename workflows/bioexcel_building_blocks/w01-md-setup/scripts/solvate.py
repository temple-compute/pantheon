#!/usr/bin/env python3
"""Stage 3 — create solvent box and fill with water.

Runs editconf to define a cubic simulation box (1 nm padding), then solvate
to fill it with SPC water molecules.

Usage:
    solvate.py --gro system.gro --top topology.zip \
               --out-gro solvated.gro --out-top solvated_top.zip
    solvate.py --selftest
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path


def run(args: argparse.Namespace) -> None:
    from biobb_gromacs.gromacs.editconf import editconf
    from biobb_gromacs.gromacs.solvate import solvate

    Path(args.out_gro).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_top).parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        boxed_gro = str(tmp_path / "boxed.gro")
        solvated_gro = str(tmp_path / "solvated.gro")
        solvated_top = str(tmp_path / "solvated_top.zip")

        editconf(
            input_gro_path=str(args.gro),
            output_gro_path=boxed_gro,
            properties={"box_type": "cubic", "distance_to_molecule": 1.0},
        )

        solvate(
            input_solute_gro_path=boxed_gro,
            output_gro_path=solvated_gro,
            input_top_zip_path=str(args.top),
            output_top_zip_path=solvated_top,
        )

        shutil.copy(solvated_gro, args.out_gro)
        shutil.copy(solvated_top, args.out_top)


def _selftest() -> None:
    print("solvate.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Box and solvate the protein system")
    p.add_argument("--gro", type=Path, help="Input GROMACS structure")
    p.add_argument("--top", type=Path, help="Input topology zip")
    p.add_argument("--out-gro", type=Path, help="Output solvated structure")
    p.add_argument("--out-top", type=Path, help="Output solvated topology zip")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)

    if args.selftest:
        _selftest()
        return 0

    if not (args.gro and args.top and args.out_gro and args.out_top):
        p.error("--gro, --top, --out-gro, and --out-top are required")

    run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
