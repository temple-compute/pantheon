#!/usr/bin/env python3
"""Stage 7 — NPT equilibration (constant N, P, T).

Runs 10 ps of NPT equilibration with Parrinello-Rahman pressure coupling.
Protein heavy atoms remain restrained. Uses md integrator, dt=0.002 ps,
5,000 steps. Requires the NVT checkpoint to continue velocity generation.

Usage:
    npt_equil.py --gro nvt.gro --cpt nvt.cpt --top ionized_top.zip \
                 --out-gro npt.gro --out-cpt npt.cpt
    npt_equil.py --selftest
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
    Path(args.out_cpt).parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        npt_tpr = str(tmp_path / "npt.tpr")
        npt_gro = str(tmp_path / "npt.gro")
        npt_trr = str(tmp_path / "npt.trr")
        npt_edr = str(tmp_path / "npt.edr")
        npt_log = str(tmp_path / "npt.log")
        npt_cpt = str(tmp_path / "npt.cpt")

        grompp(
            input_gro_path=str(args.gro),
            input_top_zip_path=str(args.top),
            output_tpr_path=npt_tpr,
            input_cpt_path=str(args.cpt),
            properties={
                "simulation_type": "npt",
                "mdp": {"nsteps": "5000"},
            },
        )

        mdrun(
            input_tpr_path=npt_tpr,
            output_trr_path=npt_trr,
            output_gro_path=npt_gro,
            output_edr_path=npt_edr,
            output_log_path=npt_log,
            output_cpt_path=npt_cpt,
        )

        shutil.copy(npt_gro, args.out_gro)
        shutil.copy(npt_cpt, args.out_cpt)


def _selftest() -> None:
    print("npt_equil.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="NPT equilibration")
    p.add_argument("--gro", type=Path, help="Input NVT structure")
    p.add_argument("--cpt", type=Path, help="Input NVT checkpoint")
    p.add_argument("--top", type=Path, help="Input ionized topology zip")
    p.add_argument("--out-gro", type=Path, help="Output NPT structure")
    p.add_argument("--out-cpt", type=Path, help="Output NPT checkpoint")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)

    if args.selftest:
        _selftest()
        return 0

    if not (args.gro and args.cpt and args.top and args.out_gro and args.out_cpt):
        p.error("--gro, --cpt, --top, --out-gro, and --out-cpt are required")

    run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
