#!/usr/bin/env python3
# Applies Sage 2.3.0 (ligand, water, ions) + ff14SB (protein) to the topology,
# exports an OpenMM system.xml and complex.pdb, and writes one slot per replica
# (replicas/<i>/{system.xml,complex.pdb,seed}) for the simulate map.

import argparse
import os
import shutil
import sys
from pathlib import Path

# Shared host: cap BLAS/torch threads unless the caller set them.
os.environ.setdefault("OMP_NUM_THREADS", "2")

FORCE_FIELDS = ("openff-2.3.0.offxml", "ff14sb_off_impropers_0.0.4.offxml")
REPLICAS = {"smoke": 2, "full": 3}
BASE_SEED = 2026


def write_slots(out: Path, system_xml: Path, complex_pdb: Path, n: int) -> None:
    # drop slots left by an earlier run with more replicas
    shutil.rmtree(out, ignore_errors=True)
    for i in range(n):
        slot = out / str(i)
        slot.mkdir(parents=True, exist_ok=True)
        shutil.copy(system_xml, slot / "system.xml")
        shutil.copy(complex_pdb, slot / "complex.pdb")
        (slot / "seed").write_text(f"{BASE_SEED + i}\n")


def parameterize(topology: Path, out: Path, n: int) -> None:
    import openmm
    from openff.toolkit import ForceField, Topology

    top = Topology.from_json(topology.read_text())
    interchange = ForceField(*FORCE_FIELDS).create_interchange(top)
    work = out.parent / "parameterized"
    work.mkdir(parents=True, exist_ok=True)
    system_xml, complex_pdb = work / "system.xml", work / "complex.pdb"
    system_xml.write_text(openmm.XmlSerializer.serialize(interchange.to_openmm_system()))
    interchange.to_pdb(str(complex_pdb))
    write_slots(out, system_xml, complex_pdb, n)
    print(f"parameterized {top.n_atoms} atoms; wrote {n} replica slots", flush=True)


def selftest() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "s.xml").write_text("<System/>")
        (d / "c.pdb").write_text("END\n")
        (d / "replicas/2").mkdir(parents=True)  # stale slot from a full run
        write_slots(d / "replicas", d / "s.xml", d / "c.pdb", REPLICAS["smoke"])
        slots = sorted(p.name for p in (d / "replicas").iterdir())
        assert slots == ["0", "1"], slots
        assert (d / "replicas/1/seed").read_text().strip() == str(BASE_SEED + 1)
        assert (d / "replicas/0/system.xml").read_text() == "<System/>"
    assert REPLICAS["full"] == 3
    print("selftest ok")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topology", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--profile", choices=sorted(REPLICAS))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not (a.topology and a.out and a.profile):
        sys.exit("--topology, --out and --profile are required")
    parameterize(a.topology, a.out, REPLICAS[a.profile])


if __name__ == "__main__":
    main()
