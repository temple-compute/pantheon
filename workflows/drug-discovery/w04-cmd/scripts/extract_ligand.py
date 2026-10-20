#!/usr/bin/env python3
"""
Extract one ligand's pose from a PDB by residue name (heavy atoms, first
altloc, first matching copy; optionally restricted to a chain).

Standalone block: its output is a plain ligand .pdb, so a ligand pose you
already have (PDB/SDF/mol2, e.g. from docking) can be connected to
parameterize_ligand in its place. Stdlib only.
"""

import argparse
from pathlib import Path


def extract(pdb_text: str, resname: str, chain: str = "") -> list[str]:
    resname = resname.strip().upper()
    copy, key = [], None
    for line in pdb_text.splitlines():
        if line.startswith("ENDMDL"):
            break
        if not line.startswith(("HETATM", "ATOM  ")) or line[17:20].strip() != resname:
            continue
        if chain and line[21] != chain:
            continue
        line = line.ljust(80)
        if line[16] not in " A1":
            continue
        element = line[76:78].strip() or line[12:14].strip().lstrip("0123456789")[:1]
        if element == "H":
            continue
        this = (line[21], line[22:27])
        if key is None:
            key = this
        if this != key:
            break  # first copy only
        copy.append("HETATM" + line[6:16] + " " + line[17:].rstrip())
    if not copy:
        where = f" in chain {chain}" if chain else ""
        raise SystemExit(f"No residue named {resname}{where} in the structure.")
    return copy


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--structure", type=Path, required=True)
    ap.add_argument("--resname", required=True)
    ap.add_argument("--chain", default="")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    lines = extract(a.structure.read_text(), a.resname, a.chain.strip())
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text("\n".join(lines) + "\nEND\n")
    print(f"Extracted {a.resname.upper()} ({len(lines)} heavy atoms, chain {lines[0][21]}) -> {a.out}")


if __name__ == "__main__":
    import sys

    if "--self-test" in sys.argv:
        def atom(serial, name, alt, res, chain, num, el):
            return f"HETATM{serial:5d} {name:<4}{alt}{res:>3} {chain}{num:>4}    {0:8.3f}{0:8.3f}{0:8.3f}  1.00  0.00          {el:>2}"
        pdb = "\n".join([
            "ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00  0.00           N",
            atom(2, " C1", " ", "JZ4", "A", "201", "C"),
            atom(3, " C2", "A", "JZ4", "A", "201", "C"),
            atom(4, " C2", "B", "JZ4", "A", "201", "C"),
            atom(5, " H1", " ", "JZ4", "A", "201", "H"),
            atom(6, " C1", " ", "JZ4", "B", "202", "C"),
        ])
        got = extract(pdb, "jz4")
        assert len(got) == 2 and all(l[16] == " " for l in got), got
        assert extract(pdb, "JZ4", "B")[0][21] == "B"
        try:
            extract(pdb, "XYZ")
        except SystemExit as e:
            assert "XYZ" in str(e)
        else:
            raise AssertionError("missing ligand must fail")
        print("extract_ligand.py: self-check OK")
    else:
        main()
