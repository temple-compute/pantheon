#!/usr/bin/env python3
"""
Generation half of MolBioMedUAB/protocols/MD/cMD/create_md_custom.sh, ported
to Python (stdlib only) and split from job submission, which Horus now owns.

Renders the 12 AMBER .mdin templates (preprod steps 1-10 + prod_1/prod) with
${temperature}/${last_residue} substituted, and writes one self-contained
"slot" directory per replica:

    <out>/<i>/
        amber.sh            # copied from the amber_env artifact
        equilibrate.sh       # copied from the equilibrate_script artifact
        production.sh       # copied from the production_script artifact
        system.prmtop        system.inpcrd
        preprod/1_min.in ... preprod/10_nvt.in
        prod/prod_1.in prod/prod.in
        steps.txt            # production chunk count, ceil(length_ns / 10)

Self-contained because a Horus `horus_map` clone receives exactly one
materialized item path and no other inputs -- see workflow.yaml's
`equilibrate` task. `produce` (the second map stage) needs the same
self-containment, but gets it by `equilibrate` copying its own item
forward into its output alongside the equilibration results -- see
scripts/equilibrate.sh and workflow.yaml's `produce` task.

Templates are read from templates.tar.gz (built from templates/*.in via
`tar -czf templates.tar.gz -C templates .`): tc-os's workflow import does
not support folder artifacts yet, only file/archive ones, so the archive
-- not the templates/ directory -- is what workflow.yaml declares as the
artifact. Regenerate it whenever a template under templates/ changes.
"""

import argparse
import json
import math
import shutil
import tarfile
from pathlib import Path
from string import Template

PREPROD_STEPS = [
    "1_min", "2_heat", "3_npt", "4_npt", "5_min",
    "6_npt", "7_npt", "8_npt", "9_npt", "10_nvt",
]
PROD_STEPS = ["prod_1", "prod"]


def steps_for(length_ns: int) -> int:
    """Production chunk count: length rounded up to the next 10 ns chunk.

    Mirrors `steps=$(echo "($length + 9) / 10" | bc)` from
    create_md_custom.sh.
    """
    return math.ceil(length_ns / 10)


def render(
    templates: tarfile.TarFile, name: str, temperature: int, last_residue: int
) -> str:
    text = templates.extractfile(f"{name}.in").read().decode()
    return Template(text).substitute(
        temperature=temperature, last_residue=last_residue
    )


def build_slot(
    slot_dir: Path,
    *,
    templates: tarfile.TarFile,
    prmtop: Path,
    inpcrd: Path,
    amber_env: Path,
    equilibrate_script: Path,
    production_script: Path,
    temperature: int,
    last_residue: int,
    length_ns: int,
) -> None:
    preprod_dir = slot_dir / "preprod"
    prod_dir = slot_dir / "prod"
    preprod_dir.mkdir(parents=True)
    prod_dir.mkdir(parents=True)

    shutil.copy(amber_env, slot_dir / "amber.sh")
    shutil.copy(equilibrate_script, slot_dir / "equilibrate.sh")
    shutil.copy(production_script, slot_dir / "production.sh")
    shutil.copy(prmtop, slot_dir / "system.prmtop")
    shutil.copy(inpcrd, slot_dir / "system.inpcrd")

    for name in PREPROD_STEPS:
        text = render(templates, name, temperature, last_residue)
        (preprod_dir / f"{name}.in").write_text(text)

    for name in PROD_STEPS:
        text = render(templates, name, temperature, last_residue)
        (prod_dir / f"{name}.in").write_text(text)

    (slot_dir / "steps.txt").write_text(str(steps_for(length_ns)))


