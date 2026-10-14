#!/usr/bin/env python3
"""
Per-replica trajectory analysis with cpptraj (AmberTools), one `analyze` map
clone per produced replica. Runs on the cluster next to the trajectories so
only the small results move.

Reads a produced item (system.prmtop, system.inpcrd, protocol.json,
solute_residues.txt, prod_N.{nc,mdout,rst}, preprod/*.out) and writes to
<out>:
  rmsd_first.dat   backbone RMSD vs the first production frame
  rmsd_start.dat   backbone RMSD vs the built structure (system.inpcrd)
  rmsf.dat         CA RMSF per residue
  rg.dat           solute heavy-atom radius of gyration
  hbond_count.dat  solute H-bonds per frame;  hbond_avg.dat  per H-bond occupancy
  lig_rmsd.dat     ligand heavy-atom RMSD in the protein frame (if ligands)
  lig_contacts.dat ligand-protein native contacts; lig_contact_res.dat per residue
  dry.prmtop dry.nc  solute-only, strided trajectory (for clustering)
  mdout/           production and equilibration mdouts (energies)
  info.json        chunks, frames, timing, ligands
Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path

AMINO = {
    "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HIS", "ILE", "LEU", "LYS",
    "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL",
    "ASH", "GLH", "HID", "HIE", "HIP", "HYP", "LYN", "CYX", "CYM", "ACE", "NME", "NHE",
}


def residue_labels(prmtop_text: str) -> list[str]:
    labels, inside = [], False
    for line in prmtop_text.splitlines():
        if line.startswith("%FLAG"):
            inside = line.split()[1] == "RESIDUE_LABEL"
        elif inside and not line.startswith("%"):
            labels += [line[i:i + 4].strip() for i in range(0, len(line), 4)]
    return [x for x in labels if x]


def system_summary(prmtop_text: str, labels: list[str], last: int) -> dict:
    """Composition of the simulated system, read from its topology."""
    lines = prmtop_text.splitlines()
    atoms = next((int(lines[i + 2].split()[0]) for i, l in enumerate(lines) if l.startswith("%FLAG POINTERS")), 0)
    tail = labels[last:]
    return {
        "atoms": atoms, "residues": len(labels), "solute_residues": last,
        "waters": sum(1 for x in tail if x in ("WAT", "HOH", "OPC")),
        "ions": {x: tail.count(x) for x in sorted(set(tail)) if x not in ("WAT", "HOH", "OPC")},
    }


def ligand_residues(labels: list[str], last: int) -> list[int]:
    """1-based solute residues that aren't amino acids (N/C-terminal names included)."""
    def amino(name: str) -> bool:
        return name in AMINO or (len(name) == 4 and name[0] in "NC" and name[1:] in AMINO)
    return [i for i, name in enumerate(labels[:last], 1) if not amino(name)]


def chunk_files(item: Path) -> list[Path]:
    """Finished production chunks (restart written + pmemd's closing TIMINGS section), in order."""
    done = []
    for nc in sorted(item.glob("prod_*.nc"), key=lambda p: int(re.findall(r"\d+", p.stem)[-1])):
        mdout = nc.with_suffix(".mdout")
        if nc.with_suffix(".rst").exists() and mdout.exists() and "5.  TIMINGS" in mdout.read_text(errors="replace"):
            done.append(nc)
    return done


def cpptraj_inputs(*, last: int, ligands: list[int], dry_topology: bool, trajs: list[Path], stride: int) -> tuple[str, str]:
    """(strip input that writes dry.prmtop, main analysis input)."""
    solute = f":1-{last}"
    strip = f"parm system.prmtop\nparmstrip !({solute})\nparmwrite out dry.prmtop\nrun\nquit\n"
    traj_parm = "[dry]" if dry_topology else "[full]"
    lines = ["parm system.prmtop [full]", "parm dry.prmtop [dry]"]
    lines += [f"trajin {t} 1 last {stride} parm {traj_parm}" for t in trajs]
    lines += [
        "reference system.inpcrd parm [full] [start]",
        "autoimage",
        f"rms BBfirst first ({solute})&@CA,C,N out rmsd_first.dat",
        f"rms BBstart ref [start] ({solute})&@CA,C,N out rmsd_start.dat",
        f"atomicfluct out rmsf.dat ({solute})&@CA byres",
        f"radgyr Rg ({solute})&!@H= out rg.dat",
        f"hbond HB {solute} out hbond_count.dat avgout hbond_avg.dat",
    ]
    if ligands:
        lig = ":" + ",".join(map(str, ligands))
        lines += [
            f"rms LIG first ({lig})&!@H= nofit out lig_rmsd.dat",
            f"nativecontacts ({lig})&!@H= ({solute})&!({lig})&!@H= distance 4.5 out lig_contacts.dat byresidue resout lig_contact_res.dat",
        ]
    if not dry_topology:
        lines.append(f"strip !({solute})")
    lines += ["trajout dry.nc", "run", "quit", ""]
    return strip, "\n".join(lines)


