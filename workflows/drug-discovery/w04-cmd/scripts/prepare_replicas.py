#!/usr/bin/env python3
"""
Generation half of MolBioMedUAB/protocols/MD/cMD/create_md_custom.sh, ported
to Python (stdlib only) and split from job submission, which Horus now owns.

Renders the AMBER .mdin files for the 10-step equilibration protocol and the
chunked production from two templates (templates/min.in, templates/md.in) and
the PROTOCOL table below, and writes one self-contained "slot" per replica:

    <out>/<i>/
        amber.sh             # the chosen AMBER module line (amber_env dropdown)
        equilibrate.sh       production.sh   live_monitor.sh   analyze.py
        system.prmtop        system.inpcrd
        preprod/1_min.in ... preprod/10_nvt.in
        prod/prod_1.in ... prod/prod_<N>.in   # one per chunk (own ig seed)
        steps.txt            # production chunk count, ceil(length_ns / chunk_ns)
        solute_residues.txt  # last solute residue (masks, analysis, ntwprt)
        protocol.json        # every resolved MD setting, for the report

Self-contained because a Horus `horus_map` clone receives exactly one
materialized item path and no other inputs -- see workflow.yaml's
`equilibrate` task; equilibrate and produce then copy the slot forward.

Templates are read from templates.tar.gz (`tar -czf templates.tar.gz -C
templates .`): tc-os's workflow import does not support folder artifacts
yet. Regenerate it whenever a template under templates/ changes.
"""

import argparse
import json
import math
import shutil
import tarfile
from pathlib import Path
from string import Template

# The equilibration schedule of create_md_custom.sh. Lengths are ns at
# equil_scale=1 (or maxcyc for minimizations); weights are kcal/mol/A^2 before
# restraint_scale. "solute" restrains solute heavy atoms, "backbone" the
# solute's CA/C/N. fresh=True draws new velocities (tempi) instead of
# restarting from the previous step's.
PROTOCOL = [
    # name,   kind,  length, ensemble, restraint,  weight, fresh
    ("1_min",  "min", 1000,   None,     "solute",   250.0, False),
    ("2_heat", "md",  2.0,    "NVT",    "solute",   100.0, True),
    ("3_npt",  "md",  1.0,    "NPT",    "solute",   100.0, False),
    ("4_npt",  "md",  1.0,    "NPT",    "solute",   10.0,  False),
    ("5_min",  "min", 1000,   None,     "backbone", 10.0,  False),
    ("6_npt",  "md",  1.0,    "NPT",    "backbone", 10.0,  True),
    ("7_npt",  "md",  1.0,    "NPT",    "backbone", 1.0,   False),
    ("8_npt",  "md",  2.0,    "NPT",    "backbone", 0.1,   False),
    ("9_npt",  "md",  2.0,    "NPT",    None,       0.0,   False),
    ("10_nvt", "md",  5.0,    "NVT",    None,       0.0,   False),
]
PREPROD_STEPS = [step[0] for step in PROTOCOL]
EQUIL_FRAME_PS = 10  # trajectory/energy output interval during equilibration

# ponytail: fixed name list for tleap's usual water models and monovalent
# ions; anything else (cofactors, metals, lipids) counts as solute. Override
# the masks with --restraint-mask when that's wrong for a system.
SOLVENT_RESIDUES = {
    "WAT", "HOH", "TIP3", "TP3", "TIP4", "TP4", "TP5", "SPC", "SOL", "OPC",
    "Na+", "Cl-", "K+", "Li+", "Rb+", "Cs+", "F-", "Br-", "I-",
    "NA", "CL", "K", "Na", "Cl",
}


def g(x: float) -> str:
    """Namelist-friendly number: 300 -> '300.0', 0.002 -> '0.002'."""
    s = f"{x:g}"
    return s if any(c in s for c in ".e") else s + ".0"


