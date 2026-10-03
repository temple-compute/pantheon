#!/usr/bin/env python3
"""
Final task for the cMD replica pipeline: walks `produced_out/<i>/` (one
subfolder per replica, each holding that replica's production chunk files
-- see workflow.yaml's `produce`/`collect` tasks) and writes a
one-row-per-replica CSV summary.
"""

import argparse
import csv
from pathlib import Path


def summarize_replica(replica_dir: Path) -> dict:
    rst_files = sorted(replica_dir.glob("prod_*.rst"))
    nc_files = sorted(replica_dir.glob("prod_*.nc"))
    chunks = len(rst_files)
    last_rst = rst_files[-1].name if rst_files else ""
    traj_bytes = sum(f.stat().st_size for f in nc_files)
    return {
        "replica": replica_dir.name,
        "chunks_completed": chunks,
        "last_restart_file": last_rst,
        "trajectory_files": len(nc_files),
        "trajectory_bytes": traj_bytes,
    }


def collect(results_dir: Path) -> list[dict]:
    rows = [
        summarize_replica(d)
        for d in sorted(results_dir.iterdir())
        if d.is_dir()
    ]
    rows.sort(key=lambda r: r["replica"])
    return rows


def write_csv(rows: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "replica", "chunks_completed", "last_restart_file",
        "trajectory_files", "trajectory_bytes",
    ]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    rows = collect(args.results)
    write_csv(rows, args.out)
    print(f"Wrote {len(rows)} replica row(s) to {args.out}")


def demo() -> None:
    """Self-check: builds a fake gathered/ tree and asserts the CSV output."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        results_dir = tmp / "gathered"
        for i, chunks in enumerate([2, 3]):
            replica_dir = results_dir / str(i)
            replica_dir.mkdir(parents=True)
            for c in range(1, chunks + 1):
                (replica_dir / f"prod_{c}.rst").write_text("r")
                (replica_dir / f"prod_{c}.nc").write_bytes(b"x" * 10)

        rows = collect(results_dir)
        assert len(rows) == 2
        assert rows[0]["chunks_completed"] == 2
        assert rows[0]["last_restart_file"] == "prod_2.rst"
        assert rows[1]["chunks_completed"] == 3
        assert rows[1]["trajectory_bytes"] == 30

        out_csv = tmp / "summary.csv"
        write_csv(rows, out_csv)
        assert out_csv.exists()
        assert len(out_csv.read_text().splitlines()) == 3  # header + 2 rows

    print("collect.py: self-check OK")


if __name__ == "__main__":
    import sys

    if "--self-test" in sys.argv:
        demo()
    else:
        main()