def prepare_replicas(
    *,
    params: dict,
    templates_archive: Path,
    prmtop: Path,
    inpcrd: Path,
    amber_env: Path,
    equilibrate_script: Path,
    production_script: Path,
    out_dir: Path,
) -> int:
    """Build every replica slot under out_dir. Returns the replica count."""
    replicas = int(params["replicas"])
    width = max(1, len(str(max(replicas - 1, 0))))
    out_dir.mkdir(parents=True, exist_ok=True)

    with tarfile.open(templates_archive) as templates:
        for i in range(replicas):
            build_slot(
                out_dir / f"{i:0{width}d}",
                templates=templates,
                prmtop=prmtop,
                inpcrd=inpcrd,
                amber_env=amber_env,
                equilibrate_script=equilibrate_script,
                production_script=production_script,
                temperature=int(params["temperature"]),
                last_residue=int(params["last_residue"]),
                length_ns=int(params["length_ns"]),
            )
    return replicas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--params", type=Path, required=True)
    parser.add_argument("--templates", type=Path, required=True,
                         help="templates.tar.gz")
    parser.add_argument("--prmtop", type=Path, required=True)
    parser.add_argument("--inpcrd", type=Path, required=True)
    parser.add_argument("--amber-env", type=Path, required=True)
    parser.add_argument("--equilibrate-script", type=Path, required=True)
    parser.add_argument("--production-script", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    params = json.loads(args.params.read_text())
    if params.get("last_residue", 0) == 0:
        raise SystemExit(
            "params.json: 'last_residue' is unset (0). Set it to the last "
            "residue number of protein + substrate before running -- see "
            "the README."
        )

    n = prepare_replicas(
        params=params,
        templates_archive=args.templates,
        prmtop=args.prmtop,
        inpcrd=args.inpcrd,
        amber_env=args.amber_env,
        equilibrate_script=args.equilibrate_script,
        production_script=args.production_script,
        out_dir=args.out,
    )
    print(f"Prepared {n} replica slot(s) under {args.out}")


def demo() -> None:
    """Self-check: renders one slot into a temp dir and asserts its shape."""
    import tempfile

    repo_root = Path(__file__).resolve().parent.parent
    templates_archive = repo_root / "templates.tar.gz"

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        prmtop = tmp / "system.prmtop"
        inpcrd = tmp / "system.inpcrd"
        amber_env = tmp / "amber.sh"
        equilibrate_script = tmp / "equilibrate.sh"
        production_script = tmp / "production.sh"
        for f in (prmtop, inpcrd, amber_env, equilibrate_script, production_script):
            f.write_text("stub\n")

        params = {
            "last_residue": 999,
            "temperature": 310,
            "length_ns": 45,
            "replicas": 3,
        }
        out_dir = tmp / "replicas"

        n = prepare_replicas(
            params=params,
            templates_archive=templates_archive,
            prmtop=prmtop,
            inpcrd=inpcrd,
            amber_env=amber_env,
            equilibrate_script=equilibrate_script,
            production_script=production_script,
            out_dir=out_dir,
        )
        assert n == 3

        slots = sorted(p.name for p in out_dir.iterdir())
        assert slots == ["0", "1", "2"], slots

        slot = out_dir / "0"
        for name in PREPROD_STEPS:
            assert (slot / "preprod" / f"{name}.in").exists()
        for name in PROD_STEPS:
            assert (slot / "prod" / f"{name}.in").exists()
        for name in ("amber.sh", "equilibrate.sh", "production.sh",
                      "system.prmtop", "system.inpcrd", "steps.txt"):
            assert (slot / name).exists()

        assert (slot / "steps.txt").read_text().strip() == "5"  # ceil(45/10)

        heat = (slot / "preprod" / "2_heat.in").read_text()
        assert "temp0 = 310" in heat
        assert "restraintmask=':1-999'" in heat

        min1 = (slot / "preprod" / "1_min.in").read_text()
        assert "restraintmask = ':1-999'" in min1

    print("prepare_replicas.py: self-check OK")


if __name__ == "__main__":
    import sys

    if "--self-test" in sys.argv:
        demo()
    else:
        main()