def prmtop_section(prmtop_text: str, flag: str) -> list[str]:
    """Raw fixed-width data lines of one %FLAG section."""
    # tleap pads %FLAG lines to 80 columns, and ParmEd adds %COMMENT lines,
    # so match on the flag name and skip every %-line before the data.
    lines = iter(prmtop_text.splitlines())
    for line in lines:
        if line.split()[:2] == ["%FLAG", flag]:
            break
    else:
        raise SystemExit(f"prmtop has no %FLAG {flag} section.")
    data = []
    for line in lines:
        if line.startswith("%FLAG"):
            break
        if not line.startswith("%"):
            data.append(line)
    return data


def residue_labels(prmtop_text: str) -> list[str]:
    """Residue names, in order, from %FLAG RESIDUE_LABEL (20a4)."""
    labels = [
        line[i : i + 4].strip()
        for line in prmtop_section(prmtop_text, "RESIDUE_LABEL")
        for i in range(0, len(line), 4)
    ]
    return [label for label in labels if label]


def numbers(prmtop_text: str, flag: str) -> list[float]:
    return [float(v) for line in prmtop_section(prmtop_text, flag) for v in line.split()]


def last_solute_residue(prmtop_text: str) -> tuple[int, str]:
    """1-based number and name of the last non-water, non-ion residue."""
    labels = residue_labels(prmtop_text)
    for number in range(len(labels), 0, -1):
        if labels[number - 1] not in SOLVENT_RESIDUES:
            return number, labels[number - 1]
    raise SystemExit("prmtop: every residue looks like solvent or ions.")


def last_atom_of_residue(prmtop_text: str, residue: int) -> int:
    """1-based index of the last atom of a 1-based residue (for ntwprt)."""
    pointers = [int(p) for p in numbers(prmtop_text, "RESIDUE_POINTER")]
    if residue < len(pointers):
        return pointers[residue] - 1
    return len(numbers(prmtop_text, "ATOMIC_NUMBER"))


def is_hmr(prmtop_text: str) -> bool:
    """True when hydrogens carry repartitioned mass (ParmEd HMassRepartition)."""
    elements = numbers(prmtop_text, "ATOMIC_NUMBER")
    masses = numbers(prmtop_text, "MASS")
    return any(z == 1 and m > 1.5 for z, m in zip(elements, masses))


def restraint_line(mask: str | None, weight: float) -> str:
    if not mask or weight <= 0:
        return ""
    return f'  ntr = 1, restraintmask = "{mask}", restraint_wt = {g(weight)},\n'


