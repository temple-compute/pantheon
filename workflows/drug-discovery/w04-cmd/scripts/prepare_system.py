#!/usr/bin/env python3
"""
System preparation for the cMD workflow: PDB -> solvated, ionized AMBER system.

Runs on the cluster with the AMBER module loaded (AmberTools: pdb4amber,
tleap, antechamber, parmchk2, parmed, ambpdb) plus PROPKA for pH-dependent
protonation. Stdlib Python; every AmberTools call is a subprocess.

Input modes:
  pdb_id    download https://files.rcsb.org/download/<ID>.pdb
  pdb_file  an uploaded .pdb
  amber     an existing prmtop/inpcrd (only HMR and the report apply)

PDB pipeline: first model, first altloc -> keep chains -> drop waters (unless
kept) and every hetero group except the named ligands (MSE becomes MET) ->
PROPKA states at the pH (HIS -> HIE/HIP, ASP -> ASH, GLU -> GLH, LYS -> LYN)
-> pdb4amber (disulfides -> CYX) -> each ligand: add H, antechamber AM1-BCC
GAFF2 with the given net charge, parmchk2 -> tleap: force field, water,
box, padding -> salt by SLTCAP (counts from the solvated box) -> optional
hydrogen mass repartitioning.

Outputs: system.prmtop, system.inpcrd, system.pdb, prep_report.json.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
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


def clean_pdb(text: str, chains: set[str], ligands: set[str], keep_waters: bool):
    """Split a PDB into protein lines, ligand residues and waters.

    Returns (protein, {resname: [[lines of one copy], ...]}, waters, dropped)
    where dropped counts residues of hetero groups that were removed.
    """
    protein, waters, removed = [], [], set()
    ligand_res: dict[str, dict[tuple, list[str]]] = {}
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
            line = "ATOM  " + line[6:12] + name + line[16:17] + MODIFIED[resname] + line[20:76] + (" S" if name == " SD " else line[76:78]) + line[78:]
            record, resname = "ATOM", MODIFIED[resname]
        if record == "ATOM":
            protein.append(line.rstrip())
        elif resname in WATERS:
            if keep_waters and element != "H":
                waters.append(line.rstrip())
        elif resname in ligands:
            if element != "H":  # hydrogens are re-added consistently later
                ligand_res.setdefault(resname, {}).setdefault(res_key(line), []).append(line.rstrip())
        else:
            removed.add((resname, res_key(line)))
    missing = ligands - set(ligand_res)
    if missing:
        raise SystemExit(f"Ligand residue(s) not found in the structure: {', '.join(sorted(missing))}")
    if not protein:
        raise SystemExit("No protein atoms left after filtering (check `chains`).")
    dropped = Counter(name for name, _ in removed)
    return protein, {k: list(v.values()) for k, v in ligand_res.items()}, waters, dropped


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
    """AMBER residue names for titratable residues whose state differs at pH.

    Parses PROPKA's 'SUMMARY OF THIS PREDICTION' table. HIS always gets a
    name (HIP when protonated, else HIE, tleap's default tautomer).
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


def parse_charges(spec: str) -> dict[str, int]:
    """'JZ4:0,HEM:-2' -> {'JZ4': 0, 'HEM': -2}."""
    out = {}
    for item in filter(None, (s.strip() for s in spec.split(","))):
        name, _, q = item.partition(":")
        out[name.strip().upper()] = int(q or 0)
    return out


def tleap_input(*, forcefield, water, box, padding, ligands, disulfides, out, ions=(0, 0), charge_cmd=False) -> str:
    lines = [f"source leaprc.protein.{forcefield}", f"source leaprc.water.{water}"]
    if ligands:
        lines.append("source leaprc.gaff2")
    for name in ligands:
        lines += [f"{name} = loadmol2 {name}.mol2", f"loadamberparams {name}.frcmod"]
    lines.append("m = loadpdb complex.pdb")
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

def run(cmd: list[str], cwd: Path, log: Path, ok_codes=(0,), stdout: Path | None = None) -> str:
    print("+", " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    with log.open("a") as f:
        f.write(f"\n$ {' '.join(cmd)}\n{proc.stdout}\n{proc.stderr}")
    if stdout is not None:
        stdout.write_text(proc.stdout)
    if proc.returncode not in ok_codes:
        tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-30:])
        raise SystemExit(f"{cmd[0]} failed (exit {proc.returncode}):\n{tail}")
    return proc.stdout + proc.stderr


