#!/usr/bin/env python3
"""
Stage 1 (prep) — build Boltz-2 inputs from a target sequence + ligand library.

Reads a protein FASTA (first record) and a ``.smi`` ligand file, then writes one
Boltz-2 input YAML per ligand (protein chain A + ligand chain B, with an
``affinity`` property so Boltz-2 predicts binding) and tars them into a single
archive. A single-file output is deliberate: Horus SSH transfer is file-based,
so a tarball is what crosses to the GPU box.

stdlib only — runs unchanged on a local or remote target.

Usage:
    prep.py --fasta target.fasta --ligands ligands.smi --out boltz_inputs.tar.gz
    prep.py --selftest
"""

import argparse
import sys
import tarfile
import tempfile
from pathlib import Path


def read_fasta_sequence(fasta_path: Path) -> str:
    """Return the concatenated sequence of the first record in *fasta_path*."""
    seq: list[str] = []
    started = False
    for line in fasta_path.read_text().splitlines():
        line = line.strip()
        if line.startswith(">"):
            if started:  # second record — stop at the first sequence
                break
            started = True
            continue
        if line:
            seq.append(line)
    sequence = "".join(seq)
    if not sequence:
        raise ValueError(f"No sequence found in {fasta_path}")
    return sequence


def read_ligands(smi_path: Path) -> list[tuple[str, str]]:
    """Parse a ``.smi`` file into ``[(ligand_id, smiles), ...]``.

    Each non-empty line is ``SMILES [name]``; when the name is absent a stable
    ``lig{n}`` id is assigned. Ids are sanitised for use as filenames.
    """
    ligands: list[tuple[str, str]] = []
    for idx, raw in enumerate(smi_path.read_text().splitlines()):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        smiles = parts[0]
        name = parts[1] if len(parts) > 1 else f"lig{idx}"
        safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in name)
        ligands.append((safe, smiles))
    if not ligands:
        raise ValueError(f"No ligands found in {smi_path}")
    return ligands


def boltz_yaml(sequence: str, smiles: str) -> str:
    """Render a Boltz-2 input YAML for one protein+ligand complex.

    SMILES is emitted as a single-quoted YAML scalar (``'`` doubled) so special
    characters never break parsing. Hand-rendered to keep this script
    dependency-free.
    """
    smiles_escaped = smiles.replace("'", "''")
    return (
        "version: 1\n"
        "sequences:\n"
        "  - protein:\n"
        "      id: A\n"
        f"      sequence: {sequence}\n"
        "  - ligand:\n"
        "      id: B\n"
        f"      smiles: '{smiles_escaped}'\n"
        "properties:\n"
        "  - affinity:\n"
        "      binder: B\n"
    )


def build_inputs(fasta: Path, ligands: Path, out: Path) -> int:
    """Write per-ligand YAMLs and tar them to *out*. Returns ligand count."""
    sequence = read_fasta_sequence(fasta)
    records = read_ligands(ligands)

    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp) / "inputs"
        staging.mkdir()
        for ligand_id, smiles in records:
            (staging / f"{ligand_id}.yaml").write_text(
                boltz_yaml(sequence, smiles)
            )
        with tarfile.open(out, "w:gz") as tar:
            tar.add(staging, arcname="inputs")
    return len(records)


def _selftest() -> None:
    """Build inputs from a tiny fixture and assert the archive is well-formed."""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "t.fasta").write_text(">target\nMVLSPADK\nTNVKAAW\n")
        (d / "l.smi").write_text("CCO ethanol\nc1ccccc1\n# comment\n")
        out = d / "boltz_inputs.tar.gz"
        n = build_inputs(d / "t.fasta", d / "l.smi", out)
        assert n == 2, n
        with tarfile.open(out) as tar:
            names = sorted(tar.getnames())
            body = tar.extractfile("inputs/ethanol.yaml").read().decode()
        assert "inputs/ethanol.yaml" in names, names
        assert "inputs/lig1.yaml" in names, names  # unnamed second ligand
        assert "sequence: MVLSPADKTNVKAAW" in body, body  # records concatenated
        assert "smiles: 'CCO'" in body, body
        assert "binder: B" in body, body
    print("prep.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Boltz-2 inputs.")
    parser.add_argument("--fasta", type=Path)
    parser.add_argument("--ligands", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        _selftest()
        return 0
    if not (args.fasta and args.ligands and args.out):
        parser.error("--fasta, --ligands and --out are required")

    n = build_inputs(args.fasta, args.ligands, args.out)
    print(f"prep.py: wrote {n} Boltz-2 inputs to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