def protocol_inputs(p: dict, replica: int) -> dict[str, str]:
    """Rendered .mdin text per file name ('preprod/1_min.in', 'prod/prod_1.in')."""
    dt_fs = p["timestep_fs"]
    steps_per_ns = round(1e6 / dt_fs)
    masks = {"solute": p["solute_mask"], "backbone": p["backbone_mask"]}

    def seed(offset: int) -> int:
        return -1 if p["seed"] < 0 else p["seed"] + 1000 * replica + offset

    def md(title, nstlim, ensemble, mask, weight, tempi, ntwx, ntwr, ig, ntwprt=0):
        npt = ensemble == "NPT"
        return md_template.substitute(
            title=title, nstlim=nstlim, dt=g(dt_fs / 1000), ig=ig,
            irest=0 if tempi else 1, ntx=1 if tempi else 5,
            tempi=f"tempi = {g(tempi)}, " if tempi else "",
            temperature=g(p["temperature"]), ntwx=ntwx, ntpr=ntwx, ntwr=ntwr,
            ntwprt=f" ntwprt = {ntwprt}," if ntwprt else "",
            cut=g(p["cutoff"]), nscm=0 if mask and weight > 0 else 1000,
            gamma_ln=g(p["gamma_ln"]), ntb=2 if npt else 1, ntp=1 if npt else 0,
            barostat=f" barostat = 2, pres0 = {g(p['pressure_bar'])}," if npt else "",
            restraint=restraint_line(mask, weight),
        )

    min_template, md_template = p["templates"]
    out = {}
    for i, (name, kind, length, ensemble, restraint, weight, fresh) in enumerate(PROTOCOL, 1):
        mask, wt = masks.get(restraint), weight * p["restraint_scale"]
        if kind == "min":
            out[f"preprod/{name}.in"] = min_template.substitute(
                title=f"{name}: minimization, {restraint} restrained ({g(wt)})",
                maxcyc=length, ncyc=length // 2, cut=g(p["cutoff"]),
                restraint=restraint_line(mask, wt),
            )
            continue
        ns = length * p["equil_scale"]
        nstlim = max(1, round(ns * steps_per_ns))
        frame = max(1, round(EQUIL_FRAME_PS * 1000 / dt_fs))
        title = (f"Heating {g(p['heat_start_k'])} K -> {g(p['temperature'])} K"
                 if name == "2_heat" else f"{name}: {g(ns)} ns {ensemble}")
        if wt > 0 and mask:
            title += f", restraint {g(wt)} on {restraint}"
        tempi = (p["heat_start_k"] if name == "2_heat" else p["temperature"]) if fresh else None
        out[f"preprod/{name}.in"] = md(
            title, nstlim, ensemble, mask, wt, tempi,
            ntwx=min(frame, nstlim), ntwr=min(steps_per_ns, nstlim), ig=seed(i),
        )

    nstlim = round(p["chunk_ns"] * steps_per_ns)
    frame = max(1, round(p["save_every_ps"] * 1000 / dt_fs))
    for n in range(1, p["chunks"] + 1):
        out[f"prod/prod_{n}.in"] = md(
            f"Production chunk {n}/{p['chunks']}: {g(p['chunk_ns'])} ns {p['prod_ensemble']}",
            nstlim, p["prod_ensemble"], None, 0, None,
            ntwx=frame, ntwr=nstlim, ig=seed(100 + n), ntwprt=p["ntwprt"],
        )
    return out


def resolve_params(args: argparse.Namespace, prmtop_text: str) -> dict:
    """Turn CLI values + the prmtop into the full setting set (printed + saved)."""
    last, name = last_solute_residue(prmtop_text)
    hmr = is_hmr(prmtop_text)
    dt_fs = args.timestep_fs or (4.0 if hmr else 2.0)
    if dt_fs > 2.0 and not hmr:
        raise SystemExit(
            f"timestep_fs={g(dt_fs)} needs hydrogen mass repartitioning; "
            "enable hmr in prepare_system or use 2 fs."
        )
    solute = f":1-{last}&!@H="
    chunks = math.ceil(args.length_ns / args.chunk_ns)
    write_solvent = args.write_solvent.lower() not in ("false", "0", "no")
    return {
        "temperature": args.temperature,
        "length_ns": args.length_ns,
        "replicas": args.replicas,
        "last_solute_residue": last,
        "last_solute_name": name,
        "hmr": hmr,
        "timestep_fs": dt_fs,
        "cutoff": args.cutoff,
        "gamma_ln": args.gamma_ln,
        "pressure_bar": args.pressure_bar,
        "restraint_scale": args.restraint_scale,
        "solute_mask": solute if args.restraint_mask in ("", "auto") else args.restraint_mask,
        "backbone_mask": f"(:1-{last})&@CA,C,N",
        "heat_start_k": args.heat_start_k,
        "equil_scale": args.equil_scale,
        "equil_ns": sum(s[2] for s in PROTOCOL if s[1] == "md") * args.equil_scale,
        "prod_ensemble": args.prod_ensemble.upper(),
        "chunk_ns": args.chunk_ns,
        "chunks": chunks,
        "save_every_ps": args.save_every_ps,
        "seed": args.seed,
        "write_solvent": write_solvent,
        "ntwprt": 0 if write_solvent else last_atom_of_residue(prmtop_text, last),
        "analysis_stride": max(1, args.analysis_stride),
        "md_engine": args.md_engine,
    }