def need(tool: str, hint: str = "") -> str:
    path = shutil.which(tool)
    if not path:
        raise SystemExit(f"`{tool}` not found on PATH. {hint or 'Is the AMBER module loaded (amber_env)?'}")
    return path


def fetch_pdb(pdb_id: str, dest: Path) -> None:
    if not re.fullmatch(r"[0-9][A-Za-z0-9]{3}", pdb_id):
        raise SystemExit(f"Not a PDB ID: {pdb_id!r} (expected 4 characters, e.g. 1AKI).")
    url = f"https://files.rcsb.org/download/{pdb_id.upper()}.pdb"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                dest.write_bytes(r.read())
            print(f"Downloaded {url}")
            return
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise SystemExit(f"{pdb_id} has no PDB-format file at RCSB (large entries are mmCIF-only); upload a .pdb instead.")
            err = e
        except OSError as e:
            err = e
        time.sleep(5 * (attempt + 1))
    raise SystemExit(f"Could not download {url}: {err}")


def protonate_ligand(name: str, heavy: Path, ph: float, cwd: Path, log: Path) -> tuple[str, str]:
    """Heavy-atom ligand PDB -> file with hydrogens; returns (file, antechamber format).

    Open Babel (protonation at the pH, bond orders perceived) writes mol2:
    its PDB output has CONECT records without bond orders, which antechamber
    reads as all-single bonds (aromatic rings typed sp3). reduce is the
    fallback (plain PDB, antechamber perceives bonds itself).
    """
    if shutil.which("obabel"):
        out = f"{name}_h.mol2"
        run(["obabel", "-ipdb", heavy.name, "-omol2", "-O", out, "-p", str(ph)], cwd, log)
        fmt = "mol2"
    elif shutil.which("reduce"):
        out = f"{name}_h.pdb"
        # reduce exits non-zero on warnings; judge by the output instead.
        run(["reduce", "-BUILD", "-NUC", heavy.name], cwd, log, ok_codes=range(256), stdout=cwd / out)
        fmt = "pdb"
    else:
        raise SystemExit("Adding ligand hydrogens needs `obabel` or `reduce` on PATH.")
    if not re.search(r"\sH\d*\s", (cwd / out).read_text()):
        raise SystemExit(f"Adding hydrogens to {name} produced no hydrogens; see prep.log.")
    return out, fmt


def hmr(prmtop: Path, cwd: Path, log: Path) -> None:
    need("parmed")
    (cwd / "hmr.in").write_text(f"HMassRepartition\noutparm {prmtop.name}.hmr\nquit\n")
    run(["parmed", "-O", "-p", prmtop.name, "-i", "hmr.in"], cwd, log)
    (cwd / f"{prmtop.name}.hmr").replace(prmtop)


