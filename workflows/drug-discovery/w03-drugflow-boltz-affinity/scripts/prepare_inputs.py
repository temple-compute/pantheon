"""Build the Boltz-2 affinity input folder for the generated molecules.

Reads the DrugFlow SDF, extracts the target sequence from the PDB, and writes
one ``<name>.yaml`` per molecule into ``<out>/``, plus a ``{name: smiles}``
JSON map consumed by the ranking stage.

The predict stage then runs ``boltz predict <out>`` over the whole folder in a
single call. The YAML stem becomes Boltz's prediction name
(``affinity_<stem>.json``), which is the key the ranking stage joins against, so
it must be the molecule name, not a constant like ``mol.yaml``.

MSAs are not built here: the predict stage runs ``boltz predict
--use_msa_server``.
"""

from __future__ import annotations

import argparse
import json
import os
import re


def sequence_from_pdb(pdb_path: str) -> str:
    """Return the amino-acid sequence of the longest protein chain in a PDB."""
    from Bio.PDB import PDBParser  # type: ignore[import-not-found]
    from Bio.PDB.Polypeptide import PPBuilder  # type: ignore[import-not-found]

    parser = PDBParser(QUIET=True)
    structure = parser.get_structure("target", pdb_path)
    builder = PPBuilder()
    sequences = [
        str(pp.get_sequence()) for pp in builder.build_peptides(structure)
    ]
    if not sequences:
        raise RuntimeError(f"No protein chain found in {pdb_path}.")
    return max(sequences, key=len)


def molecules_from_sdf(sdf_path: str) -> list[tuple[str, str]]:
    """Return ``(name, smiles)`` tuples for each molecule in an SDF."""
    from rdkit import Chem  # type: ignore[import-not-found]

    supplier = Chem.SDMolSupplier(sdf_path, removeHs=False)
    molecules = []
    for index, mol in enumerate(supplier):
        if mol is None:
            continue
        name = mol.GetProp("_Name") if mol.HasProp("_Name") else ""
        name = name.strip() or f"mol_{index + 1}"
        smiles = Chem.MolToSmiles(mol)
        molecules.append((name, smiles))
    if not molecules:
        raise RuntimeError(f"No valid molecules parsed from {sdf_path}.")
    return molecules


def write_boltz_yaml(path: str, sequence: str, smiles: str) -> None:
    """Write a Boltz affinity YAML for a single protein/ligand pair."""
    lines = [
        "version: 1",
        "sequences:",
        "  - protein:",
        "      id: A",
        f'      sequence: "{sequence}"',
        "  - ligand:",
        "      id: B",
        f'      smiles: "{smiles}"',
        "properties:",
        "  - affinity:",
        "      binder: B",
        "",
    ]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


# --- glue ----------------------------------------------------------------


def _safe_name(name: str) -> str:
    """Filesystem-safe molecule name (anything unusual becomes '_')."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Write one Boltz affinity YAML per molecule into a folder."
    )
    parser.add_argument("--protein", required=True, help="Target protein PDB.")
    parser.add_argument("--sdf", required=True, help="Generated molecules SDF.")
    parser.add_argument(
        "--out", required=True, help="Output folder holding one YAML per molecule."
    )
    parser.add_argument(
        "--smiles-map", required=True, help="Output {name: smiles} JSON path."
    )
    args = parser.parse_args()

    sequence = sequence_from_pdb(args.protein)
    molecules = molecules_from_sdf(args.sdf)

    os.makedirs(args.out, exist_ok=True)
    smiles_by_name: dict[str, str] = {}
    for name, smiles in molecules:
        safe = _safe_name(name)
        smiles_by_name[safe] = smiles
        write_boltz_yaml(os.path.join(args.out, f"{safe}.yaml"), sequence, smiles)

    with open(args.smiles_map, "w", encoding="utf-8") as fh:
        json.dump(smiles_by_name, fh, indent=2)

    print(f"Wrote {len(molecules)} Boltz input YAMLs to {args.out}")


if __name__ == "__main__":
    main()
