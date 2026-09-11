#!/usr/bin/env python3
"""
Stage 4 (dock) — dock one ligand. Runs once per horus_map clone.

Body of the ``dock`` task, a ``kind: horus_map`` task: for each child of the
``ligands_pdbqt`` folder (one PDBQT per ligand), the engine runs this script
once, handing it that one ligand plus a copy of every normal input the map
task declared — here, the shared ``receptor_box/`` folder (``receptor.pdbqt``
+ ``box.json``). Each clone writes into its own numbered slot under the map's
single folder output, so nothing here needs to know its own slot index.

Docks with the AutoDock Vina Python bindings (``from vina import Vina``).

**This script must never exit non-zero.** A clone that fails aborts the run
or blocks downstream tasks depending on the workflow's failure policy, so a
single unparseable or unsupported ligand must not sink docking for every
other ligand's clone. A failure is recorded in ``status.json`` and the clone
still succeeds.

Usage:
    dock_one.py --receptor receptor_box/receptor.pdbqt --box receptor_box/box.json \
        --ligand ligands_pdbqt/aspirin.pdbqt --out docked/ --exhaustiveness 8 --n-poses 9 --cpu 1
    dock_one.py --selftest
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def dock_ligand(
    receptor: Path,
    ligand: Path,
    box: dict,
    out_dir: Path,
    exhaustiveness: int,
    n_poses: int,
    cpu: int,
) -> dict:
    """Dock *ligand* with Vina; return its status entry."""
    name = ligand.stem
    entry = {"ligand": name, "status": "failed", "error": None}
    try:
        from vina import Vina

        v = Vina(sf_name="vina", cpu=cpu, verbosity=0)
        v.set_receptor(str(receptor))
        v.set_ligand_from_file(str(ligand))
        v.compute_vina_maps(center=box["center"], box_size=box["size"])
        v.dock(exhaustiveness=exhaustiveness, n_poses=n_poses)
        out_pdbqt = out_dir / f"{name}_out.pdbqt"
        v.write_poses(str(out_pdbqt), n_poses=n_poses, overwrite=True)
        # energies()[0][0] is the best pose's total affinity (kcal/mol).
        best = float(v.energies(n_poses=1)[0][0])
        print(f"dock_one.py: {name} best affinity {best:.2f} kcal/mol")
        entry["status"] = "ok"
        entry["best_affinity"] = best
    except Exception as exc:  # noqa: BLE001 — a failed ligand must not fail the clone
        print(f"dock_one.py: WARNING docking failed for {name}: {exc}")
        entry["error"] = str(exc)
    return entry


def run(args: argparse.Namespace) -> dict:
    """Dock the one ligand and write ``status.json`` into ``--out``."""
    box = json.loads(args.box.read_text())
    # Created unconditionally: the output folder is this clone's declared
    # artifact, so it must exist even if docking fails.
    args.out.mkdir(parents=True, exist_ok=True)
    entry = dock_ligand(
        args.receptor, args.ligand, box, args.out,
        args.exhaustiveness, args.n_poses, args.cpu,
    )
    (args.out / "status.json").write_text(json.dumps(entry, indent=2))
    return entry


def _selftest() -> None:
    """Exercise the docking call with Vina stubbed out."""
    import tempfile
    import types

    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)

        receptor = d / "receptor.pdbqt"
        receptor.write_text("REMARK receptor\n")
        box = d / "box.json"
        box.write_text(json.dumps({"center": [1.0, 2.0, 3.0], "size": [20.0, 20.0, 20.0]}))
        good = d / "good.pdbqt"
        good.write_text("REMARK good\n")
        bad = d / "bad.pdbqt"
        bad.write_text("REMARK bad\n")

        class _FakeVina:
            def __init__(self, **_kw):
                self._name = None

            def set_receptor(self, path):
                pass

            def set_ligand_from_file(self, path):
                self._name = Path(path).stem
                if "bad" in self._name:
                    raise RuntimeError("boom")

            def compute_vina_maps(self, **_kw):
                pass

            def dock(self, **_kw):
                pass

            def write_poses(self, path, **_kw):
                Path(path).write_text("REMARK VINA RESULT:    -8.5    0.0    0.0\n")

            def energies(self, **_kw):
                return [[-8.5]]

        fake_module = types.ModuleType("vina")
        fake_module.Vina = _FakeVina
        sys.modules["vina"] = fake_module
        try:
            out_good = d / "docked_good"
            entry = run(argparse.Namespace(
                receptor=receptor, box=box, ligand=good, out=out_good,
                exhaustiveness=4, n_poses=1, cpu=1,
            ))
            assert entry["status"] == "ok", entry
            assert entry["best_affinity"] == -8.5, entry
            assert (out_good / "good_out.pdbqt").exists()
            status = json.loads((out_good / "status.json").read_text())
            assert status["status"] == "ok", status

            out_bad = d / "docked_bad"
            entry = run(argparse.Namespace(
                receptor=receptor, box=box, ligand=bad, out=out_bad,
                exhaustiveness=4, n_poses=1, cpu=1,
            ))
            assert entry["status"] == "failed", entry
            assert not (out_bad / "bad_out.pdbqt").exists()
            # The clone's output folder still exists even on failure.
            assert out_bad.exists()
        finally:
            del sys.modules["vina"]

    print("dock_one.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dock one ligand with AutoDock Vina.")
    parser.add_argument("--receptor", type=Path, help="receptor PDBQT")
    parser.add_argument("--box", type=Path, help="box.json ({center, size})")
    parser.add_argument("--ligand", type=Path, help="one ligand PDBQT")
    parser.add_argument("--out", type=Path, help="output folder for this clone")
    parser.add_argument("--exhaustiveness", type=int, default=8)
    parser.add_argument("--n-poses", type=int, default=9)
    parser.add_argument("--cpu", type=int, default=1)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        _selftest()
        return 0
    if not (args.receptor and args.box and args.ligand and args.out):
        parser.error("--receptor, --box, --ligand and --out are required")

    run(args)
    # Always 0: a failed ligand is data, not a task failure — see the module
    # docstring.
    return 0


if __name__ == "__main__":
    sys.exit(main())