def build_slot(slot_dir: Path, replica: int, params: dict, files: dict) -> None:
    for sub in ("preprod", "prod"):
        (slot_dir / sub).mkdir(parents=True)
    (slot_dir / "amber.sh").write_text(files["amber_env"] + "\n")
    (slot_dir / "engine.txt").write_text(params["md_engine"])
    for dest, src in files["copy"].items():
        if src is not None:
            shutil.copy(src, slot_dir / dest)
    for rel, text in protocol_inputs(params, replica).items():
        (slot_dir / rel).write_text(text)
    (slot_dir / "steps.txt").write_text(str(params["chunks"]))
    (slot_dir / "solute_residues.txt").write_text(str(params["last_solute_residue"]))
    saved = {k: v for k, v in params.items() if k != "templates"}
    (slot_dir / "protocol.json").write_text(json.dumps(saved | {"replica": replica}, indent=2))


def prepare_replicas(params: dict, templates_archive: Path, files: dict, out_dir: Path) -> int:
    """Build every replica slot under out_dir. Returns the replica count."""
    replicas = int(params["replicas"])
    width = max(1, len(str(max(replicas - 1, 0))))
    out_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(templates_archive) as tar:
        members = {Path(m.name).name: m for m in tar.getmembers() if m.isfile()}
        params["templates"] = tuple(
            Template(tar.extractfile(members[f"{n}.in"]).read().decode()) for n in ("min", "md")
        )
    for i in range(replicas):
        build_slot(out_dir / f"{i:0{width}d}", i, params, files)
    return replicas


def whole(text: str) -> int:
    """argparse type: UI number inputs may arrive as '3.0'."""
    return int(float(text))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--temperature", type=float, required=True)
    ap.add_argument("--length-ns", type=float, required=True)
    ap.add_argument("--replicas", type=whole, required=True)
    ap.add_argument("--timestep-fs", type=float, default=0, help="0 = 4 with HMR, else 2")
    ap.add_argument("--cutoff", type=float, default=9.0)
    ap.add_argument("--gamma-ln", type=float, default=3.0)
    ap.add_argument("--pressure-bar", type=float, default=1.0)
    ap.add_argument("--restraint-scale", type=float, default=1.0)
    ap.add_argument("--restraint-mask", default="auto", help="'auto' = solute heavy atoms")
    ap.add_argument("--heat-start-k", type=float, default=100.0)
    ap.add_argument("--equil-scale", type=float, default=1.0)
    ap.add_argument("--prod-ensemble", choices=["NVT", "NPT", "nvt", "npt"], default="NVT")
    ap.add_argument("--chunk-ns", type=float, default=10.0)
    ap.add_argument("--save-every-ps", type=float, default=10.0)
    ap.add_argument("--seed", type=whole, default=-1)
    ap.add_argument("--write-solvent", default="true", help="false = solute-only production trajectories")
    ap.add_argument("--analysis-stride", type=whole, default=1, help="analyze every Nth saved frame")
    ap.add_argument("--templates", type=Path, required=True, help="templates.tar.gz")
    ap.add_argument("--prmtop", type=Path, required=True)
    ap.add_argument("--inpcrd", type=Path, required=True)
    ap.add_argument("--amber-env", required=True, help="Shell line that puts pmemd on PATH.")
    ap.add_argument("--md-engine", choices=["pmemd", "openmm"], default="pmemd",
                    help="pmemd/pmemd.cuda, or OpenMM via mdin_openmm.py (same .mdin files)")
    ap.add_argument("--openmm-runner", type=Path, default=None, help="mdin_openmm.py, copied into each slot")
    ap.add_argument("--equilibrate-script", type=Path, required=True)
    ap.add_argument("--production-script", type=Path, required=True)
    ap.add_argument("--live-monitor-script", type=Path, default=None)
    ap.add_argument("--analyze-script", type=Path, default=None)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    params = resolve_params(args, args.prmtop.read_text())
    for key, value in params.items():
        print(f"{key}: {value}")
    files = {
        "amber_env": args.amber_env,
        "copy": {
            "equilibrate.sh": args.equilibrate_script,
            "production.sh": args.production_script,
            "live_monitor.sh": args.live_monitor_script,
            "analyze.py": args.analyze_script,
            "mdin_openmm.py": args.openmm_runner,
            "system.prmtop": args.prmtop,
            "system.inpcrd": args.inpcrd,
        },
    }
    n = prepare_replicas(params, args.templates, files, args.out)
    print(f"Prepared {n} replica slot(s) under {args.out}")


