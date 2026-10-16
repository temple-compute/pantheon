#!/usr/bin/env python3
# Solvates the receptor with PDBFixer (1 nm padding, 0.15 M NaCl), inserts the
# ligand, drops waters/ions within 1.5 A of it and writes an OpenFF Topology
# as JSON. Same steps as the openff-toolkit 0.19.0 toolkit_showcase notebook.

import argparse
import os
import sys
from pathlib import Path

# Shared host: cap BLAS/torch threads unless the caller set them.
os.environ.setdefault("OMP_NUM_THREADS", "2")

import numpy as np

CLASH_A = 1.5
# Waters and ions are the only molecules we remove; the protein is kept.
MAX_SOLVENT_ATOMS = 3


def clashing(positions: np.ndarray, sizes: list[int], insert: np.ndarray,
             radius: float = CLASH_A) -> list[int]:
    """Indices of solvent-sized molecules with any atom within radius of insert."""
    out, start = [], 0
    for i, n in enumerate(sizes):
        if n <= MAX_SOLVENT_ATOMS:
            d = np.linalg.norm(positions[start:start + n, None, :] - insert[None], axis=-1)
            if d.min() <= radius:
                out.append(i)
        start += n
    return out


def build(receptor: Path, ligand_path: Path, out: Path) -> None:
    import openmm.app
    from openff.toolkit import Molecule, Topology
    from openff.units import unit
    from openmm import unit as omm_unit
    from pdbfixer import PDBFixer

    ligand = Molecule.from_file(str(ligand_path))
    fixer = PDBFixer(str(receptor))
    fixer.addSolvent(padding=1.0 * omm_unit.nanometer, ionicStrength=0.15 * omm_unit.molar)
    solvated = out.parent / "receptor_solvated.pdb"
    with solvated.open("w") as f:
        openmm.app.PDBFile.writeFile(fixer.topology, fixer.positions, f)

    top = Topology.from_pdb(str(solvated))
    mols = list(top.molecules)
    drop = set(clashing(top.get_positions().m_as(unit.angstrom),
                        [m.n_atoms for m in mols],
                        ligand.conformers[0].m_as(unit.angstrom)))
    print(f"{top.n_atoms} atoms after solvation; removing {len(drop)} clashing "
          "solvent molecules", flush=True)
    new = Topology.from_molecules([m for i, m in enumerate(mols) if i not in drop] + [ligand])
    new.box_vectors = top.box_vectors
    out.write_text(new.to_json())
    print(f"wrote {out} ({new.n_atoms} atoms, {new.n_molecules} molecules)", flush=True)


def selftest() -> None:
    # protein (5 atoms at origin) + two waters, one on top of the ligand
    pos = np.array([[0, 0, 0]] * 5 + [[10, 0, 0]] * 3 + [[20, 0, 0]] * 3, float)
    lig = np.array([[10.5, 0, 0], [30, 0, 0]], float)
    assert clashing(pos, [5, 3, 3], lig) == [1]
    # the protein is never removed even when it clashes
    assert clashing(pos, [5, 3, 3], np.zeros((1, 3))) == []
    assert clashing(pos, [5, 3, 3], lig, radius=0.1) == []
    print("selftest ok")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--receptor", type=Path)
    ap.add_argument("--ligand", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not (a.receptor and a.ligand and a.out):
        sys.exit("--receptor, --ligand and --out are required")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    build(a.receptor, a.ligand, a.out)


if __name__ == "__main__":
    main()
