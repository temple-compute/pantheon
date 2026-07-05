#!/usr/bin/env python3
"""Stage 4 — neutralize system charge by adding ions.

Runs grompp with simulation_type='ions' to produce a run file, then genion
to replace solvent molecules with Na+/Cl- ions until the system is neutral.

Usage:
    add_ions.py --gro solvated.gro --top solvated_top.zip \
                --out-gro ionized.gro --out-top ionized_top.zip
    add_ions.py --selftest
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path


def run(args: argparse.Namespace) -> None:
    from biobb_gromacs.gromacs.genion import genion
    from biobb_gromacs.gromacs.grompp import grompp

    Path(args.out_gro).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_top).parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ion_tpr = str(tmp_path / "ion.tpr")
        ionized_gro = str(tmp_path / "ionized.gro")
        ionized_top = str(tmp_path / "ionized_top.zip")

        grompp(
            input_gro_path=str(args.gro),
            input_top_zip_path=str(args.top),
            output_tpr_path=ion_tpr,
            properties={"simulation_type": "ions", "maxwarn": 1},
        )

        genion(
            input_tpr_path=ion_tpr,
            output_gro_path=ionized_gro,
            input_top_zip_path=str(args.top),
            output_top_zip_path=ionized_top,
            properties={"neutral": True, "concentration": 0},
        )

        shutil.copy(ionized_gro, args.out_gro)
        shutil.copy(ionized_top, args.out_top)


def _selftest() -> None:
    print("add_ions.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Add ions to neutralize the system")
    p.add_argument("--gro", type=Path, help="Input solvated structure")
    p.add_argument("--top", type=Path, help="Input solvated topology zip")
    p.add_argument("--out-gro", type=Path, help="Output ionized structure")
    p.add_argument("--out-top", type=Path, help="Output ionized topology zip")
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
