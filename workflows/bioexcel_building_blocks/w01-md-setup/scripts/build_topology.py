#!/usr/bin/env python3
"""Stage 2 — build GROMACS topology with pdb2gmx.

Generates a GROMACS structure (.gro) and a compressed topology (.zip) from
the fixed PDB. Force field: amber99sb-ildn; water model: spc/e (defaults).
Hydrogen atoms are added automatically.

Usage:
    build_topology.py --fixed fixed.pdb --out-gro system.gro --out-top topology.zip
    build_topology.py --selftest
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path


def run(args: argparse.Namespace) -> None:
    from biobb_gromacs.gromacs.pdb2gmx import pdb2gmx

    Path(args.out_gro).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_top).parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        system_gro = str(tmp_path / "system.gro")
        pdb2gmx_top = str(tmp_path / "pdb2gmx_top.zip")

        pdb2gmx(
            input_pdb_path=str(args.fixed),
            output_gro_path=system_gro,
            output_top_zip_path=pdb2gmx_top,
        )

        shutil.copy(system_gro, args.out_gro)
        shutil.copy(pdb2gmx_top, args.out_top)


def _selftest() -> None:
    print("build_topology.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build GROMACS topology via pdb2gmx")
    p.add_argument("--fixed", type=Path, help="Input fixed PDB")
    p.add_argument("--out-gro", type=Path, help="Output GROMACS structure (.gro)")
    p.add_argument("--out-top", type=Path, help="Output topology zip")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)

    if args.selftest:
        _selftest()
        return 0

    if not (args.fixed and args.out_gro and args.out_top):
        p.error("--fixed, --out-gro, and --out-top are required")

    run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
