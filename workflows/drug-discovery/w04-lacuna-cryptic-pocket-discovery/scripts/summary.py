#!/usr/bin/env python3
"""
Stage 5 (summary) — fan-in. Turn the dock map's per-ligand output into ranked
energy tables.

``dock`` is a ``kind: horus_map`` task with one folder output: after every
clone runs, that folder holds one numbered slot per ligand
(``docked/0/``, ``docked/1/``, ...), each containing the ``dock_one.py``
clone's ``status.json`` (a single ligand's outcome) and, if it succeeded,
``{ligand}_out.pdbqt``. Parses the ``REMARK VINA RESULT`` line of every
``MODEL`` in that PDBQT and writes two CSVs:

* ``scores.csv`` — one row per ligand, ranked best (most negative) first:
  ``rank, ligand, best_affinity_kcal_mol, mean_affinity_kcal_mol, num_poses``.
* ``poses.csv``  — one row per pose:
  ``ligand, pose, affinity_kcal_mol, rmsd_lb, rmsd_ub``.

A ligand a clone recorded as ``failed`` (docking error) is skipped, not
treated as a zero-affinity result. Lower (more negative) affinity is better.
stdlib only.

Usage:
    summary.py --results docked/ --summary scores.csv --poses poses.csv
    summary.py --selftest
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


def parse_poses(pdbqt_text: str) -> list[tuple[float, float, float]]:
    """Return ``[(affinity, rmsd_lb, rmsd_ub), ...]`` from an output PDBQT."""
    poses: list[tuple[float, float, float]] = []
    for line in pdbqt_text.splitlines():
        if line.startswith("REMARK VINA RESULT:"):
            parts = line.split(":", 1)[1].split()
            affinity = float(parts[0])
            rmsd_lb = float(parts[1]) if len(parts) > 1 else 0.0
            rmsd_ub = float(parts[2]) if len(parts) > 2 else 0.0
            poses.append((affinity, rmsd_lb, rmsd_ub))
    return poses


def collect(results: Path) -> list[dict]:
    """
    Walk the map's slots (``docked/<i>/``). Returns per-ligand records.

    Each slot holds exactly one ligand's ``status.json``; only a slot whose
    ligand docked successfully is expected to also have a
    ``{ligand}_out.pdbqt`` to parse.
    """
    ligands: list[dict] = []
    for slot in sorted(results.iterdir(), key=lambda p: p.name):
        if not slot.is_dir():
            continue
        status_path = slot / "status.json"
        if not status_path.exists():
            print(f"summary.py: WARNING no status.json in {slot}, skipping")
            continue
        entry = json.loads(status_path.read_text())
        if entry.get("status") != "ok":
            continue
        name = entry["ligand"]
        pdbqt = slot / f"{name}_out.pdbqt"
        if not pdbqt.exists():
            print(f"summary.py: WARNING {name} marked ok but {pdbqt} is missing")
            continue
        poses = parse_poses(pdbqt.read_text())
        if not poses:
            print(f"summary.py: WARNING no poses parsed for {name}")
            continue
        affinities = [p[0] for p in poses]
        ligands.append(
            {
                "ligand": name,
                "best_affinity": min(affinities),
                "mean_affinity": sum(affinities) / len(affinities),
                "num_poses": len(poses),
                "poses": poses,
            }
        )
    return ligands


def write_tables(ligands: list[dict], summary: Path, poses: Path) -> None:
    """Write the ranked summary and per-pose CSVs."""
    ligands = sorted(ligands, key=lambda r: r["best_affinity"])  # best first

    summary.parent.mkdir(parents=True, exist_ok=True)
    with summary.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["rank", "ligand", "best_affinity_kcal_mol",
             "mean_affinity_kcal_mol", "num_poses"]
        )
        for rank, rec in enumerate(ligands, start=1):
            writer.writerow(
                [rank, rec["ligand"], f"{rec['best_affinity']:.2f}",
                 f"{rec['mean_affinity']:.2f}", rec["num_poses"]]
            )

    poses.parent.mkdir(parents=True, exist_ok=True)
    with poses.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["ligand", "pose", "affinity_kcal_mol", "rmsd_lb", "rmsd_ub"]
        )
        for rec in ligands:
            for i, (aff, lb, ub) in enumerate(rec["poses"], start=1):
                writer.writerow(
                    [rec["ligand"], i, f"{aff:.2f}", f"{lb:.3f}", f"{ub:.3f}"]
                )


def run(args: argparse.Namespace) -> int:
    """Collect, rank, and write both CSVs. Returns ligand count."""
    ligands = collect(args.results)
    write_tables(ligands, args.summary, args.poses)
    if ligands:
        best = min(ligands, key=lambda r: r["best_affinity"])
        print(
            f"summary.py: {len(ligands)} ligand(s); top hit {best['ligand']} "
            f"@ {best['best_affinity']:.2f} kcal/mol → {args.summary}"
        )
    else:
        print(f"summary.py: no ligands parsed; wrote empty tables to {args.summary}")
    return len(ligands)


def _selftest() -> None:
    """Rank a synthetic dock-map output, including a failed-ligand slot."""
    import tempfile

    fixtures = {
        "strong": [(-9.5, 0.0, 0.0), (-9.1, 1.2, 2.3)],
        "weak": [(-5.0, 0.0, 0.0)],
        "mid": [(-7.2, 0.0, 0.0), (-7.0, 0.9, 1.1)],
    }
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        results = d / "docked"

        for i, (name, poses) in enumerate(fixtures.items()):
            slot = results / str(i)
            slot.mkdir(parents=True)
            body = ["MODEL 1"]
            for aff, lb, ub in poses:
                body.append(f"REMARK VINA RESULT:    {aff:.1f}    {lb:.3f}    {ub:.3f}")
            body.append("ENDMDL")
            (slot / f"{name}_out.pdbqt").write_text("\n".join(body) + "\n")
            (slot / "status.json").write_text(
                json.dumps({"ligand": name, "status": "ok"})
            )

        # A failed clone: recorded in status.json, no PDBQT to match — must
        # not be silently treated as a zero-affinity ligand.
        failed_slot = results / "3"
        failed_slot.mkdir(parents=True)
        (failed_slot / "status.json").write_text(
            json.dumps({"ligand": "broken", "status": "failed", "error": "boom"})
        )

        summary = d / "scores.csv"
        poses_csv = d / "poses.csv"
        n = run(argparse.Namespace(results=results, summary=summary, poses=poses_csv))
        assert n == 3, n

        rows = list(csv.DictReader(summary.open()))
        assert [r["ligand"] for r in rows] == ["strong", "mid", "weak"], rows
        assert rows[0]["rank"] == "1"
        assert rows[0]["best_affinity_kcal_mol"] == "-9.50", rows[0]
        assert rows[0]["mean_affinity_kcal_mol"] == "-9.30", rows[0]
        assert rows[0]["num_poses"] == "2", rows[0]
        assert "broken" not in {r["ligand"] for r in rows}, rows

        pose_rows = list(csv.DictReader(poses_csv.open()))
        assert len(pose_rows) == 5, pose_rows  # 2 + 2 + 1 across three ligands
        strong = [r for r in pose_rows if r["ligand"] == "strong"]
        assert strong[0]["affinity_kcal_mol"] == "-9.50", strong
        assert strong[1]["rmsd_ub"] == "2.300", strong
    print("summary.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rank gathered AutoDock Vina docking results.")
    parser.add_argument("--results", type=Path, help="the dock map task's output folder (docked/)")
    parser.add_argument("--summary", type=Path, help="output ranking CSV")
    parser.add_argument("--poses", type=Path, help="output per-pose CSV")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        _selftest()
        return 0
    if not (args.results and args.summary and args.poses):
        parser.error("--results, --summary and --poses are required")

    run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
