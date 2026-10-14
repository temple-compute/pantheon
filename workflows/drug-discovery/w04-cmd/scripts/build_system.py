#!/usr/bin/env python3
"""
Build a solvated, ionized AMBER system from a protein PDB, optionally with
one parameterized ligand (build_complex = with --ligand-mol2/--ligand-frcmod,
build_system = without).

Protein: first model, first altloc, chosen chains, MSE -> MET; every hetero
group is removed (crystal waters optionally kept); the ligand comes only
from ligand.mol2 (its pose and GAFF2 parameters, see parameterize_ligand).
Protonation: PROPKA states at the pH (HIS -> HIE/HIP, ASP -> ASH, GLU ->
GLH, LYS -> LYN), or reduce, or none; pdb4amber finds disulfides. tleap:
force field, water, box, padding; NaCl by SLTCAP on top of neutralization;
optional hydrogen mass repartitioning (ParmEd).

Outputs: system.prmtop, system.inpcrd, system.pdb, prep_report.json.
Needs AmberTools (pdb4amber, tleap, parmed) and PROPKA for
protonation=propka: the workflow's tools conda environment provides them. Stdlib Python.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path

WATERS = {"HOH", "WAT", "H2O", "DOD", "TIP3", "SOL"}
MODIFIED = {"MSE": "MET"}  # selenomethionine -> methionine (SE -> SD)
WATER_BOX = {"tip3p": "TIP3PBOX", "opc": "OPCBOX"}
BOX_CMD = {"octahedral": "solvateoct", "cubic": "solvatebox"}
SOLVENT_RESIDUES = {"WAT", "HOH", "OPC", "Na+", "Cl-", "K+"}


# --- PDB handling (pure Python, covered by the self-test) -------------------

def res_key(line: str) -> tuple[str, str]:
    """(chain, residue number + insertion code) of an ATOM/HETATM line."""
    return line[21], line[22:27].strip()


def clean_pdb(text: str, chains: set[str], keep_waters: bool):
    """Protein lines, crystal-water lines, and a count of removed hetero residues."""
    protein, waters, removed = [], [], set()
    for line in text.splitlines():
        record = line[:6].strip()
        if record == "ENDMDL":
            break  # first model only
        if record not in ("ATOM", "HETATM"):
            continue
        line = line.ljust(80)
        if line[16] not in " A1":
            continue  # first alternate location only
        line = line[:16] + " " + line[17:]
        resname, chain = line[17:20].strip(), line[21]
        if chains and chain not in chains:
            continue
        element = line[76:78].strip() or line[12:14].strip().lstrip("0123456789")[:1]
        if record == "HETATM" and resname in MODIFIED:
            name = " SD " if line[12:16].strip() == "SE" else line[12:16]
            line = ("ATOM  " + line[6:12] + name + line[16:17] + MODIFIED[resname] + line[20:76]
                    + (" S" if name == " SD " else line[76:78]) + line[78:])
            record = "ATOM"
        if record == "ATOM":
            protein.append(line.rstrip())
        elif resname in WATERS:
            if keep_waters and element != "H":
                waters.append(line[:17] + "WAT" + line[20:].rstrip())
        else:
            removed.add((resname, res_key(line)))
    if not protein:
        raise SystemExit("No protein atoms left after filtering (check `chains`).")
    return protein, waters, Counter(name for name, _ in removed)


def with_ter(lines: list[str]) -> list[str]:
    """Insert TER records between chains."""
    out, last = [], None
    for line in lines:
        if last is not None and line[21] != last:
            out.append("TER")
        out.append(line)
        last = line[21]
    return out + ["TER"]


def propka_states(pka_text: str, ph: float) -> dict[tuple[str, str], str]:
    """AMBER residue names for titratable residues at pH, from PROPKA's summary.

    HIS always gets a name (HIP when protonated, else HIE, tleap's default).
    """
    states, in_summary = {}, False
    for line in pka_text.splitlines():
        if "SUMMARY OF THIS PREDICTION" in line:
            in_summary = True
            continue
        if in_summary:
            if line.startswith("---"):
                break
            parts = line.split()
            if len(parts) < 4 or not re.fullmatch(r"-?\d+", parts[1]):
                continue
            resname, resnum, chain, pka = parts[0], parts[1], parts[2], float(parts[3])
            new = {
                "HIS": "HIP" if pka > ph else "HIE",
                "ASP": "ASH" if pka > ph else None,
                "GLU": "GLH" if pka > ph else None,
                "LYS": "LYN" if pka < ph else None,
            }.get(resname)
            if new:
                states[(chain, resnum)] = new
    return states


def apply_states(lines: list[str], states: dict[tuple[str, str], str]) -> list[str]:
    out = []
    for line in lines:
        if line.startswith("ATOM") and (line[21], line[22:26].strip()) in states:
            line = line[:17] + states[(line[21], line[22:26].strip())] + line[20:]
        out.append(line)
    return out


def sltcap(n_water: int, charge: int, conc_mM: float) -> tuple[int, int]:
    """(cations, anions) for a salt concentration in a box of n_water waters.

    SLTCAP (Schmit et al., JCTC 2018): N0 = Nw * c / 55.5 M, then
    N+/- = N0 (sqrt(1 + y^2) -/+ y), y = Q / (2 N0). Rounded so the system
    ends neutral. conc 0 = neutralize only.
    """
    if conc_mM <= 0:
        return max(0, -charge), max(0, charge)
    n0 = n_water * conc_mM / 1000 / 55.5
    y = charge / (2 * n0) if n0 else 0
    n_pos = round(n0 * (math.sqrt(1 + y * y) - y))
    n_neg = n_pos + charge  # n_pos - n_neg == -charge
    if n_neg < 0:
        n_pos, n_neg = n_pos - n_neg, 0
    return n_pos, n_neg


def mol2_info(text: str) -> tuple[str, float]:
    """(residue name, net charge) of a parameterized ligand mol2."""
    block = text.split("@<TRIPOS>ATOM")[1].split("@<TRIPOS>")[0]
    rows = [line.split() for line in block.splitlines() if len(line.split()) >= 9]
    return rows[0][7], sum(float(r[8]) for r in rows)


def tleap_input(*, forcefield, water, box, padding, ligand, waters, disulfides, out,
                ions=(0, 0), charge_cmd=False) -> str:
    """Protein first, then the ligand, then crystal waters: residue numbers of
    the protein match pdb4amber's (disulfide bonds), and the ligand is the
    last solute residue (restraint masks, analysis)."""
    lines = [f"source leaprc.protein.{forcefield}", f"source leaprc.water.{water}"]
    parts = ["prot"]
    if ligand:
        lines += ["source leaprc.gaff2", "lig = loadmol2 ligand.mol2", "loadamberparams ligand.frcmod"]
        parts.append("lig")
    lines.append("prot = loadpdb protein_amber.pdb")
    if waters:
        lines.append("xwat = loadpdb waters.pdb")
        parts.append("xwat")
    lines.append(f"m = combine {{{' '.join(parts)}}}")
    lines += [f"bond m.{a}.SG m.{b}.SG" for a, b in disulfides]
    lines.append(f"{BOX_CMD[box]} m {WATER_BOX[water]} {padding}")
    if charge_cmd:
        lines.append("charge m")
    n_pos, n_neg = ions
    if n_pos or n_neg:
        lines.append("addIonsRand m" + (f" Na+ {n_pos}" if n_pos else "") + (f" Cl- {n_neg}" if n_neg else ""))
    lines += [f"saveamberparm m {out}.prmtop {out}.inpcrd", f"savepdb m {out}.pdb", "quit", ""]
    return "\n".join(lines)


def residue_labels(prmtop_text: str) -> list[str]:
    """Residue names from a prmtop's %FLAG RESIDUE_LABEL (20a4)."""
    labels, inside = [], False
    for line in prmtop_text.splitlines():
        if line.startswith("%FLAG"):
            inside = line.split()[1] == "RESIDUE_LABEL"
        elif inside and not line.startswith("%"):
            labels += [line[i:i + 4].strip() for i in range(0, len(line), 4)]
    return [x for x in labels if x]


def atom_count(prmtop_text: str) -> int:
    lines = prmtop_text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("%FLAG POINTERS"):
            return int(lines[i + 2].split()[0])
    return 0


# --- AmberTools calls ---------------------------------------------------------

def run(cmd: list[str], cwd: Path, log: Path) -> str:
    print("+", " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    with log.open("a") as f:
        f.write(f"\n$ {' '.join(cmd)}\n{proc.stdout}\n{proc.stderr}")
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-30:])
        raise SystemExit(f"{cmd[0]} failed (exit {proc.returncode}):\n{tail}")
    return proc.stdout + proc.stderr