def run_cpptraj(text: str, name: str, cwd: Path) -> None:
    (cwd / name).write_text(text)
    proc = subprocess.run(["cpptraj", "-i", name], cwd=cwd, capture_output=True, text=True)
    (cwd / f"{name}.log").write_text(proc.stdout + proc.stderr)
    if proc.returncode != 0 or "Error:" in proc.stdout + proc.stderr:
        tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-30:])
        raise SystemExit(f"cpptraj ({name}) failed:\n{tail}")


def whole(text: str) -> int:
    """argparse type: UI number inputs may arrive as '3.0'."""
    return int(float(text))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--item", type=Path, required=True, help="one produced replica")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--stride", type=whole, default=0, help="every Nth saved frame; 0 = protocol.json's analysis_stride")
    a = ap.parse_args()
    if not shutil.which("cpptraj"):
        raise SystemExit("`cpptraj` not found on PATH. Is the AMBER module loaded (amber_env)?")

    item, out = a.item.resolve(), a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    protocol = json.loads((item / "protocol.json").read_text())
    last = int(protocol["last_solute_residue"])
    prmtop_text = (item / "system.prmtop").read_text()
    labels = residue_labels(prmtop_text)
    ligands = ligand_residues(labels, last)
    stride = a.stride or int(protocol.get("analysis_stride", 1))
    trajs = chunk_files(item)
    if not trajs:
        raise SystemExit(f"No finished production chunks in {item}.")

    for f in ("system.prmtop", "system.inpcrd"):
        shutil.copy(item / f, out / f)
    strip, main_in = cpptraj_inputs(last=last, ligands=ligands, dry_topology=protocol.get("ntwprt", 0) > 0,
                                    trajs=trajs, stride=max(1, stride))
    run_cpptraj(strip, "strip.in", out)
    run_cpptraj(main_in, "analysis.in", out)
    for f in ("system.prmtop", "system.inpcrd"):
        (out / f).unlink()

    (out / "mdout").mkdir(exist_ok=True)
    for f in sorted(item.glob("prod_*.mdout")) + sorted((item / "preprod").glob("*.out")):
        shutil.copy(f, out / "mdout" / (f"equil_{f.name}" if f.parent.name == "preprod" else f.name))

    frames = sum(1 for line in (out / "rmsd_first.dat").read_text().splitlines() if line.strip() and not line.startswith("#"))
    info = {
        "replica": int(protocol.get("replica", 0)),
        "chunks_planned": protocol["chunks"],
        "chunks_completed": len(trajs),
        "simulated_ns": len(trajs) * protocol["chunk_ns"],
        "frames": frames,
        "frame_ps": protocol["save_every_ps"] * max(1, stride),
        "trajectory_bytes": sum(t.stat().st_size for t in trajs),
        "last_solute_residue": last,
        "ligands": [f"{labels[i - 1]}{i}" for i in ligands],
        "system": system_summary(prmtop_text, labels, last),
        "protocol": protocol,
    }
    (out / "info.json").write_text(json.dumps(info, indent=2))
    print(json.dumps({k: v for k, v in info.items() if k != "protocol"}, indent=2))


def demo() -> None:
    """Self-check of input generation and chunk detection (no cpptraj needed)."""
    import tempfile

    labels = ["NALA", "GLY", "HIE", "CLYS", "JZ4", "WAT", "Na+"]
    assert ligand_residues(labels, 5) == [5]
    top = "%FLAG POINTERS\n%FORMAT(10I8)\n     123\n%FLAG X\n"
    assert system_summary(top, labels, 5) == {"atoms": 123, "residues": 7, "solute_residues": 5,
                                              "waters": 1, "ions": {"Na+": 1}}
    assert ligand_residues(["ACE", "ALA", "NME"], 3) == []
    strip, main_in = cpptraj_inputs(last=5, ligands=[5], dry_topology=False, trajs=[Path("prod_1.nc")], stride=2)
    assert "parmstrip !(:1-5)" in strip
    for want in ("trajin prod_1.nc 1 last 2 parm [full]", "rms BBstart ref [start]", "byres",
                 "rms LIG first (:5)&!@H= nofit", "strip !(:1-5)", "trajout dry.nc"):
        assert want in main_in, want
    _, dry_in = cpptraj_inputs(last=5, ligands=[], dry_topology=True, trajs=[Path("p.nc")], stride=1)
    assert "parm [dry]" in dry_in and "strip !" not in dry_in and "LIG" not in dry_in

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for n, finished in ((1, True), (2, True), (10, True), (3, False)):
            (tmp / f"prod_{n}.nc").write_text("x")
            (tmp / f"prod_{n}.rst").write_text("x")
            (tmp / f"prod_{n}.mdout").write_text("   5.  TIMINGS\n" if finished else "running")
        assert [p.name for p in chunk_files(tmp)] == ["prod_1.nc", "prod_2.nc", "prod_10.nc"]
    print("analyze.py: self-check OK")


if __name__ == "__main__":
    import sys

    if "--self-test" in sys.argv:
        demo()
    else:
        main()
