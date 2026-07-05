#!/usr/bin/env python3
"""
Stage 1 (prep) — build AutoDock Vina inputs from a receptor + ligand library.

Converts a receptor ``.pdb`` and a ligand file into the PDBQT inputs Vina needs,
resolves the docking box, and tars everything into a single archive. A single-
file output is deliberate: Horus transfer is file-based, so a tarball is what
crosses to the docking box.

The receptor is parameterised with OpenBabel (``obabel``) — a rigid PDBQT with
hydrogens added at pH 7.4; Vina's default ``vina`` scoring uses atom types, not
receptor partial charges, so this is sufficient and robust across structures.
Ligands use Meeko's ``mk_prepare_ligand.py`` (better small-molecule typing/
torsions); both tools are on PATH inside the stage's uv environment. SMILES
ligands are embedded to 3D with RDKit before Meeko sees them.

The docking box center is resolved (in priority order) from an explicit
``--center``, the centroid of a ``--ref-ligand``, or — as a last resort — the
centroid of the whole receptor (blind docking; a large ``--size`` is advised).

The pure-Python helpers (centroid parsing, box + archive assembly) are covered by
``--selftest`` and need neither RDKit nor Meeko, so the self-check runs anywhere.

Usage:
    prep.py --receptor r.pdb --ligands ligs.sdf --out vina_inputs.tar.gz \
            --center 15.19 53.90 16.92 --size 20 20 20
    prep.py --receptor r.pdb --ligands ligs.smi --ref-ligand ref.sdf --out o.tar.gz
    prep.py --selftest
"""

from __future__ import annotations  # portable across python3 (>=3.9)

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

DEFAULT_SIZE = (25.0, 25.0, 25.0)
DEFAULT_PADDING = 5.0