def fake_prmtop(labels: list[str], atoms_per_res: int = 3, h_mass: float = 1.008) -> str:
    """Minimal prmtop text with the sections this script reads."""
    def block(flag, fmt, values, width):
        per = 80 // width
        rows = ["".join(values[i:i + per]) for i in range(0, len(values), per)]
        return f"{'%FLAG ' + flag:<80}\n%FORMAT({fmt})\n" + "\n".join(rows) + "\n"
    n = len(labels) * atoms_per_res
    return (
        block("ATOMIC_NUMBER", "10I8", [f"{z:8d}" for z in [7, 6, 1] * len(labels)], 8)
        + block("MASS", "5E16.8", [f"{m:16.8E}" for m in [14.01, 12.01, h_mass] * len(labels)], 16)
        + "%COMMENT  padded like tleap\n"
        + block("RESIDUE_LABEL", "20a4", [f"{x:<4}" for x in labels], 4)
        + block("RESIDUE_POINTER", "10I8", [f"{1 + i * atoms_per_res:8d}" for i in range(len(labels))], 8)
        + f"%FLAG POINTERS\n%FORMAT(10I8)\n{n:8d}\n"
    )


def demo() -> None:
    """Self-check: renders replica slots into a temp dir and asserts the protocol."""
    import io
    import re
    import tempfile

    labels = ["ALA", "GLY", "LYS", "LIG", "Na+", "Cl-"] + ["WAT"] * 18
    assert last_solute_residue(fake_prmtop(labels)) == (4, "LIG")
    assert last_atom_of_residue(fake_prmtop(labels), 4) == 12
    assert not is_hmr(fake_prmtop(labels)) and is_hmr(fake_prmtop(labels, h_mass=3.024))

    def field(text, key):
        m = re.search(rf"\b{key} = ([^,\s]+)", text)
        return m and m.group(1)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        archive = tmp / "templates.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            for f in sorted((Path(__file__).resolve().parent.parent / "templates").glob("*.in")):
                tar.add(f, arcname=f"./{f.name}")
        prmtop, hmr_prmtop = tmp / "system.prmtop", tmp / "hmr.prmtop"
        prmtop.write_text(fake_prmtop(labels))
        hmr_prmtop.write_text(fake_prmtop(labels, h_mass=3.024))
        stub = tmp / "stub.sh"
        stub.write_text("stub\n")

        def run(argv: list[str], top: Path) -> tuple[dict, Path]:
            ap_args = ["--temperature", "310", "--length-ns", "45", "--replicas", "3",
                       "--templates", str(archive), "--prmtop", str(top), "--inpcrd", str(stub),
                       "--amber-env", "module load amber/24", "--equilibrate-script", str(stub),
                       "--production-script", str(stub), "--analyze-script", str(stub)] + argv
            out = tmp / f"out{len(list(tmp.iterdir()))}"
            import sys
            old, sys.argv = sys.argv, ["prepare_replicas.py", *ap_args, "--out", str(out)]
            buf = io.StringIO()
            try:
                from contextlib import redirect_stdout
                with redirect_stdout(buf):
                    main()
            finally:
                sys.argv = old
            return json.loads((out / "0" / "protocol.json").read_text()), out

        # Defaults: today's protocol at 2 fs.
        params, out = run([], prmtop)
        assert sorted(p.name for p in out.iterdir()) == ["0", "1", "2"]
        slot = out / "0"
        assert (slot / "steps.txt").read_text() == "5"  # ceil(45/10)
        assert (slot / "amber.sh").read_text() == "module load amber/24\n"
        assert (slot / "analyze.py").exists() and not (slot / "live_monitor.sh").exists()
        heat = (slot / "preprod/2_heat.in").read_text()
        assert heat.splitlines()[0].startswith("Heating 100.0 K -> 310.0 K")
        assert field(heat, "nstlim") == "1000000" and field(heat, "dt") == "0.002"
        assert field(heat, "tempi") == "100.0" and field(heat, "temp0") == "310.0"
        assert 'restraintmask = ":1-4&!@H="' in heat and field(heat, "restraint_wt") == "100.0"
        min1 = (slot / "preprod/1_min.in").read_text()
        assert field(min1, "restraint_wt") == "250.0" and field(min1, "maxcyc") == "1000"
        npt6 = (slot / "preprod/6_npt.in").read_text()
        assert field(npt6, "tempi") == "310.0" and field(npt6, "irest") == "0"  # was 310.15
        assert '"(:1-4)&@CA,C,N"' in npt6 and field(npt6, "barostat") == "2"
        nine = (slot / "preprod/9_npt.in").read_text()
        assert not nine.startswith(" &cntrl") and "restraintmask" not in nine  # has a title, no restraint
        for name in PREPROD_STEPS:
            text = (slot / f"preprod/{name}.in").read_text()
            assert text.splitlines()[1] == " &cntrl" and "${" not in text, name
            assert name.endswith("min") or field(text, "cut") == "9.0"
        prods = sorted((slot / "prod").iterdir())
        assert len(prods) == 5
        p1 = (slot / "prod/prod_1.in").read_text()
        assert field(p1, "irest") == "1" and field(p1, "ntx") == "5"  # was irest=0
        assert field(p1, "nstlim") == "5000000" and field(p1, "ntwx") == "5000"
        assert field(p1, "ntb") == "1" and "ntwprt" not in p1 and field(p1, "ig") == "-1"
        assert params["equil_ns"] == 15.0 and params["timestep_fs"] == 2.0

        # Options: HMR auto 4 fs, NPT production, seeds, solute-only output.
        params, out = run(["--prod-ensemble", "NPT", "--seed", "7", "--write-solvent", "false",
                           "--equil-scale", "0.1", "--chunk-ns", "20", "--save-every-ps", "20",
                           "--restraint-scale", "0.5", "--cutoff", "10"], hmr_prmtop)
        assert params["timestep_fs"] == 4.0 and params["chunks"] == 3
        heat = (out / "0/preprod/2_heat.in").read_text()
        assert field(heat, "dt") == "0.004" and field(heat, "nstlim") == "50000"
        assert field(heat, "restraint_wt") == "50.0" and field(heat, "ig") == "9"
        p2 = (out / "1/prod/prod_2.in").read_text()
        assert field(p2, "ntb") == "2" and field(p2, "barostat") == "2"
        assert field(p2, "nstlim") == "5000000" and field(p2, "ntwx") == "5000"
        assert field(p2, "ntwprt") == "12" and field(p2, "ig") == str(7 + 1000 + 102)
        assert field(p2, "cut") == "10.0"

        try:
            run(["--timestep-fs", "4"], prmtop)
        except SystemExit as e:
            assert "hydrogen mass repartitioning" in str(e)
        else:
            raise AssertionError("4 fs without HMR must fail")

    print("prepare_replicas.py: self-check OK")


if __name__ == "__main__":
    import sys

    if "--self-test" in sys.argv:
        demo()
    else:
        main()
