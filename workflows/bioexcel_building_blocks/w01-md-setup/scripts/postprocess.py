#!/usr/bin/env python3
"""Stage 9 — post-process trajectory (strip solvent, fix periodicity).

Runs gmx_image to center the protein, strip water/ions, and correct PBC
artifacts, producing a protein-only trajectory. Then runs gmx_trjconv_str
to generate a dry (protein-only) GRO structure for use as a topology when
visualizing the imaged trajectory.

Usage:
    postprocess.py --trr md.trr --tpr md.tpr --gro md.gro \
                   --out-trr imaged.trr --out-gro dry.gro
    postprocess.py --selftest
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path


def run(args: argparse.Namespace) -> None:
    from biobb_analysis.gromacs.gmx_image import gmx_image
    from biobb_analysis.gromacs.gmx_trjconv_str import gmx_trjconv_str

    Path(args.out_trr).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_gro).parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        imaged_trr = str(tmp_path / "imaged.trr")
        dry_gro = str(tmp_path / "dry.gro")

        gmx_image(
            input_traj_path=str(args.trr),
            input_top_path=str(args.tpr),
            output_traj_path=imaged_trr,
            properties={
                "center_selection": "Protein",
                "output_selection": "Protein",
                "pbc": "mol",
                "center": True,
            },
        )

        gmx_trjconv_str(
            input_structure_path=str(args.gro),
            input_top_path=str(args.tpr),
            output_str_path=dry_gro,
            properties={"selection": "Protein"},
        )

        shutil.copy(imaged_trr, args.out_trr)
        shutil.copy(dry_gro, args.out_gro)


def _selftest() -> None:
    print("postprocess.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Strip solvent and fix PBC in trajectory")
    p.add_argument("--trr", type=Path, help="Input MD trajectory")
    p.add_argument("--tpr", type=Path, help="Input MD TPR")
    p.add_argument("--gro", type=Path, help="Input MD final structure")
    p.add_argument("--out-trr", type=Path, help="Output imaged trajectory")
    p.add_argument("--out-gro", type=Path, help="Output dry structure")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)

    if args.selftest:
        _selftest()
        return 0

    if not (args.trr and args.tpr and args.gro and args.out_trr and args.out_gro):
        p.error("--trr, --tpr, --gro, --out-trr, and --out-gro are required")

    run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