def need(tool: str, hint: str = "") -> str:
    path = shutil.which(tool)
    if not path:
        raise SystemExit(f"`{tool}` not found on PATH. {hint or "Is the workflow's tools conda environment (_tools: ambertools, propka, openbabel) in use?"}")
    return path


def build(a: argparse.Namespace, work: Path, log: Path, report: dict) -> None:
    chains = {c.strip() for c in a.chains.split(",") if c.strip()}
    protein, waters, dropped = clean_pdb(a.structure.read_text(), chains, a.keep_waters)
    report.update(source=a.structure.name, chains=sorted({l[21] for l in protein}),
                  removed_hetero=dict(dropped), crystal_waters_kept=len({res_key(w) for w in waters}))

    (work / "protein.pdb").write_text("\n".join(with_ter(protein)) + "\nEND\n")
    p4a = ["pdb4amber", "-i", "protein_prot.pdb", "-o", "protein_amber.pdb"]
    if a.protonation == "propka":
        exe = shutil.which("propka3")
        if not exe:
            raise SystemExit("protonation=propka needs PROPKA (propka3), which the workflow's tools "
                             "conda environment provides; or choose protonation=reduce/none.")
        run([exe, "--pH", str(a.ph), "protein.pdb"], work, log)
        states = propka_states((work / "protein.pka").read_text(), a.ph)
        (work / "protein_prot.pdb").write_text("\n".join(apply_states(with_ter(protein), states)) + "\nEND\n")
        p4a.append("-y")
        report["protonation"] = {"method": f"PROPKA at pH {a.ph}",
                                 "changed": {f"{c}:{n}": s for (c, n), s in sorted(states.items()) if s != "HIE"}}
    else:
        shutil.copy(work / "protein.pdb", work / "protein_prot.pdb")
        p4a.append("--reduce" if a.protonation == "reduce" else "-y")
        report["protonation"] = {"method": a.protonation}
    need("pdb4amber")
    p4a_log = run(p4a, work, log)
    report["warnings"] += [f"pdb4amber: {l.strip()}" for l in p4a_log.splitlines()
                           if "gap" in l.lower() and "A between" in l]
    sslink = work / "protein_amber_sslink"
    disulfides = []
    if sslink.exists():
        disulfides = [tuple(int(x) for x in l.split()[:2]) for l in sslink.read_text().splitlines() if l.strip()]
    report["disulfides"] = [f"{x}-{y}" for x, y in disulfides]

    ligand = a.ligand_mol2 is not None
    if ligand:
        shutil.copy(a.ligand_mol2, work / "ligand.mol2")
        shutil.copy(a.ligand_frcmod, work / "ligand.frcmod")
        name, q = mol2_info((work / "ligand.mol2").read_text())
        report["ligand"] = {"name": name, "charge": round(q, 3)}
    if waters:
        (work / "waters.pdb").write_text("\n".join(waters) + "\nEND\n")

    # tleap twice: solvate to count waters and the net charge, then add ions.
    need("tleap")
    ff = dict(forcefield=a.forcefield, water=a.water, box=a.box, padding=a.padding,
              ligand=ligand, waters=bool(waters), disulfides=disulfides)
    (work / "leap_solvate.in").write_text(tleap_input(**ff, out="solvated", charge_cmd=True))
    out = run(["tleap", "-f", "leap_solvate.in"], work, log)
    m = re.search(r"Total (?:unperturbed )?charge:\s*(-?\d+\.\d+)", out)
    if not m:
        raise SystemExit("tleap did not report the system charge; see build.log.")
    charge = float(m.group(1))
    if abs(charge - round(charge)) > 0.01:
        report["warnings"].append(f"Non-integer net charge {charge:.3f}: check the ligand charge / missing atoms.")
    n_water = residue_labels((work / "solvated.prmtop").read_text()).count("WAT")
    ions = sltcap(n_water, round(charge), a.salt_mM)
    (work / "leap_final.in").write_text(tleap_input(**ff, out="system", ions=ions))
    out = run(["tleap", "-f", "leap_final.in"], work, log)
    if not (work / "system.prmtop").exists():
        raise SystemExit("tleap did not write system.prmtop; see build.log.")
    report["warnings"] += [l.strip() for l in out.splitlines() if l.strip().startswith("WARNING")][:20]
    report.update(forcefield=a.forcefield, water=a.water, box=a.box, padding_A=a.padding,
                  salt_mM=a.salt_mM, net_charge_before_ions=round(charge, 3),
                  ions_added={"Na+": ions[0], "Cl-": ions[1]})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--structure", type=Path, required=True, help="protein .pdb")
    ap.add_argument("--ligand-mol2", type=Path, help="parameterized ligand (build_complex)")
    ap.add_argument("--ligand-frcmod", type=Path)
    ap.add_argument("--chains", default="", help="comma list; empty = all")
    ap.add_argument("--keep-waters", default="false")
    ap.add_argument("--protonation", choices=["propka", "reduce", "none"], default="propka")
    ap.add_argument("--ph", type=float, default=7.0)
    ap.add_argument("--forcefield", choices=["ff14SB", "ff19SB"], default="ff14SB")
    ap.add_argument("--water", choices=["tip3p", "opc"], default="tip3p")
    ap.add_argument("--box", choices=["octahedral", "cubic"], default="octahedral")
    ap.add_argument("--padding", type=float, default=12.0)
    ap.add_argument("--salt-mM", type=float, default=150.0)
    ap.add_argument("--hmr", default="false")
    ap.add_argument("--work", type=Path, default=Path("build"))
    ap.add_argument("--out-prmtop", type=Path, required=True)
    ap.add_argument("--out-inpcrd", type=Path, required=True)
    ap.add_argument("--out-pdb", type=Path, required=True)
    ap.add_argument("--out-report", type=Path, required=True)
    a = ap.parse_args()
    if (a.ligand_mol2 is None) != (a.ligand_frcmod is None):
        raise SystemExit("Pass both --ligand-mol2 and --ligand-frcmod, or neither.")
    a.keep_waters = a.keep_waters.lower() in ("true", "1", "yes")
    hmr = a.hmr.lower() in ("true", "1", "yes")

    work = a.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    log = work / "build.log"
    report: dict = {"warnings": []}
    if a.forcefield == "ff19SB" and a.water != "opc":
        report["warnings"].append("ff19SB is parameterized for OPC water; consider water=opc.")
    build(a, work, log, report)

    if hmr:
        need("parmed")
        (work / "hmr.in").write_text("HMassRepartition\noutparm system.prmtop.hmr\nquit\n")
        run(["parmed", "-O", "-p", "system.prmtop", "-i", "hmr.in"], work, log)
        (work / "system.prmtop.hmr").replace(work / "system.prmtop")
    report["hmr"] = hmr

    prmtop_text = (work / "system.prmtop").read_text()
    labels = residue_labels(prmtop_text)
    counts = Counter(labels)
    box = (work / "system.inpcrd").read_text().splitlines()[-1].split()
    report.update(
        atoms=atom_count(prmtop_text), residues=len(labels),
        solute_residues=sum(1 for x in labels if x not in SOLVENT_RESIDUES),
        waters=counts.get("WAT", 0),
        ions={k: counts[k] for k in ("Na+", "Cl-", "K+") if counts.get(k)},
        box_A=[float(x) for x in box[:3]] if len(box) >= 6 else None,
    )
    for src, dest in (("system.prmtop", a.out_prmtop), ("system.inpcrd", a.out_inpcrd), ("system.pdb", a.out_pdb)):
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(work / src, dest)
    a.out_report.parent.mkdir(parents=True, exist_ok=True)
    a.out_report.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


def demo() -> None:
    """Self-check of the pure-Python parts (no AmberTools needed)."""
    def atom(rec, serial, name, alt, res, chain, num, el):
        return f"{rec:<6}{serial:5d} {name:<4}{alt}{res:>3} {chain}{num:>4}    {0:8.3f}{0:8.3f}{0:8.3f}  1.00  0.00          {el:>2}"
    pdb = "\n".join([
        atom("ATOM", 1, " N", " ", "ALA", "A", "1", "N"),
        atom("ATOM", 2, " CA", "A", "HIS", "A", "2", "C"),
        atom("ATOM", 3, " CA", "B", "HIS", "A", "2", "C"),       # altloc B dropped
        atom("HETATM", 4, "SE", " ", "MSE", "A", "3", "SE"),     # -> MET SD
        atom("ATOM", 5, " CA", " ", "GLY", "B", "1", "C"),       # chain B filtered
        atom("HETATM", 6, " C1", " ", "JZ4", "A", "201", "C"),   # hetero removed
        atom("HETATM", 7, " C2", " ", "JZ4", "A", "201", "C"),
        atom("HETATM", 8, " O", " ", "HOH", "A", "301", "O"),
        atom("HETATM", 9, " S", " ", "SO4", "A", "401", "S"),
        "ENDMDL",
        atom("ATOM", 10, " CA", " ", "ALA", "A", "9", "C"),      # model 2 ignored
    ])
    protein, waters, dropped = clean_pdb(pdb, {"A"}, keep_waters=True)
    assert [l[17:20] for l in protein] == ["ALA", "HIS", "MET"], protein
    assert protein[2][12:16] == " SD " and protein[2].startswith("ATOM") and protein[1][16] == " "
    assert len(waters) == 1 and waters[0][17:20] == "WAT"
    assert dropped == {"JZ4": 1, "SO4": 1}, dropped
    assert clean_pdb(pdb, set(), False)[1] == []
    assert with_ter([atom("ATOM", 1, " N", " ", "ALA", "A", "1", "N"),
                     atom("ATOM", 2, " N", " ", "ALA", "B", "1", "N")]).count("TER") == 2

    pka = """
SUMMARY OF THIS PREDICTION
       Group      pKa  model-pKa   ligand atom-type
   ASP  48 A     3.36       3.80
   ASP  52 A     7.90       3.80
   GLU  35 A     6.20       4.50
   HIS  15 A     6.90       6.50
   HIS  20 A     5.10       6.50
   LYS  13 A    10.40      10.50
   LYS  96 A     6.00      10.50
   N+    1 A     7.70       8.00
--------------------------------------------------------------------------------------------------------
"""
    states = propka_states(pka, 7.0)
    assert states == {("A", "52"): "ASH", ("A", "15"): "HIE", ("A", "20"): "HIE", ("A", "96"): "LYN"}, states
    assert propka_states(pka, 6.0)[("A", "15")] == "HIP" and propka_states(pka, 6.0)[("A", "35")] == "GLH"
    assert apply_states([atom("ATOM", 1, " CB", " ", "ASP", "A", "52", "C"), "TER"], states)[0][17:20] == "ASH"

    for nw, q, c in ((10000, -8, 150), (10000, 5, 150), (3000, 0, 0), (3000, -3, 0), (50, -20, 150)):
        pos, neg = sltcap(nw, q, c)
        assert pos - neg == -q and pos >= 0 and neg >= 0, (nw, q, c, pos, neg)
    assert sltcap(10000, 0, 150) == (27, 27)  # 10000 * 0.15 / 55.5

    mol2 = ("@<TRIPOS>MOLECULE\nJZ4\n@<TRIPOS>ATOM\n"
            "      1 C1   0.0 0.0 0.0 c3   1 JZ4  -0.25\n"
            "      2 H1   0.0 0.0 1.0 hc   1 JZ4   0.25\n@<TRIPOS>BOND\n")
    assert mol2_info(mol2)[0] == "JZ4" and abs(mol2_info(mol2)[1]) < 1e-9
    leap = tleap_input(forcefield="ff19SB", water="opc", box="cubic", padding=10.0, ligand=True,
                       waters=True, disulfides=[(6, 127)], out="system", ions=(30, 22))
    for want in ("source leaprc.protein.ff19SB", "source leaprc.water.opc", "source leaprc.gaff2",
                 "lig = loadmol2 ligand.mol2", "m = combine {prot lig xwat}", "bond m.6.SG m.127.SG",
                 "solvatebox m OPCBOX 10.0", "addIonsRand m Na+ 30 Cl- 22",
                 "saveamberparm m system.prmtop system.inpcrd"):
        assert want in leap, want
    plain = tleap_input(forcefield="ff14SB", water="tip3p", box="octahedral", padding=12, ligand=False,
                        waters=False, disulfides=[], out="x")
    assert "gaff2" not in plain and "m = combine {prot}" in plain and "solvateoct m TIP3PBOX 12" in plain
    assert residue_labels("%FLAG RESIDUE_LABEL\n%FORMAT(20a4)\nALA WAT Na+ \n%FLAG X\n") == ["ALA", "WAT", "Na+"]
    print("build_system.py: self-check OK")


if __name__ == "__main__":
    import sys

    if "--self-test" in sys.argv:
        demo()
    else:
        main()
