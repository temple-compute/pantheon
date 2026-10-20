#!/usr/bin/env python3
"""
GAFF2 parameters for one ligand pose: hydrogens -> antechamber (AM1-BCC
charges, GAFF2 types) -> parmchk2. Writes ligand.mol2 (pose, types, charges)
and ligand.frcmod, which build_complex loads into tleap.

Standalone block: input is any ligand pose file (.pdb, .sdf, .mol2) --
extract_ligand's output, a docking pose, or your own file. Ligand files you
already parameterized go straight to build_complex instead.

Hydrogens: Open Babel at the pH (keeps bond orders by writing mol2; its PDB
output's CONECT records would read as all-single bonds), else reduce for
PDB input. --protonate false keeps the file's own hydrogens.

Needs AmberTools (antechamber, parmchk2) plus obabel or reduce: the
workflow's tools conda environment provides them.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from pathlib import Path

FORMATS = {".pdb": "pdb", ".ent": "pdb", ".sdf": "sdf", ".mol": "sdf", ".mol2": "mol2"}
ANTECHAMBER_FMT = {"pdb": "pdb", "sdf": "mdl", "mol2": "mol2"}


def run(cmd: list[str], cwd: Path, log: Path, ok_codes=(0,), stdout: Path | None = None) -> None:
    print("+", " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    with log.open("a") as f:
        f.write(f"\n$ {' '.join(cmd)}\n{proc.stdout}\n{proc.stderr}")
    if stdout is not None:
        stdout.write_text(proc.stdout)
    if proc.returncode not in ok_codes:
        tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-30:])
        raise SystemExit(f"{cmd[0]} failed (exit {proc.returncode}):\n{tail}")


def need(tool: str) -> None:
    if not shutil.which(tool):
        raise SystemExit(f"`{tool}` not found on PATH. Is the workflow's tools conda environment (_tools: ambertools, propka, openbabel) in use?")


def mol2_charge(text: str) -> float:
    """Sum of partial charges in a mol2's ATOM block."""
    block = text.split("@<TRIPOS>ATOM")[1].split("@<TRIPOS>")[0]
    return sum(float(line.split()[8]) for line in block.splitlines() if len(line.split()) >= 9)


def add_hydrogens(src: Path, fmt: str, ph: float, work: Path, log: Path) -> tuple[Path, str]:
    if shutil.which("obabel"):
        out = work / "ligand_h.mol2"
        run(["obabel", f"-i{fmt}", str(src), "-omol2", "-O", out.name, "-p", str(ph)], work, log)
        return out, "mol2"
    if shutil.which("reduce") and fmt == "pdb":
        out = work / "ligand_h.pdb"
        # reduce exits non-zero on warnings; judge by the output instead.
        run(["reduce", "-BUILD", "-NUC", str(src)], work, log, ok_codes=range(256), stdout=out)
        return out, "pdb"
    raise SystemExit("Adding hydrogens needs `obabel` (any format) or `reduce` (PDB) on PATH; "
                     "or pass a file that already has hydrogens with protonate=false.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ligand", type=Path, required=True, help=".pdb / .sdf / .mol2 pose")
    ap.add_argument("--resname", required=True, help="residue name in the system, e.g. JZ4")
    ap.add_argument("--charge", type=float, required=True, help="net formal charge")
    ap.add_argument("--ph", type=float, default=7.0)
    ap.add_argument("--protonate", default="true", help="false keeps the file's hydrogens")
    ap.add_argument("--work", type=Path, default=Path("ligand_work"))
    ap.add_argument("--out-mol2", type=Path, required=True)
    ap.add_argument("--out-frcmod", type=Path, required=True)
    a = ap.parse_args()

    fmt = FORMATS.get(a.ligand.suffix.lower())
    if fmt is None:
        raise SystemExit(f"Unknown ligand format {a.ligand.suffix!r}; use .pdb, .sdf or .mol2.")
    resname = a.resname.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{1,3}", resname):
        raise SystemExit(f"Residue name {resname!r}: use 1-3 letters/digits.")
    charge = round(a.charge)
    work = a.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    log = work / "ligand.log"
    src = work / f"input{a.ligand.suffix.lower()}"
    shutil.copy(a.ligand, src)

    if a.protonate.lower() in ("true", "1", "yes"):
        src, fmt = add_hydrogens(src, fmt, a.ph, work, log)
    need("antechamber")
    need("parmchk2")
    run(["antechamber", "-i", str(src), "-fi", ANTECHAMBER_FMT[fmt], "-o", "ligand.mol2", "-fo", "mol2",
         "-c", "bcc", "-at", "gaff2", "-nc", str(charge), "-rn", resname, "-s", "2", "-pf", "y"], work, log)
    run(["parmchk2", "-i", "ligand.mol2", "-f", "mol2", "-o", "ligand.frcmod", "-s", "gaff2"], work, log)

    total = mol2_charge((work / "ligand.mol2").read_text())
    if abs(total - charge) > 0.01:
        raise SystemExit(f"Charges sum to {total:.3f}, not {charge}: check the net charge / protonation.")
    missing = (work / "ligand.frcmod").read_text().count("ATTN, need revision")
    for src_name, dest in (("ligand.mol2", a.out_mol2), ("ligand.frcmod", a.out_frcmod)):
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(work / src_name, dest)
    print(f"{resname}: net charge {charge}, GAFF2 + AM1-BCC"
          + (f"; WARNING: {missing} parameter(s) parmchk2 could not assign (ATTN in frcmod)" if missing else ""))


if __name__ == "__main__":
    import sys

    if "--self-test" in sys.argv:
        mol2 = ("@<TRIPOS>MOLECULE\nJZ4\n@<TRIPOS>ATOM\n"
                "      1 C1   0.0 0.0 0.0 c3   1 JZ4  -0.25\n"
                "      2 H1   0.0 0.0 1.0 hc   1 JZ4   0.25\n@<TRIPOS>BOND\n")
        assert abs(mol2_charge(mol2)) < 1e-9
        assert FORMATS[".sdf"] == "sdf" and ANTECHAMBER_FMT["sdf"] == "mdl"
        print("parameterize_ligand.py: self-check OK")
    else:
        main()
