#!/usr/bin/env python3
"""
Stage 1 (prep) — build OpenDDE inputs from a target sequence + ligand library.

Reads a protein FASTA (first record) and a ``.smi`` ligand file, then writes a
single OpenDDE ``jobs.json`` (a top-level list with one job per ligand: protein
chain + SMILES ligand) and tars it into one archive. A single-file output is
deliberate: Horus SSH transfer is file-based, so a tarball is what crosses to a
remote GPU box.

stdlib only — runs unchanged on a local or remote target.

Usage:
    prep.py --fasta target.fasta --ligands ligands.smi --out opendde_inputs.tar.gz
    prep.py --selftest
"""

import argparse
import json
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
    ``lig{n}`` id is assigned. Ids are sanitised for use as job/dir names.
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


def build_jobs(sequence: str, ligands: list[tuple[str, str]]) -> list[dict]:
    """One OpenDDE job per ligand: protein chain + SMILES ligand."""
    return [
        {
            "name": ligand_id,
            "modelSeeds": [101],
            "sequences": [
                {"proteinChain": {"sequence": sequence, "count": 1}},
                {"ligand": {"ligand": smiles, "count": 1}},
            ],
        }
        for ligand_id, smiles in ligands
    ]


def build_inputs(fasta: Path, ligands: Path, out: Path) -> int:
    """Write ``inputs/jobs.json`` and tar it to *out*. Returns job count."""
    jobs = build_jobs(read_fasta_sequence(fasta), read_ligands(ligands))

    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp) / "inputs"
        staging.mkdir()
        (staging / "jobs.json").write_text(json.dumps(jobs, indent=2))
        with tarfile.open(out, "w:gz") as tar:
            tar.add(staging, arcname="inputs")
    return len(jobs)


def _selftest() -> None:
    """Build inputs from a tiny fixture and assert the archive is well-formed."""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "t.fasta").write_text(">target\nMVLSPADK\nTNVKAAW\n")
        (d / "l.smi").write_text("CCO ethanol\nc1ccccc1\n# comment\n")
        out = d / "opendde_inputs.tar.gz"
        n = build_inputs(d / "t.fasta", d / "l.smi", out)
        assert n == 2, n
        with tarfile.open(out) as tar:
            jobs = json.loads(tar.extractfile("inputs/jobs.json").read())
        assert [j["name"] for j in jobs] == ["ethanol", "lig1"], jobs
        seqs = jobs[0]["sequences"]
        assert seqs[0]["proteinChain"]["sequence"] == "MVLSPADKTNVKAAW", seqs
        assert seqs[1]["ligand"]["ligand"] == "CCO", seqs
    print("prep.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build OpenDDE inputs.")
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
    print(f"prep.py: wrote {n} OpenDDE jobs to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