# --------------------------------------------------------------------------- #
# Pure-Python helpers (stdlib only — exercised by --selftest)                  #
# --------------------------------------------------------------------------- #
def _centroid(coords: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    """Mean (x, y, z) of *coords*."""
    if not coords:
        raise ValueError("no atomic coordinates found")
    n = len(coords)
    sx = sum(c[0] for c in coords)
    sy = sum(c[1] for c in coords)
    sz = sum(c[2] for c in coords)
    return (sx / n, sy / n, sz / n)


def parse_pdb_coords(pdb_path: Path) -> list[tuple[float, float, float]]:
    """Read ATOM/HETATM coordinates from a PDB (fixed-column format)."""
    coords: list[tuple[float, float, float]] = []
    for line in pdb_path.read_text().splitlines():
        if line.startswith(("ATOM", "HETATM")):
            try:
                coords.append(
                    (float(line[30:38]), float(line[38:46]), float(line[46:54]))
                )
            except ValueError:
                continue
    return coords


def parse_sdf_coords(sdf_path: Path) -> list[tuple[float, float, float]]:
    """Read atom coordinates of the first molecule in a V2000 SDF."""
    lines = sdf_path.read_text().splitlines()
    if len(lines) < 4:
        raise ValueError(f"{sdf_path} is not a valid SDF")
    counts = lines[3]
    try:  # V2000 counts line: "aaabbb..." — atom count in cols 0-3
        n_atoms = int(counts[0:3])
    except ValueError as exc:
        raise ValueError(f"unreadable SDF counts line in {sdf_path}") from exc
    coords: list[tuple[float, float, float]] = []
    for line in lines[4 : 4 + n_atoms]:
        parts = line.split()
        coords.append((float(parts[0]), float(parts[1]), float(parts[2])))
    return coords


def ligand_kind(path: Path) -> str:
    """Classify a ligand file as 'sdf' or 'smi' by extension."""
    suffix = path.suffix.lower()
    if suffix in (".sdf", ".mol", ".mdl"):
        return "sdf"
    if suffix in (".smi", ".smiles", ".txt"):
        return "smi"
    raise ValueError(
        f"unsupported ligand file '{path}': expected .sdf or .smi/.smiles"
    )


def write_box(box_path: Path, center, size) -> None:
    """Write the docking box as JSON for the dock stage to consume."""
    box_path.write_text(
        json.dumps(
            {"center": [round(float(c), 3) for c in center],
             "size": [float(s) for s in size]},
            indent=2,
        )
    )


def make_archive(staging: Path, out: Path) -> None:
    """Tar the staged ``vina_inputs`` directory to *out*."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out, "w:gz") as tar:
        tar.add(staging, arcname="vina_inputs")


# --------------------------------------------------------------------------- #
# Runtime steps (need RDKit / Meeko — only run in the uv environment)          #
# --------------------------------------------------------------------------- #
def _run(cmd: list[str]) -> None:
    """Run a subprocess, echoing the command; raise on failure."""
    print("prep.py: $", " ".join(cmd))
    subprocess.run(cmd, check=True)


def smiles_to_sdf(smi_path: Path, out_sdf: Path) -> int:
    """Embed each ``SMILES [name]`` line to a 3D, protonated SDF via RDKit.

    Mirrors w01's ``.smi`` convention: one ligand per line, optional name in the
    second column (else a stable ``lig{n}`` id). Returns the molecule count.
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem

    writer = Chem.SDWriter(str(out_sdf))
    count = 0
    for idx, raw in enumerate(smi_path.read_text().splitlines()):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        smiles = parts[0]
        name = parts[1] if len(parts) > 1 else f"lig{idx}"
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            print(f"prep.py: WARNING skipping unparseable SMILES '{smiles}'")
            continue
        mol = Chem.AddHs(mol)
        if AllChem.EmbedMolecule(mol, AllChem.ETKDGv3()) != 0:
            print(f"prep.py: WARNING could not embed 3D coords for '{name}'")
            continue
        AllChem.MMFFOptimizeMolecule(mol)
        mol.SetProp("_Name", name)
        writer.write(mol)
        count += 1
    writer.close()
    if count == 0:
        raise ValueError(f"no ligands could be embedded from {smi_path}")
    return count


def prepare_receptor(receptor: Path, staging: Path) -> Path:
    """Use OpenBabel to write a rigid ``receptor.pdbqt`` into *staging*."""
    pdbqt = staging / "receptor.pdbqt"
    _run(
        [
            "obabel", str(receptor),
            "-O", str(pdbqt),
            "-xr",           # rigid receptor (no rotatable bonds)
            "-p", "7.4",     # add hydrogens for pH 7.4
        ]
    )
    if not pdbqt.exists() or pdbqt.stat().st_size == 0:
        raise RuntimeError("obabel did not produce a receptor.pdbqt")
    return pdbqt


def prepare_ligands(ligands: Path, staging: Path) -> int:
    """Convert *ligands* (SDF or SMILES) to per-ligand PDBQT files.

    Returns the number of ligand PDBQT files written to ``staging/ligands``.
    """
    lig_dir = staging / "ligands"
    lig_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        sdf = ligands
        if ligand_kind(ligands) == "smi":
            sdf = Path(tmp) / "ligands.sdf"
            n = smiles_to_sdf(ligands, sdf)
            print(f"prep.py: embedded {n} SMILES to 3D")
        _run(
            [
                "mk_prepare_ligand.py",
                "-i", str(sdf),
                "--multimol_outdir", str(lig_dir),
            ]
        )
    written = sorted(lig_dir.glob("*.pdbqt"))
    if not written:
        raise RuntimeError("mk_prepare_ligand.py produced no PDBQT files")
    return len(written)


# --------------------------------------------------------------------------- #
# Orchestration                                                                #
# --------------------------------------------------------------------------- #
def resolve_center(args: argparse.Namespace) -> tuple[float, float, float]:
    """Resolve the box center from --center, --ref-ligand, or receptor centroid."""
    if args.center is not None:
        return tuple(args.center)
    if args.ref_ligand is not None:
        ref = Path(args.ref_ligand)
        coords = (
            parse_sdf_coords(ref)
            if ligand_kind(ref) == "sdf"
            else parse_pdb_coords(ref)
        )
        center = _centroid(coords)
        print(f"prep.py: box center from --ref-ligand = {center}")
        return center
    center = _centroid(parse_pdb_coords(args.receptor))
    print(
        "prep.py: WARNING no --center or --ref-ligand given; using receptor "
        f"centroid {center} (blind docking — use a large --size)."
    )
    return center


def build_inputs(args: argparse.Namespace) -> int:
    """Prepare receptor + ligands + box and tar them. Returns ligand count."""
    center = resolve_center(args)
    size = tuple(args.size)

    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp) / "vina_inputs"
        staging.mkdir(parents=True)
        prepare_receptor(args.receptor, staging)
        n = prepare_ligands(args.ligands, staging)
        write_box(staging / "box.json", center, size)
        make_archive(staging, args.out)

    print(f"prep.py: wrote {n} ligand(s) + receptor + box to {args.out}")
    return n


