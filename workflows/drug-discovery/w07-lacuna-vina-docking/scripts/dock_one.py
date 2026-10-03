#!/usr/bin/env python3
# Body of the `dock` horus_map task: docks one ligand with AutoDock Vina.
# Runs once per ligand, concurrently. Never raises -- a failed ligand is
# recorded in status.json instead, so one bad ligand doesn't sink the batch.

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receptor", type=Path, required=True)
    parser.add_argument("--box", type=Path, required=True)
    parser.add_argument("--ligand", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--exhaustiveness", type=int, default=8)
    parser.add_argument("--n-poses", type=int, default=9)
    parser.add_argument("--cpu", type=int, default=1)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    box = json.loads(args.box.read_text())
    name = args.ligand.stem
    entry = {"ligand": name, "status": "failed"}

    try:
        from vina import Vina

        v = Vina(sf_name="vina", cpu=args.cpu, verbosity=0)
        v.set_receptor(str(args.receptor))
        v.set_ligand_from_file(str(args.ligand))
        v.compute_vina_maps(center=box["center"], box_size=box["size"])
        v.dock(exhaustiveness=args.exhaustiveness, n_poses=args.n_poses)
        v.write_poses(str(args.out / f"{name}_out.pdbqt"), n_poses=args.n_poses, overwrite=True)
        entry["status"] = "ok"
        entry["best_affinity"] = float(v.energies(n_poses=1)[0][0])  # best pose, kcal/mol
    except Exception as exc:
        print(f"dock_one.py: docking failed for {name}: {exc}")
        entry["error"] = str(exc)

    (args.out / "status.json").write_text(json.dumps(entry))


if __name__ == "__main__":
    main()
