#!/usr/bin/env python3
"""Self-check for generate_dimers.py: run build() into a tmp dir and assert
one sub-directory per (methane, helium) pair, each with a valid molecule.xyz.

Usage: python3 scripts/test_generate_dimers.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from generate_dimers import build  # noqa: E402


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="test_generate_dimers_"))
    try:
        out = tmp / "dimers"
        count = build(
            out,
            methane_step=60,
            helium_step=90,
            max_methane=120,
            max_helium=180,
        )
        # methane: 0, 60 -> 2 values; helium: 0, 90, 180 -> 3 values
        assert count == 6, f"expected 6 geometries, got {count}"

        subdirs = sorted(p.name for p in out.iterdir())
        assert len(subdirs) == 6, f"expected 6 sub-directories, got {subdirs}"
        assert subdirs[0] == "dimer_000_000", subdirs

        for name in subdirs:
            xyz = out / name / "molecule.xyz"
            assert xyz.is_file(), f"missing {xyz}"
            lines = xyz.read_text().splitlines()
            assert lines[0].strip() == "6", (name, lines[0])  # 5 CH4 + 1 He
            assert len(lines) == 8, (name, len(lines))  # count + comment + 6 atoms

        print(f"test_generate_dimers.py: OK ({count} geometries)")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
