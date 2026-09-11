#!/usr/bin/env python3
"""
Stage 3 (prep) — build AutoDock Vina inputs from a receptor + ligand library,
boxed on a Lacuna-discovered pocket.

Converts a receptor ``.pdb`` and a ligand file into the PDBQT inputs Vina needs,
resolves the docking box from a Lacuna ``pocket_N_vina.conf`` file (written by
the ``dock_prep`` task), and writes receptor + box into one output folder and
the per-ligand PDBQTs into a second. Two folders, not one nested tree: the
downstream ``dock`` task is a ``horus_map`` task, whose iterable input maps
over a ``FolderArtifact``'s own immediate children — so the folder it maps
over must hold only ligands, one PDBQT per child, with the receptor and box
living in a folder of their own that every clone additionally receives.

Adapted from w02-autodock-vina-docking/scripts/prep.py: the only difference is
the box source. w02 takes an explicit ``--center``/``--size`` or a reference
ligand; here the box comes from ``--box-config``, the ``center_x/y/z`` +
``size_x/y/z`` key = value file Lacuna emits per ranked pocket, so the search
box tracks whatever site Lacuna ranked rather than a hand-picked coordinate.

The receptor is parameterised with OpenBabel (``obabel``) — a rigid PDBQT with
hydrogens added at pH 7.4; Vina's default ``vina`` scoring uses atom types, not
receptor partial charges, so this is sufficient and robust across structures.
Ligands use Meeko's ``mk_prepare_ligand.py`` (better small-molecule typing/
torsions); both tools are on PATH inside the stage's conda environment. SMILES
ligands are embedded to 3D with RDKit before Meeko sees them.

The pure-Python helpers (box-config parsing, box.json assembly) are covered by
``--selftest`` and need neither RDKit nor Meeko, so the self-check runs anywhere.

Usage:
    prep.py --receptor r.pdb --ligands ligs.smi --box-config pocket_0_vina.conf \
            --out-receptor receptor_box/ --out-ligands ligands_pdbqt/
    prep.py --selftest
"""

from __future__ import annotations  # portable across python3 (>=3.9)

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


