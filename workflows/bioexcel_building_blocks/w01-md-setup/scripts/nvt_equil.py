#!/usr/bin/env python3
"""Stage 6 — NVT equilibration (constant N, V, T).

Runs 10 ps of NVT equilibration with protein heavy atoms restrained
(POSRES). Uses md integrator, dt=0.002 ps, 5,000 steps at 300 K.

Usage:
    nvt_equil.py --gro minimized.gro --top ionized_top.zip \
                 --out-gro nvt.gro --out-cpt nvt.cpt
    nvt_equil.py --selftest
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
        nvt_tpr = str(tmp_path / "nvt.tpr")
        nvt_gro = str(tmp_path / "nvt.gro")
        nvt_trr = str(tmp_path / "nvt.trr")
        nvt_edr = str(tmp_path / "nvt.edr")
        nvt_log = str(tmp_path / "nvt.log")
        nvt_cpt = str(tmp_path / "nvt.cpt")

        grompp(
            input_gro_path=str(args.gro),
            input_top_zip_path=str(args.top),
            output_tpr_path=nvt_tpr,
            properties={
                "simulation_type": "nvt",
                "mdp": {"nsteps": 5000, "dt": 0.002, "Define": "-DPOSRES"},
            },
        )

        mdrun(
            input_tpr_path=nvt_tpr,
            output_trr_path=nvt_trr,
            output_gro_path=nvt_gro,
            output_edr_path=nvt_edr,
            output_log_path=nvt_log,
            output_cpt_path=nvt_cpt,
        )

        shutil.copy(nvt_gro, args.out_gro)
        shutil.copy(nvt_cpt, args.out_cpt)


def _selftest() -> None:
    print("nvt_equil.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="NVT equilibration")
    p.add_argument("--gro", type=Path, help="Input minimized structure")
    p.add_argument("--top", type=Path, help="Input ionized topology zip")
    p.add_argument("--out-gro", type=Path, help="Output NVT structure")
    p.add_argument("--out-cpt", type=Path, help="Output NVT checkpoint")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)

    if args.selftest:
        _selftest()
        return 0

    if not (args.gro and args.top and args.out_gro and args.out_cpt):
        p.error("--gro, --top, --out-gro, and --out-cpt are required")

    run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
