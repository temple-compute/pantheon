#!/usr/bin/env python3
# Reads the `dock` map's output (docked/<i>/status.json + {ligand}_out.pdbqt)
# and writes ranked scores.csv + per-pose poses.csv. Lower affinity = better.

import argparse
import csv
import json
from pathlib import Path


def parse_poses(pdbqt_text: str) -> list[tuple]:
    poses = []
    for line in pdbqt_text.splitlines():
        if line.startswith("REMARK VINA RESULT:"):
            aff, lb, ub = (line.split(":", 1)[1].split() + [0.0, 0.0])[:3]
            poses.append((float(aff), float(lb), float(ub)))
    return poses


def collect(results: Path) -> list[dict]:
    ligands = []
    for slot in sorted(results.iterdir()):
        entry = json.loads((slot / "status.json").read_text())
        if entry["status"] != "ok":
            continue
        name = entry["ligand"]
        poses = parse_poses((slot / f"{name}_out.pdbqt").read_text())
        affinities = [p[0] for p in poses]
        ligands.append({
            "ligand": name,
            "best_affinity": min(affinities),
            "mean_affinity": sum(affinities) / len(affinities),
            "poses": poses,
        })
    return sorted(ligands, key=lambda r: r["best_affinity"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)  # dock map's output folder
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--poses", type=Path, required=True)
    args = parser.parse_args()

    ligands = collect(args.results)

    with args.summary.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["rank", "ligand", "best_affinity_kcal_mol", "mean_affinity_kcal_mol", "num_poses"])
        for rank, rec in enumerate(ligands, start=1):
            writer.writerow([rank, rec["ligand"], f"{rec['best_affinity']:.2f}",
                              f"{rec['mean_affinity']:.2f}", len(rec["poses"])])

    with args.poses.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ligand", "pose", "affinity_kcal_mol", "rmsd_lb", "rmsd_ub"])
        for rec in ligands:
            for i, (aff, lb, ub) in enumerate(rec["poses"], start=1):
                writer.writerow([rec["ligand"], i, f"{aff:.2f}", f"{lb:.3f}", f"{ub:.3f}"])


if __name__ == "__main__":
    main()
