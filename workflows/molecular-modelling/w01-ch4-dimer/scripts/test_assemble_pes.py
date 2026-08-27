#!/usr/bin/env python3
"""Self-check for assemble_pes.py: build a couple of fake result.json slots
and assert the assembled CSV rows.

Usage: python3 scripts/test_assemble_pes.py
"""

from __future__ import annotations

import csv
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from assemble_pes import assemble, write_csv  # noqa: E402


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="test_assemble_pes_"))
    try:
        results = tmp / "results"
        slots = {
            "0": ("dimer_000_000", 0.0),
            "1": ("dimer_000_090", -1.5),
        }
        for slot, (geometry, energy) in slots.items():
            slot_dir = results / slot
            slot_dir.mkdir(parents=True)
            (slot_dir / "result.json").write_text(
                json.dumps(
                    {
                        "file": f"/some/target/path/{geometry}/molecule.xyz",
                        "energy": energy,
                        "gradient": [0.0, 0.0, 0.0],
                    }
                )
            )

        rows = assemble(results)
        assert len(rows) == 2, rows
        by_slot = {r["slot"]: r for r in rows}
        assert by_slot["0"]["geometry"] == "dimer_000_000"
        assert by_slot["0"]["methane_deg"] == 0
        assert by_slot["0"]["helium_deg"] == 0
        assert by_slot["1"]["geometry"] == "dimer_000_090"
        assert by_slot["1"]["helium_deg"] == 90
        assert by_slot["1"]["energy"] == -1.5

        out_csv = tmp / "pes" / "pes.csv"
        write_csv(rows, out_csv)
        assert out_csv.is_file()
        with out_csv.open() as f:
            csv_rows = list(csv.DictReader(f))
        assert len(csv_rows) == 2
        assert csv_rows[0]["geometry"] == "dimer_000_000"

        print("test_assemble_pes.py: OK")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
