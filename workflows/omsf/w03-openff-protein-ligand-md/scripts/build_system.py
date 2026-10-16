#!/usr/bin/env python3
# Solvates the receptor with PDBFixer (padding and NaCl ionic strength from the
# workflow variables), inserts the
# ligand, drops waters within 1.5 A of it and writes an OpenFF Topology
# as JSON. Same steps as the openff-toolkit 0.19.0 toolkit_showcase notebook.

import argparse
import math
import os
import sys
import tempfile
from pathlib import Path

# Shared host: cap BLAS/torch threads unless the caller set them.
os.environ.setdefault("OMP_NUM_THREADS", "2")

CLASH_A = 1.5
# Only 3-atom waters are removed: dropping a 1-atom ion would leave a net charge.
WATER_ATOMS = 3


def clashing(positions, sizes: list[int], insert, radius: float = CLASH_A) -> list[int]:
    """Indices of waters with any atom within radius of insert (Nx3 sequences)."""
    out, start = [], 0
    for i, n in enumerate(sizes):
        if n == WATER_ATOMS and any(math.dist(a, b) <= radius
                                    for a in positions[start:start + n] for b in insert):
            out.append(i)
        start += n
    return out


def check_range(name: str, value: float, lo: float, hi: float) -> float:
    """Exit with a clear message unless lo <= value <= hi."""
    if not lo <= value <= hi:
        sys.exit(f"{name} must be between {lo} and {hi}, got {value}")
    return value


def build(receptor: Path, ligand_path: Path, out: Path, padding_nm: float,
          ionic_strength: float) -> None:
    import openmm.app
    from openff.toolkit import Molecule, Topology
    from openff.units import unit
    from openmm import unit as omm_unit
    from pdbfixer import PDBFixer

    ligand = Molecule.from_file(str(ligand_path))
    fixer = PDBFixer(str(receptor))
    fixer.addSolvent(padding=padding_nm * omm_unit.nanometer,
                     ionicStrength=ionic_strength * omm_unit.molar)
    with tempfile.TemporaryDirectory() as d:
        solvated = Path(d) / "receptor_solvated.pdb"
        with solvated.open("w") as f:
            openmm.app.PDBFile.writeFile(fixer.topology, fixer.positions, f)
        top = Topology.from_pdb(str(solvated))
    mols = list(top.molecules)
    drop = set(clashing(top.get_positions().m_as(unit.angstrom),
                        [m.n_atoms for m in mols],
                        ligand.conformers[0].m_as(unit.angstrom)))
    print(f"{top.n_atoms} atoms after solvation; removing {len(drop)} clashing "
          "waters", flush=True)
    new = Topology.from_molecules([m for i, m in enumerate(mols) if i not in drop] + [ligand])
    new.box_vectors = top.box_vectors
    out.write_text(new.to_json())
    print(f"wrote {out} ({new.n_atoms} atoms, {new.n_molecules} molecules)", flush=True)


def selftest() -> None:
    # protein (5 atoms at origin) + two waters, one on top of the ligand, + an ion
    pos = [[0, 0, 0]] * 5 + [[10, 0, 0]] * 3 + [[20, 0, 0]] * 3 + [[30, 0, 0]]
    lig = [[10.5, 0, 0], [30, 0, 0]]
    # the ion at 30 A clashes but is kept
    assert clashing(pos, [5, 3, 3, 1], lig) == [1]
    # the protein is never removed even when it clashes
    assert clashing(pos, [5, 3, 3, 1], [[0, 0, 0]]) == []
    assert clashing(pos, [5, 3, 3, 1], lig, radius=0.1) == []
    assert check_range("x", 1.0, 0.5, 5.0) == 1.0
    try:
        check_range("padding_nm", 0.1, 0.5, 5.0)
        raise AssertionError("out-of-range value accepted")
    except SystemExit as e:
        assert "padding_nm must be between" in str(e)
    print("selftest ok")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--receptor", type=Path)
    ap.add_argument("--ligand", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--padding-nm", type=float)
    ap.add_argument("--ionic-strength", type=float, help="NaCl, molar")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not (a.receptor and a.ligand and a.out and a.padding_nm is not None
            and a.ionic_strength is not None):
        sys.exit("--receptor, --ligand, --out, --padding-nm and --ionic-strength are required")
    # below 0.5 nm protein images come within the 0.9 nm Sage cutoff
    check_range("padding_nm", a.padding_nm, 0.5, 5.0)
    check_range("ionic_strength_molar", a.ionic_strength, 0.0, 2.0)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    build(a.receptor, a.ligand, a.out, a.padding_nm, a.ionic_strength)


if __name__ == "__main__":
    main()
