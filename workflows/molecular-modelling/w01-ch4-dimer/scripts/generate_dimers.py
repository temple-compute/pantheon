#!/usr/bin/env python3
"""
Generate methane-helium dimer XYZ files for the PES workflow.

Writes one sub-directory per dimer geometry under ``--out``, each containing a
``molecule.xyz`` file. The ``map:`` block in ``workflow.yaml`` fans one psi4
single-point calculation out over every sub-directory concurrently.

Self-contained (numpy only) so the ``python_script`` runtime can ship it to the
task target as a single file. The rotation / XYZ writing logic is intentionally
kept inline instead of importing the project's ``molecular.py`` because only the
one script file is transferred to the target.

Usage:
    generate_dimers.py --out dimers/ [--methane-step 20] [--helium-step 20]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

METHANE_SYMBOLS = ["C", "H", "H", "H", "H"]
METHANE = np.array(
    [
        [0.00000, 0.00000, 0.00000],
        [0.00000, 0.00000, 1.08900],
        [1.02672, 0.00000, -0.36300],
        [-0.51336, -0.88916, -0.36300],
        [-0.51336, 0.88916, -0.36300],
    ],
    dtype=float,
)

HELIUM_SYMBOLS = ["He"]
HELIUM_POS = np.array([0.0, 0.0, 1.2], dtype=float)


def rotate(coords: np.ndarray, axis, angle_deg: float, point) -> np.ndarray:
    """Rotate *coords* around *axis* by *angle_deg* about *point* (Rodrigues)."""
    u = np.asarray(axis, dtype=float)
    u = u / np.linalg.norm(u)
    rad = np.radians(angle_deg)
    p0 = np.asarray(point, dtype=float)
    ux, uy, uz = u
    k = np.array(
        [[0.0, -uz, uy], [uz, 0.0, -ux], [-uy, ux, 0.0]], dtype=float
    )
    r = np.eye(3) + np.sin(rad) * k + (1.0 - np.cos(rad)) * (k @ k)
    return (coords - p0) @ r.T + p0


def write_xyz(path: Path, symbols, coords: np.ndarray, comment: str = "") -> None:
    """Write an XYZ file for *symbols* / *coords* to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{len(symbols)}", comment]
    for sym, c in zip(symbols, coords):
        lines.append(f"{sym:<3s} {c[0]:15.8f} {c[1]:15.8f} {c[2]:15.8f}")
    path.write_text("\n".join(lines) + "\n")


def build(
    out: Path,
    methane_step: int,
    helium_step: int,
    max_methane: int,
    max_helium: int,
) -> int:
    """Write one dimer sub-directory per (methane, helium) rotation pair."""
    out.mkdir(parents=True, exist_ok=True)
    count = 0
    for i in range(0, max_methane, methane_step):
        ch4 = rotate(METHANE, [0, 0, 1], i, [0, 0, 0])
        for j in range(0, max_helium + 1, helium_step):
            he = rotate(HELIUM_POS.reshape(1, 3), [1, 0, 0], j, [0, 0, 0])[0]
            dimer_syms = METHANE_SYMBOLS + HELIUM_SYMBOLS
            dimer_coords = np.vstack([ch4, he])
            name = f"dimer_{i:03d}_{j:03d}"
            write_xyz(
                out / name / "molecule.xyz",
                dimer_syms,
                dimer_coords,
                comment=f"CH4-He dimer i={i} j={j}",
            )
            count += 1
    print(f"generate_dimers.py: wrote {count} dimer(s) -> {out}")
    return count


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate CH4-He dimer XYZ files.")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--methane-step", type=int, default=20)
    parser.add_argument("--helium-step", type=int, default=20)
    parser.add_argument("--max-methane", type=int, default=120)
    parser.add_argument("--max-helium", type=int, default=180)
    args = parser.parse_args(argv)
    build(
        args.out,
        args.methane_step,
        args.helium_step,
        args.max_methane,
        args.max_helium,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
