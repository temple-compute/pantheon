#!/usr/bin/env python3
"""
Stage 3 (summary) — turn Vina output PDBQTs into ranked energy tables.

Untars the docking archive, parses the ``REMARK VINA RESULT`` line of every
``MODEL`` in each ``*_out.pdbqt`` (its first field is the binding affinity in
kcal/mol, followed by RMSD lower/upper bounds), and writes two CSVs:

* ``summary.csv`` — one row per ligand, ranked best (most negative) first:
  ``rank, ligand, best_affinity_kcal_mol, mean_affinity_kcal_mol, num_poses``.
* ``poses.csv``   — one row per pose:
  ``ligand, pose, affinity_kcal_mol, rmsd_lb, rmsd_ub``.

Lower (more negative) affinity is better. stdlib only.

Usage:
    summary.py --docking docking_out.tar.gz --summary summary.csv --poses poses.csv
    summary.py --selftest
"""

from __future__ import annotations  # runs on the target's python3 (>=3.9)

import argparse
import csv
import tarfile
import tempfile
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


def collect(pred_dir: Path) -> list[dict]:
    """Parse every ``*_out.pdbqt`` under *pred_dir* into per-ligand records."""
    ligands: list[dict] = []
    for pdbqt in sorted(pred_dir.rglob("*_out.pdbqt")):
        name = pdbqt.stem[: -len("_out")]
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
    """Extract, parse, and write both CSVs. Returns ligand count."""
    with tempfile.TemporaryDirectory() as tmp:
        extracted = Path(tmp)
        with tarfile.open(args.docking) as tar:
            tar.extractall(extracted, filter="data")  # safe extraction
        ligands = collect(extracted)

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
    """Parse a synthetic docking archive and assert ranking + CSV output."""
    fixtures = {
        "strong": [(-9.5, 0.0, 0.0), (-9.1, 1.2, 2.3)],
        "weak": [(-5.0, 0.0, 0.0)],
        "mid": [(-7.2, 0.0, 0.0), (-7.0, 0.9, 1.1)],
    }
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        out_dir = d / "docking_out"
        out_dir.mkdir()
        for name, poses in fixtures.items():
            body = ["MODEL 1"]
            for aff, lb, ub in poses:
                body.append(f"REMARK VINA RESULT:    {aff:.1f}    {lb:.3f}    {ub:.3f}")
            body.append("ENDMDL")
            (out_dir / f"{name}_out.pdbqt").write_text("\n".join(body) + "\n")

        archive = d / "docking_out.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(out_dir, arcname="docking_out")

        summary = d / "summary.csv"
        poses_csv = d / "poses.csv"
        n = run(argparse.Namespace(docking=archive, summary=summary, poses=poses_csv))
        assert n == 3, n

        rows = list(csv.DictReader(summary.open()))
        assert [r["ligand"] for r in rows] == ["strong", "mid", "weak"], rows
        assert rows[0]["rank"] == "1"
        assert rows[0]["best_affinity_kcal_mol"] == "-9.50", rows[0]
        assert rows[0]["mean_affinity_kcal_mol"] == "-9.30", rows[0]
        assert rows[0]["num_poses"] == "2", rows[0]

        pose_rows = list(csv.DictReader(poses_csv.open()))
        # 2 + 2 + 1 poses across the three ligands.
        assert len(pose_rows) == 5, pose_rows
        strong = [r for r in pose_rows if r["ligand"] == "strong"]
        assert strong[0]["affinity_kcal_mol"] == "-9.50", strong
        assert strong[1]["rmsd_ub"] == "2.300", strong
    print("summary.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarise Vina docking results.")
    parser.add_argument("--docking", type=Path)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--poses", type=Path)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        _selftest()
        return 0
    if not (args.docking and args.summary and args.poses):
        parser.error("--docking, --summary and --poses are required")

    run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