# --------------------------------------------------------------------------- #
# Self-test (stdlib only)                                                      #
# --------------------------------------------------------------------------- #
def _selftest() -> None:
    """Exercise the pure-Python helpers on tiny fixtures."""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)

        # PDB centroid: two atoms → midpoint.
        pdb = d / "r.pdb"
        pdb.write_text(
            "ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00  0.00\n"
            "ATOM      2  C   ALA A   1       2.000   4.000   6.000  1.00  0.00\n"
            "TER\n"
        )
        assert _centroid(parse_pdb_coords(pdb)) == (1.0, 2.0, 3.0)

        # SDF centroid: a 2-atom V2000 block.
        sdf = d / "ref.sdf"
        sdf.write_text(
            "ref\n  prog\n\n"
            "  2  1  0  0  0  0  0  0  0  0999 V2000\n"
            "    0.0000    0.0000    0.0000 O   0  0\n"
            "    4.0000    2.0000    0.0000 C   0  0\n"
            "  1  2  1  0\nM  END\n$$$$\n"
        )
        assert _centroid(parse_sdf_coords(sdf)) == (2.0, 1.0, 0.0)

        # Kind detection.
        assert ligand_kind(Path("a.sdf")) == "sdf"
        assert ligand_kind(Path("a.smi")) == "smi"
        try:
            ligand_kind(Path("a.mol2"))
            raise AssertionError("expected ValueError for .mol2")
        except ValueError:
            pass

        # box.json + archive assembly with fake staged files.
        staging = d / "vina_inputs"
        (staging / "ligands").mkdir(parents=True)
        (staging / "receptor.pdbqt").write_text("REMARK receptor\n")
        (staging / "ligands" / "benzene.pdbqt").write_text("REMARK ligand\n")
        write_box(staging / "box.json", (1.0, 2.0, 3.0), DEFAULT_SIZE)
        box = json.loads((staging / "box.json").read_text())
        assert box["center"] == [1.0, 2.0, 3.0], box
        assert box["size"] == [25.0, 25.0, 25.0], box

        out = d / "vina_inputs.tar.gz"
        make_archive(staging, out)
        with tarfile.open(out) as tar:
            names = set(tar.getnames())
        assert "vina_inputs/receptor.pdbqt" in names, names
        assert "vina_inputs/ligands/benzene.pdbqt" in names, names
        assert "vina_inputs/box.json" in names, names
    print("prep.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build AutoDock Vina inputs.")
    parser.add_argument("--receptor", type=Path)
    parser.add_argument("--ligands", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--center", type=float, nargs=3, metavar=("X", "Y", "Z"),
        help="docking box center in Angstrom",
    )
    parser.add_argument(
        "--size", type=float, nargs=3, metavar=("X", "Y", "Z"),
        default=list(DEFAULT_SIZE), help="docking box size in Angstrom",
    )
    parser.add_argument(
        "--ref-ligand", type=Path,
        help="reference ligand whose centroid sets the box center",
    )
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        _selftest()
        return 0
    if not (args.receptor and args.ligands and args.out):
        parser.error("--receptor, --ligands and --out are required")
    for tool in ("obabel", "mk_prepare_ligand.py"):
        if shutil.which(tool) is None:
            parser.error(f"'{tool}' not on PATH — run inside the stage's uv env")

    build_inputs(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
