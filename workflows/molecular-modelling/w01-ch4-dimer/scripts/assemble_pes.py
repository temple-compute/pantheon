#!/usr/bin/env python3
"""
Assemble every clone's result.json (written by compute_energy.py, one per
horus_map slot) into a single PES summary CSV.

Self-contained (stdlib only) so the ``python_script`` runtime can ship it to
the target as a single file.

Usage:
    assemble_pes.py --results results_in/ --out pes/
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

_NAME_RE = re.compile(r"dimer_(\d+)_(\d+)")

_FIELDNAMES = ["slot", "geometry", "methane_deg", "helium_deg", "energy"]


def assemble(results: Path) -> list[dict]:
    """Read every slot's result.json under *results* into summary rows."""
    rows = []
    for slot_dir in sorted(results.iterdir(), key=lambda p: p.name):
        result_path = slot_dir / "result.json"
        if not result_path.is_file():
            continue
        data = json.loads(result_path.read_text())
        geometry = Path(data["file"]).parent.name
        match = _NAME_RE.match(geometry)
        methane_deg, helium_deg = (
            (int(match.group(1)), int(match.group(2))) if match else ("", "")
        )
        rows.append(
            {
                "slot": slot_dir.name,
                "geometry": geometry,
                "methane_deg": methane_deg,
                "helium_deg": helium_deg,
                "energy": data["energy"],
            }
        )
    return rows


def write_csv(rows: list[dict], out_csv: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Assemble a PES summary CSV from per-geometry result.json files."
    )
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    rows = assemble(args.results)
    out_csv = args.out / "pes.csv"
    write_csv(rows, out_csv)

    print(f"assemble_pes.py: wrote {len(rows)} row(s) -> {out_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
