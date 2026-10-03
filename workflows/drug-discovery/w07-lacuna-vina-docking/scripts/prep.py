#!/usr/bin/env python3
# Converts receptor + ligands into AutoDock Vina inputs, boxed on a Lacuna
# pocket_N_vina.conf. Writes receptor.pdbqt + box.json into --out-receptor
# (shared by every dock clone) and one PDBQT per ligand into --out-ligands
# (the folder the `dock` horus_map task iterates over).

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def parse_vina_conf(conf_path: Path) -> tuple[tuple, tuple]:
    values = {}
    for line in conf_path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if "=" in line:
            key, _, val = line.partition("=")
            values[key.strip()] = float(val.strip())
    center = (values["center_x"], values["center_y"], values["center_z"])
    size = (values["size_x"], values["size_y"], values["size_z"])
    return center, size


def prepare_receptor(receptor: Path, out_dir: Path) -> None:
    # Keep ATOM records only: drops waters/bound GDP and the RCSB header
    # lines obabel would otherwise copy into the PDBQT, which Vina rejects.
    protein_only = out_dir / "receptor_protein.pdb"
    kept = [l for l in receptor.read_text().splitlines() if l.startswith(("ATOM", "TER", "END"))]
    protein_only.write_text("\n".join(kept) + "\n")
    subprocess.run(
        ["obabel", str(protein_only), "-O", str(out_dir / "receptor.pdbqt"), "-xr", "-p", "7.4"],
        check=True,
    )


def prepare_ligands(ligands: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    sdf = ligands
    if ligands.suffix.lower() in (".smi", ".smiles"):
        from rdkit import Chem
        from rdkit.Chem import AllChem

        sdf = Path(tempfile.mkdtemp()) / "ligands.sdf"
        writer = Chem.SDWriter(str(sdf))
        for i, line in enumerate(ligands.read_text().splitlines()):
            parts = line.split()
            if not parts:
                continue
            mol = Chem.AddHs(Chem.MolFromSmiles(parts[0]))
            AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
            AllChem.MMFFOptimizeMolecule(mol)
            mol.SetProp("_Name", parts[1] if len(parts) > 1 else f"lig{i}")
            writer.write(mol)
        writer.close()

    # Not the console script: its shim breaks when the env path has a space.
    subprocess.run(
        [sys.executable, "-m", "meeko.cli.mk_prepare_ligand",
         "-i", str(sdf), "--multimol_outdir", str(out_dir)],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receptor", type=Path, required=True)
    parser.add_argument("--ligands", type=Path, required=True)
    parser.add_argument("--box-config", type=Path, required=True)
    parser.add_argument("--out-receptor", type=Path, required=True)
    parser.add_argument("--out-ligands", type=Path, required=True)
    args = parser.parse_args()

    args.out_receptor.mkdir(parents=True, exist_ok=True)
    prepare_receptor(args.receptor, args.out_receptor)

    center, size = parse_vina_conf(args.box_config)
    (args.out_receptor / "box.json").write_text(json.dumps({"center": center, "size": size}))

    prepare_ligands(args.ligands, args.out_ligands)


if __name__ == "__main__":
    main()
