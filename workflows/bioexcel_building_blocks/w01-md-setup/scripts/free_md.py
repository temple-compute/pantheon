#!/usr/bin/env python3
"""Stage 8 — free MD simulation (100 ps).

Runs 100 ps of unconstrained MD (no position restraints) using md integrator,
dt=0.002 ps, 50,000 steps. The NPT checkpoint provides the starting velocities
and barostat state.

Usage:
    free_md.py --gro npt.gro --cpt npt.cpt --top ionized_top.zip \
               --out-gro md.gro --out-trr md.trr --out-tpr md.tpr
    free_md.py --selftest
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
    Path(args.out_trr).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_tpr).parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        md_tpr = str(tmp_path / "md.tpr")
        md_gro = str(tmp_path / "md.gro")
        md_trr = str(tmp_path / "md.trr")
        md_edr = str(tmp_path / "md.edr")
        md_log = str(tmp_path / "md.log")
        md_cpt = str(tmp_path / "md.cpt")

        grompp(
            input_gro_path=str(args.gro),
            input_top_zip_path=str(args.top),
            output_tpr_path=md_tpr,
            input_cpt_path=str(args.cpt),
            properties={
                "simulation_type": "free",
                "mdp": {"nsteps": "50000"},
            },
        )

        mdrun(
            input_tpr_path=md_tpr,
            output_trr_path=md_trr,
            output_gro_path=md_gro,
            output_edr_path=md_edr,
            output_log_path=md_log,
            output_cpt_path=md_cpt,
        )

        shutil.copy(md_gro, args.out_gro)
        shutil.copy(md_trr, args.out_trr)
        shutil.copy(md_tpr, args.out_tpr)


def _selftest() -> None:
    print("free_md.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Free MD simulation")
    p.add_argument("--gro", type=Path, help="Input NPT structure")
    p.add_argument("--cpt", type=Path, help="Input NPT checkpoint")
    p.add_argument("--top", type=Path, help="Input ionized topology zip")
    p.add_argument("--out-gro", type=Path, help="Output final structure")
    p.add_argument("--out-trr", type=Path, help="Output trajectory")
    p.add_argument("--out-tpr", type=Path, help="Output TPR (portable run file)")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)

    if args.selftest:
        _selftest()
        return 0

    if not (args.gro and args.cpt and args.top and args.out_gro and args.out_trr and args.out_tpr):
        p.error("--gro, --cpt, --top, --out-gro, --out-trr, and --out-tpr are required")

    run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
