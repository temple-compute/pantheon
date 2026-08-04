#!/usr/bin/env python3
"""
Stage 1 (prepare_models) -- turn a folder of structures into map items.

The ``analyze`` task's ``map:`` block fans out over the children of this task's
output folder, and the engine hands each clone a copy of the i-th child
*directory* (``MapExpander._materialize_item`` calls ``shutil.copytree``). A
directory of loose ``.pdb`` files therefore cannot be mapped over directly: each
model has to be wrapped in its own folder first.

    models/model_000/model.pdb
                     name.txt     # the original stem, for the summary
    models/model_001/...

Model order is the sorted order of the input filenames, which is also the order
the engine fans out in (children sorted by name), so slot ``<i>`` in the
gathered output always corresponds to ``model_<i>``.

Usage:
    prepare_models.py --structures structures/ --out models/
    prepare_models.py --selftest
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def find_structures(structures: Path) -> list[Path]:
    """Every PDB under *structures*, sorted by name. A single file is allowed."""
    if structures.is_file():
        return [structures]
    return sorted(p for p in structures.glob("*.pdb") if p.is_file())


def write_models(pdbs: list[Path], out: Path) -> int:
    """
    Wrap each PDB in its own ``model_NNN/`` directory. Returns the count.

    Zero-padded because the engine fans out over children sorted by name:
    unpadded ``model_10`` would sort before ``model_2`` and silently scramble
    which structure lands in which gathered slot.
    """
    out.mkdir(parents=True, exist_ok=True)
    width = max(3, len(str(max(len(pdbs) - 1, 0))))
    for index, pdb in enumerate(pdbs):
        child = out / f"model_{index:0{width}d}"
        child.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pdb, child / "model.pdb")
        (child / "name.txt").write_text(pdb.stem + "\n")
    return len(pdbs)


def run(args: argparse.Namespace) -> int:
    """Wrap every input structure into a mappable folder. Returns the count."""
    pdbs = find_structures(args.structures)
    if not pdbs:
        raise SystemExit(f"no .pdb files found in {args.structures}")
    count = write_models(pdbs, args.out)
    print(f"prepare_models.py: {count} model(s) -> {args.out}")
    return count


def _selftest() -> None:
    """Wrap synthetic structures and assert the layout the map: block needs."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        structures = tmpdir / "structures"
        structures.mkdir()
        # Deliberately out of lexical order on creation, and >9 to exercise padding.
        for name in ["cluster2", "cluster0", "cluster10", "cluster1"]:
            (structures / f"{name}.pdb").write_text(f"ATOM {name}\n")
        (structures / "notes.txt").write_text("ignored\n")

        found = find_structures(structures)
        assert [p.stem for p in found] == [
            "cluster0",
            "cluster1",
            "cluster10",
            "cluster2",
        ], found

        out = tmpdir / "models"
        assert write_models(found, out) == 4

        children = sorted(p.name for p in out.iterdir())
        assert children == ["model_000", "model_001", "model_002", "model_003"], children
        # Every child must be a directory: the engine copytree's each one.
        assert all((out / name).is_dir() for name in children)
        # Padding keeps sorted-by-name order equal to model order.
        assert children == sorted(children)
        assert (out / "model_000" / "model.pdb").read_text() == "ATOM cluster0\n"
        assert (out / "model_000" / "name.txt").read_text() == "cluster0\n"
        assert (out / "model_003" / "name.txt").read_text() == "cluster2\n"

        # A single file input is accepted as a one-model run.
        assert [p.stem for p in find_structures(structures / "cluster0.pdb")] == [
            "cluster0"
        ]

    print("prepare_models.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wrap structures into mappable folders.")
    parser.add_argument("--structures", type=Path, help="folder of PDBs, or one PDB")
    parser.add_argument("--out", type=Path, help="output folder of model directories")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        _selftest()
        return 0
    if not (args.structures and args.out):
        parser.error("--structures and --out are required")

    run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