def prepare_from_pdb(a: argparse.Namespace, work: Path, log: Path, report: dict) -> None:
    raw = work / "raw.pdb"
    if a.input_mode == "pdb_id":
        fetch_pdb(a.pdb_id.strip(), raw)
        report["source"] = f"RCSB {a.pdb_id.strip().upper()}"
    else:
        shutil.copy(a.structure, raw)
        report["source"] = f"uploaded {a.structure.name}"

    chains = {c.strip() for c in a.chains.split(",") if c.strip()}
    ligands = [x.strip().upper() for x in a.ligands.split(",") if x.strip()]
    charges = parse_charges(a.ligand_charges)
    protein, lig_res, waters, dropped = clean_pdb(raw.read_text(), chains, set(ligands), a.keep_waters)
    report.update(chains=sorted({l[21] for l in protein}), removed_hetero=dict(dropped),
                  crystal_waters_kept=len({res_key(w) for w in waters}))

    # Protonation of the protein.
    (work / "protein.pdb").write_text("\n".join(with_ter(protein)) + "\nEND\n")
    p4a = ["pdb4amber", "-i", "protein_prot.pdb", "-o", "protein_amber.pdb"]
    if a.protonation == "propka":
        exe = shutil.which("propka3")
        if not exe:
            raise SystemExit("protonation=propka needs PROPKA: `python3 -m pip install --user propka` "
                             "with the cluster's python, or choose protonation=reduce/none.")
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
    gaps = [l.strip() for l in p4a_log.splitlines() if "gap" in l.lower() and "A between" in l]
    report["warnings"] += [f"pdb4amber: {g}" for g in gaps]
    sslink = work / "protein_amber_sslink"
    disulfides = []
    if sslink.exists():
        disulfides = [tuple(int(x) for x in l.split()[:2]) for l in sslink.read_text().splitlines() if l.strip()]
    report["disulfides"] = [f"{a_}-{b}" for a_, b in disulfides]

    # Ligands: parameterize one copy, place every copy.
    lig_report = []
    for name in ligands:
        q = charges.get(name)
        if q is None:
            q = 0
            report["warnings"].append(f"No net charge given for {name}; assumed 0 (set ligand_charges, e.g. {name}:0).")
        (work / f"{name}_heavy.pdb").write_text("\n".join(lig_res[name][0]) + "\nEND\n")
        lig_file, lig_fmt = protonate_ligand(name, work / f"{name}_heavy.pdb", a.ph, work, log)
        need("antechamber")
        run(["antechamber", "-i", lig_file, "-fi", lig_fmt, "-o", f"{name}.mol2", "-fo", "mol2",
             "-c", "bcc", "-at", "gaff2", "-nc", str(q), "-rn", name, "-s", "2", "-pf", "y"], work, log)
        run(["parmchk2", "-i", f"{name}.mol2", "-f", "mol2", "-o", f"{name}.frcmod", "-s", "gaff2"], work, log)
        lig_report.append({"name": name, "charge": q, "copies": len(lig_res[name])})
    report["ligands"] = lig_report

    # Complex: protein, each ligand copy, crystal waters.
    body = [l for l in (work / "protein_amber.pdb").read_text().splitlines() if l.startswith(("ATOM", "HETATM", "TER"))]
    for name in ligands:
        for copy in lig_res[name]:
            body += copy + ["TER"]
    body += [w[:17] + "WAT" + w[20:] for w in waters]
    (work / "complex.pdb").write_text("\n".join(body) + "\nEND\n")

    # tleap twice: solvate to count waters and the net charge, then add ions.
    need("tleap")
    ff = dict(forcefield=a.forcefield, water=a.water, box=a.box, padding=a.padding,
              ligands=ligands, disulfides=disulfides)
    (work / "leap_solvate.in").write_text(tleap_input(**ff, out="solvated", charge_cmd=True))
    out = run(["tleap", "-f", "leap_solvate.in"], work, log)
    m = re.search(r"Total (?:unperturbed )?charge:\s*(-?\d+\.\d+)", out)
    if not m:
        raise SystemExit("tleap did not report the system charge; see prep.log.")
    charge = float(m.group(1))
    if abs(charge - round(charge)) > 0.01:
        report["warnings"].append(f"Non-integer net charge {charge:.3f}: check ligand_charges / missing atoms.")
    n_water = residue_labels((work / "solvated.prmtop").read_text()).count("WAT")
    ions = sltcap(n_water, round(charge), a.salt_mM)
    (work / "leap_final.in").write_text(tleap_input(**ff, out="system", ions=ions))
    out = run(["tleap", "-f", "leap_final.in"], work, log)
    if not (work / "system.prmtop").exists():
        raise SystemExit("tleap did not write system.prmtop; see prep.log.")
    report["warnings"] += [l.strip() for l in out.splitlines() if l.strip().startswith("WARNING")][:20]
    report.update(forcefield=a.forcefield, water=a.water, box=a.box, padding_A=a.padding,
                  salt_mM=a.salt_mM, net_charge_before_ions=round(charge, 3),
                  ions_added={"Na+": ions[0], "Cl-": ions[1]})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input-mode", choices=["pdb_id", "pdb_file", "amber"], required=True)
    ap.add_argument("--pdb-id", default="")
    ap.add_argument("--structure", type=Path, help="uploaded .pdb (pdb_file mode)")
    ap.add_argument("--prmtop", type=Path, help="amber mode")
    ap.add_argument("--inpcrd", type=Path, help="amber mode")
    ap.add_argument("--chains", default="", help="comma list; empty = all")
    ap.add_argument("--ligands", default="", help="residue names to keep and parameterize, e.g. JZ4,HEM")
    ap.add_argument("--ligand-charges", default="", help="e.g. JZ4:0,HEM:-2")
    ap.add_argument("--keep-waters", default="false")
    ap.add_argument("--protonation", choices=["propka", "reduce", "none"], default="propka")
    ap.add_argument("--ph", type=float, default=7.0)
    ap.add_argument("--forcefield", choices=["ff14SB", "ff19SB"], default="ff14SB")
    ap.add_argument("--water", choices=["tip3p", "opc"], default="tip3p")
    ap.add_argument("--box", choices=["octahedral", "cubic"], default="octahedral")
    ap.add_argument("--padding", type=float, default=12.0)
    ap.add_argument("--salt-mM", type=float, default=150.0)
    ap.add_argument("--hmr", default="false")
    ap.add_argument("--work", type=Path, default=Path("prep"))
    ap.add_argument("--out-prmtop", type=Path, required=True)
    ap.add_argument("--out-inpcrd", type=Path, required=True)
    ap.add_argument("--out-pdb", type=Path, required=True)
    ap.add_argument("--out-report", type=Path, required=True)
    a = ap.parse_args()
    a.keep_waters = a.keep_waters.lower() in ("true", "1", "yes")
    a.hmr = a.hmr.lower() in ("true", "1", "yes")

    work = a.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    log = work / "prep.log"
    report: dict = {"input_mode": a.input_mode, "warnings": []}
    if a.forcefield == "ff19SB" and a.water != "opc":
        report["warnings"].append("ff19SB is parameterized for OPC water; consider water=opc.")

    if a.input_mode == "amber":
        shutil.copy(a.prmtop, work / "system.prmtop")
        shutil.copy(a.inpcrd, work / "system.inpcrd")
        report["source"] = f"uploaded {a.prmtop.name} / {a.inpcrd.name}"
    else:
        prepare_from_pdb(a, work, log, report)

    if a.hmr:
        hmr(work / "system.prmtop", work, log)
    report["hmr"] = a.hmr
    if a.input_mode == "amber" or a.hmr:
        need("ambpdb")
        run(["ambpdb", "-p", "system.prmtop", "-c", "system.inpcrd"], work, log, stdout=work / "system.pdb")

    prmtop_text = (work / "system.prmtop").read_text()
    labels = residue_labels(prmtop_text)
    counts = Counter(labels)
    box = (work / "system.inpcrd").read_text().splitlines()[-1].split()
    report.update(
        atoms=atom_count(prmtop_text), residues=len(labels),
        solute_residues=sum(1 for x in labels if x not in SOLVENT_RESIDUES),
        waters=counts.get("WAT", 0) + counts.get("HOH", 0) + counts.get("OPC", 0),
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
    def atom(rec, serial, name, alt, res, chain, num, el, x=0.0):
        return f"{rec:<6}{serial:5d} {name:<4}{alt}{res:>3} {chain}{num:>4}    {x:8.3f}{0:8.3f}{0:8.3f}  1.00  0.00          {el:>2}"
    pdb = "\n".join([
        atom("ATOM", 1, " N", " ", "ALA", "A", "1", "N"),
        atom("ATOM", 2, " CA", "A", "HIS", "A", "2", "C"),
        atom("ATOM", 3, " CA", "B", "HIS", "A", "2", "C"),       # altloc B dropped
        atom("HETATM", 4, "SE", " ", "MSE", "A", "3", "SE"),     # -> MET SD
        atom("ATOM", 5, " CA", " ", "GLY", "B", "1", "C"),       # chain B filtered
        atom("HETATM", 6, " C1", " ", "JZ4", "A", "201", "C"),
        atom("HETATM", 7, " H1", " ", "JZ4", "A", "201", "H"),   # ligand H dropped
        atom("HETATM", 8, " C1", " ", "JZ4", "A", "202", "C"),   # second copy
        atom("HETATM", 9, " O", " ", "HOH", "A", "301", "O"),
        atom("HETATM", 10, " S", " ", "SO4", "A", "401", "S"),
        "ENDMDL",
        atom("ATOM", 11, " CA", " ", "ALA", "A", "9", "C"),      # model 2 ignored
    ])
    protein, ligs, waters, dropped = clean_pdb(pdb, {"A"}, {"JZ4"}, keep_waters=True)
    assert [l[17:20] for l in protein] == ["ALA", "HIS", "MET"], protein
    assert protein[2][12:16] == " SD " and protein[2].startswith("ATOM") and protein[1][16] == " "
    assert len(ligs["JZ4"]) == 2 and len(ligs["JZ4"][0]) == 1
    assert len(waters) == 1 and dropped["SO4"] == 1
    assert len(clean_pdb(pdb, set(), {"JZ4"}, False)[2]) == 0
    try:
        clean_pdb(pdb, {"A"}, {"XYZ"}, False)
    except SystemExit as e:
        assert "XYZ" in str(e)
    else:
        raise AssertionError("missing ligand must fail")
    assert with_ter([atom("ATOM", 1, " N", " ", "ALA", "A", "1", "N"), atom("ATOM", 2, " N", " ", "ALA", "B", "1", "N")]).count("TER") == 2

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
    renamed = apply_states([atom("ATOM", 1, " CB", " ", "ASP", "A", "52", "C")], states)
    assert renamed[0][17:20] == "ASH"

    for nw, q, c in ((10000, -8, 150), (10000, 5, 150), (3000, 0, 0), (3000, -3, 0), (50, -20, 150)):
        pos, neg = sltcap(nw, q, c)
        assert pos - neg == -q and pos >= 0 and neg >= 0, (nw, q, c, pos, neg)
    pos, neg = sltcap(10000, 0, 150)
    assert pos == neg == 27  # 10000 * 0.15 / 55.5

    assert parse_charges("JZ4:0, hem:-2,") == {"JZ4": 0, "HEM": -2}
    leap = tleap_input(forcefield="ff19SB", water="opc", box="cubic", padding=10.0,
                       ligands=["JZ4"], disulfides=[(6, 127)], out="system", ions=(30, 22))
    for want in ("source leaprc.protein.ff19SB", "source leaprc.water.opc", "source leaprc.gaff2",
                 "JZ4 = loadmol2 JZ4.mol2", "bond m.6.SG m.127.SG", "solvatebox m OPCBOX 10.0",
                 "addIonsRand m Na+ 30 Cl- 22", "saveamberparm m system.prmtop system.inpcrd"):
        assert want in leap, want
    assert "gaff2" not in tleap_input(forcefield="ff14SB", water="tip3p", box="octahedral", padding=12,
                                       ligands=[], disulfides=[], out="x")
    assert residue_labels("%FLAG RESIDUE_LABEL\n%FORMAT(20a4)\nALA WAT Na+ \n%FLAG X\n") == ["ALA", "WAT", "Na+"]
    print("prepare_system.py: self-check OK")


if __name__ == "__main__":
    import sys

    if "--self-test" in sys.argv:
        demo()
    else:
        main()
