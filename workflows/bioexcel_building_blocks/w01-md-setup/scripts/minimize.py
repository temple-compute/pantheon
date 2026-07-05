#!/usr/bin/env python3
"""Stage 5 — energy minimization.

Runs grompp (simulation_type='minimization') then mdrun to minimize the
ionized system using steepest descent until max force < 500 kJ/mol/nm or
5,000 steps, whichever comes first.

Usage:
    minimize.py --gro ionized.gro --top ionized_top.zip \
                --out-gro minimized.gro --out-tpr min.tpr
    minimize.py --selftest
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path


def run(args: argparse.Namespace) -> None:
    from biobb_gromacs.gromacs.grompp import grompp
    from biobb_gromacs.gromacs.mdrun import mdrun

    Path(args.out_gro).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_tpr).parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        min_tpr = str(tmp_path / "min.tpr")
        min_gro = str(tmp_path / "min.gro")
        min_trr = str(tmp_path / "min.trr")
        min_edr = str(tmp_path / "min.edr")
        min_log = str(tmp_path / "min.log")

        grompp(
            input_gro_path=str(args.gro),
            input_top_zip_path=str(args.top),
            output_tpr_path=min_tpr,
            properties={
                "simulation_type": "minimization",
                "mdp": {"emtol": "500", "nsteps": "5000"},
            },
        )

        mdrun(
            input_tpr_path=min_tpr,
            output_trr_path=min_trr,
            output_gro_path=min_gro,
            output_edr_path=min_edr,
            output_log_path=min_log,
        )

        shutil.copy(min_gro, args.out_gro)
        shutil.copy(min_tpr, args.out_tpr)


def _selftest() -> None:
    print("minimize.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Energy minimization")
    p.add_argument("--gro", type=Path, help="Input ionized structure")
    p.add_argument("--top", type=Path, help="Input ionized topology zip")
    p.add_argument("--out-gro", type=Path, help="Output minimized structure")
    p.add_argument("--out-tpr", type=Path, help="Output minimization TPR")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)

    if args.selftest:
        _selftest()
        return 0

    if not (args.gro and args.top and args.out_gro and args.out_tpr):
        p.error("--gro, --top, --out-gro, and --out-tpr are required")

    run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