# --------------------------------------------------------------------------- #
# Pure-Python helpers (stdlib only — exercised by --selftest)                  #
# --------------------------------------------------------------------------- #
def parse_vina_conf(conf_path: Path) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Parse a Lacuna ``pocket_N_vina.conf`` (key = value, ``#`` comments)."""
    values: dict[str, float] = {}
    for line in conf_path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = float(val.strip())
    try:
        center = (values["center_x"], values["center_y"], values["center_z"])
        size = (values["size_x"], values["size_y"], values["size_z"])
    except KeyError as exc:
        raise ValueError(f"{conf_path} is missing {exc} — not a Vina box config") from exc
    return center, size


def extract_protein_only(receptor: Path, out_pdb: Path) -> Path:
    """Write only ``ATOM`` records (+ ``TER``/``END``) from *receptor* to *out_pdb*.

    Drops HETATM records (crystallographic waters, the bound GDP, the Mg2+
    cofactor) and every non-coordinate header/REMARK/JRNL line an RCSB export
    carries. Two reasons: obabel otherwise copies those header lines verbatim
    into the PDBQT as literal record types (``HEADER``, ``TITLE``, ...), which
    Vina's strict parser rejects outright; and docking a new ligand into a
    pocket that still contains its native ligand (GDP occupies Lacuna's
    rank-1 pocket here) would score against a physically occupied site.
    """
    kept = [
        line for line in receptor.read_text().splitlines()
        if line.startswith(("ATOM", "TER", "END"))
    ]
    if not any(line.startswith("ATOM") for line in kept):
        raise ValueError(f"{receptor} has no ATOM records to dock against")
    out_pdb.write_text("\n".join(kept) + "\n")
    return out_pdb


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


# --------------------------------------------------------------------------- #
# Runtime steps (need RDKit / Meeko — only run in the conda environment)       #
# --------------------------------------------------------------------------- #
def _run(cmd: list[str]) -> None:
    """Run a subprocess, echoing the command; raise on failure."""
    print("prep.py: $", " ".join(cmd))
    subprocess.run(cmd, check=True)


def smiles_to_sdf(smi_path: Path, out_sdf: Path) -> int:
    """Embed each ``SMILES [name]`` line to a 3D, protonated SDF via RDKit."""
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
    protein_only = staging / "receptor_protein.pdb"
    extract_protein_only(receptor, protein_only)
    _run(
        [
            "obabel", str(protein_only),
            "-O", str(pdbqt),
            "-xr",           # rigid receptor (no rotatable bonds)
            "-p", "7.4",     # add hydrogens for pH 7.4
        ]
    )
    if not pdbqt.exists() or pdbqt.stat().st_size == 0:
        raise RuntimeError("obabel did not produce a receptor.pdbqt")
    return pdbqt


def prepare_ligands(ligands: Path, lig_dir: Path) -> int:
    """Convert *ligands* (SDF or SMILES) to per-ligand PDBQT files.

    Writes flat into *lig_dir* (one PDBQT per ligand, no sub-folder): this
    directory becomes the ``horus_map`` task's iterable input downstream, and
    a ``FolderArtifact`` maps over its immediate children, so each child must
    already be one ligand. Returns the number of files written.
    """
    lig_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        sdf = ligands
        if ligand_kind(ligands) == "smi":
            sdf = Path(tmp) / "ligands.sdf"
            n = smiles_to_sdf(ligands, sdf)
            print(f"prep.py: embedded {n} SMILES to 3D")
        _run(
            [
                # Not the console script: its /bin/sh shim execs an unquoted
                # interpreter path, which breaks when the env dir has a space.
                sys.executable, "-m", "meeko.cli.mk_prepare_ligand",
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
def build_inputs(args: argparse.Namespace) -> int:
    """Prepare receptor + box into one folder, ligands into another. Returns ligand count.

    Two separate output folders, not one nested tree: ``dock`` (a
    ``horus_map`` task) needs one input shared by every clone
    (receptor + box) and a second, disjoint input to map over (one ligand
    PDBQT per clone) — a ``FolderArtifact``'s items are its own immediate
    children, so the mapped-over folder cannot also contain the receptor.
    """
    center, size = parse_vina_conf(args.box_config)
    print(f"prep.py: box from {args.box_config} = center {center} size {size}")

    args.out_receptor.mkdir(parents=True, exist_ok=True)
    prepare_receptor(args.receptor, args.out_receptor)
    write_box(args.out_receptor / "box.json", center, size)
    n = prepare_ligands(args.ligands, args.out_ligands)

    print(f"prep.py: wrote receptor + box to {args.out_receptor}, {n} ligand(s) to {args.out_ligands}")
    return n


# --------------------------------------------------------------------------- #
# Self-test (stdlib only)                                                      #
# --------------------------------------------------------------------------- #
def _selftest() -> None:
    """Exercise the pure-Python helpers on tiny fixtures."""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)

        # Vina box-config parsing, mirroring Lacuna's emitted format.
        conf = d / "pocket_0_vina.conf"
        conf.write_text(
            "# Lacuna pocket 0 - AutoDock Vina box\n"
            "# Rank 1, druggability=0.600, crypticity=0.000\n"
            "center_x = 55.106\n"
            "center_y = 40.573\n"
            "center_z = 23.009\n"
            "size_x = 20.5\n"
            "size_y = 20.5\n"
            "size_z = 20.5\n"
            "exhaustiveness = 8\n"
            "num_modes = 9\n"
        )
        center, size = parse_vina_conf(conf)
        assert center == (55.106, 40.573, 23.009), center
        assert size == (20.5, 20.5, 20.5), size

        # Missing keys raise, rather than silently docking a wrong box.
        bad = d / "bad.conf"
        bad.write_text("center_x = 1.0\n")
        try:
            parse_vina_conf(bad)
            raise AssertionError("expected ValueError for incomplete config")
        except ValueError:
            pass

        # Protein-only extraction drops HEADER/HETATM, keeps ATOM/TER/END.
        raw = d / "raw.pdb"
        raw.write_text(
            "HEADER    HYDROLASE                               24-JUN-13   4LDJ\n"
            "TITLE     SOME TITLE\n"
            "ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00  0.00           N\n"
            "HETATM    2  PB  GDP A 201       5.000   5.000   5.000  1.00  0.00           P\n"
            "TER\n"
            "END\n"
        )
        cleaned = d / "clean.pdb"
        extract_protein_only(raw, cleaned)
        text = cleaned.read_text()
        assert "HEADER" not in text and "HETATM" not in text, text
        assert "ATOM" in text and "TER" in text, text

        # Kind detection.
        assert ligand_kind(Path("a.sdf")) == "sdf"
        assert ligand_kind(Path("a.smi")) == "smi"
        try:
            ligand_kind(Path("a.mol2"))
            raise AssertionError("expected ValueError for .mol2")
        except ValueError:
            pass

        # receptor + box in one folder; ligands flat in a second folder.
        out_receptor = d / "receptor_box"
        out_ligands = d / "ligands_pdbqt"
        out_receptor.mkdir(parents=True)
        (out_receptor / "receptor.pdbqt").write_text("REMARK receptor\n")
        write_box(out_receptor / "box.json", center, size)
        box = json.loads((out_receptor / "box.json").read_text())
        assert box["center"] == [55.106, 40.573, 23.009], box
        assert box["size"] == [20.5, 20.5, 20.5], box

        out_ligands.mkdir(parents=True)
        (out_ligands / "benzene.pdbqt").write_text("REMARK ligand\n")
        assert (out_receptor / "receptor.pdbqt").exists()
        assert (out_ligands / "benzene.pdbqt").exists()
        # ligands folder must hold only ligands: horus_map maps over its
        # immediate children.
        assert [p.name for p in out_ligands.iterdir()] == ["benzene.pdbqt"]
    print("prep.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build AutoDock Vina inputs, boxed on a Lacuna pocket."
    )
    parser.add_argument("--receptor", type=Path)
    parser.add_argument("--ligands", type=Path)
    parser.add_argument(
        "--box-config", type=Path,
        help="Lacuna pocket_N_vina.conf (center_x/y/z, size_x/y/z key = value)",
    )
    parser.add_argument("--out-receptor", type=Path, help="folder for receptor.pdbqt + box.json")
    parser.add_argument("--out-ligands", type=Path, help="folder for one PDBQT per ligand")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        _selftest()
        return 0
    if not (args.receptor and args.ligands and args.box_config
            and args.out_receptor and args.out_ligands):
        parser.error(
            "--receptor, --ligands, --box-config, --out-receptor and "
            "--out-ligands are required"
        )
    if shutil.which("obabel") is None:
        parser.error("'obabel' not on PATH — run inside the stage's conda env")
    if importlib.util.find_spec("meeko.cli.mk_prepare_ligand") is None:
        parser.error("meeko not importable — run inside the stage's conda env")

    build_inputs(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
