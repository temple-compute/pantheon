#!/usr/bin/env python3
"""
Stage 5 (split_ligands) -- chunk the ligand library into per-batch folders.

Writes one *sub-directory* per batch into the output folder, because that is
what the ``dock`` task's ``map:`` block fans out over: the engine hands each
clone a copy of the i-th child **directory** (``MapExpander._materialize_item``
does ``shutil.copytree``), so a batch has to be a directory, not a file.

Each batch folder also carries its own copy of the prepared receptor and the
docking box:

    ligand_batches/batch_000/ligands.sdf
                             names.json
                             prep_receptor.pdbqt
                             box.pdb

That duplication is deliberate. A map clone cannot receive a normal edge -- the
only inputs it gets are its slice and its index -- so anything a clone needs
beyond its own ligands has to travel *inside* the slice. Copying two small files
per batch keeps each clone self-contained and target-agnostic; the alternative
(pointing the clone at the prep tasks' run-directory paths) only works when
every clone shares one filesystem.

Ligand naming follows vs_autodock.py:715-719 -- ``{alnum(title)}_{index}``,
falling back to ``ligand_{index}`` -- so the identifiers in scores.csv match
what the original CLI produces. The index is part of the name because a library
routinely repeats a title across tautomers of one compound.

Usage:
    split_ligands.py --library ligands.sdf --receptor prep_receptor.pdbqt \
        --box box.pdb --out ligand_batches/ --batch-size 2
    split_ligands.py --selftest
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

SDF_TERMINATOR = "$$$$"


def sanitize_title(title: str) -> str:
    """Keep only alphanumerics, as vs_autodock does before using a title."""
    return "".join(char for char in title if char.isalnum())


def ligand_name(title: str, index: int) -> str:
    """Unique per-ligand name; titles repeat across tautomers, indices don't."""
    clean = sanitize_title(title)
    return f"{clean}_{index}" if clean else f"ligand_{index}"


def read_sdf(text: str) -> list[tuple[str, str]]:
    """
    Split an SDF into ``(title, record)`` pairs, records keeping their ``$$$$``.

    Parsed textually rather than with pybel: an SDF record is delimited by a
    line that is exactly ``$$$$`` and its title is the first line, so splitting
    it needs no chemistry toolkit. The ligands are only being routed here --
    the docking stage is where they actually get interpreted.
    """
    records: list[tuple[str, str]] = []
    current: list[str] = []

    def flush() -> None:
        if not any(line.strip() for line in current):
            return
        body = "\n".join(current).lstrip("\n")
        title = body.splitlines()[0].strip()
        records.append((title, f"{body}\n{SDF_TERMINATOR}\n"))

    for line in text.splitlines():
        if line.strip() == SDF_TERMINATOR:
            flush()
            current = []
            continue
        current.append(line)
    flush()

    return records


def read_smi(text: str) -> list[tuple[str, str]]:
    """
    Parse a SMILES library into ``(title, record)`` pairs.

    Port of ``read_ligand_lib`` (vs_autodock.py:172): one ligand per line,
    ``SMILES [name]``. Blank lines are skipped; a line with no name falls back
    to the index-based name downstream.
    """
    records: list[tuple[str, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        fields = stripped.split()
        smiles = fields[0]
        title = fields[1] if len(fields) > 1 else ""
        records.append((title, f"{smiles}\n"))
    return records


def read_library(path: Path) -> tuple[str, list[tuple[str, str]]]:
    """Dispatch on extension. Returns ``(format, records)``."""
    suffix = path.suffix.lower()
    text = path.read_text()
    if suffix == ".sdf":
        return "sdf", read_sdf(text)
    if suffix in (".smi", ".smiles"):
        return "smi", read_smi(text)
    raise SystemExit(f"unsupported ligand library format {suffix!r}: use .sdf or .smi")


def write_batches(
    fmt: str,
    records: list[tuple[str, str]],
    out: Path,
    batch_size: int,
    receptor: Path,
    box: Path,
) -> int:
    """
    Write ``batch_NNN/`` directories under *out*. Returns the batch count.

    Batch directories are zero-padded because the engine fans out over a
    folder's children *sorted by name*: unpadded ``batch_10`` would sort before
    ``batch_2`` and silently scramble the batch ordering in the gathered slots.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    out.mkdir(parents=True, exist_ok=True)

    named = [
        (ligand_name(title, index), record)
        for index, (title, record) in enumerate(records)
    ]
    batches = [named[i : i + batch_size] for i in range(0, len(named), batch_size)]
    width = max(3, len(str(max(len(batches) - 1, 0))))

    for batch_index, batch in enumerate(batches):
        child = out / f"batch_{batch_index:0{width}d}"
        child.mkdir(parents=True, exist_ok=True)
        (child / f"ligands.{fmt}").write_text("".join(record for _, record in batch))
        (child / "names.json").write_text(
            json.dumps({"format": fmt, "names": [name for name, _ in batch]}, indent=2) + "\n"
        )
        shutil.copyfile(receptor, child / "prep_receptor.pdbqt")
        shutil.copyfile(box, child / "box.pdb")

    return len(batches)


def run(args: argparse.Namespace) -> int:
    """Split the library into batch folders. Returns the batch count."""
    fmt, records = read_library(args.library)
    if not records:
        raise SystemExit(f"{args.library} contains no ligands")
    count = write_batches(fmt, records, args.out, args.batch_size, args.receptor, args.box)
    print(
        f"split_ligands.py: {len(records)} ligand(s) -> {count} batch(es) "
        f"of <= {args.batch_size} in {args.out}"
    )
    return count


def _selftest() -> None:
    """Batch a synthetic library and assert the layout the map: block needs."""
    import tempfile

    assert ligand_name("ZINC-000_1", 3) == "ZINC0001_3"
    assert ligand_name("", 4) == "ligand_4"
    assert ligand_name("   ", 5) == "ligand_5"

    sdf = "".join(f"MOL{i}\n  body {i}\n{SDF_TERMINATOR}\n" for i in range(5))
    records = read_sdf(sdf)
    assert len(records) == 5, records
    assert records[0][0] == "MOL0"
    assert records[4][1].endswith(f"{SDF_TERMINATOR}\n")
    # A trailing record with no terminator is still a ligand, not a dropped one.
    assert len(read_sdf(sdf + "MOL5\n  body 5\n")) == 6

    smi = read_smi("CCO ethanol\nCCC\n\n  \nCCN amine\n")
    assert smi == [("ethanol", "CCO\n"), ("", "CCC\n"), ("amine", "CCN\n")], smi

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        receptor = tmpdir / "prep_receptor.pdbqt"
        receptor.write_text("RECEPTOR\n")
        box = tmpdir / "box.pdb"
        box.write_text("BOX\n")
        out = tmpdir / "ligand_batches"

        assert write_batches("sdf", records, out, 2, receptor, box) == 3

        children = sorted(p.name for p in out.iterdir())
        assert children == ["batch_000", "batch_001", "batch_002"], children
        # Every child must be a directory: the engine copytree's each one.
        assert all((out / name).is_dir() for name in children)
        # Sorted-by-name order must equal batch order, which is why they pad.
        assert children == sorted(children)

        first = out / "batch_000"
        assert (first / "ligands.sdf").read_text().count(SDF_TERMINATOR) == 2
        assert json.loads((first / "names.json").read_text())["names"] == [
            "MOL0_0",
            "MOL1_1",
        ]
        # The shared reference data has to ride along inside each slice.
        for name in children:
            assert (out / name / "prep_receptor.pdbqt").read_text() == "RECEPTOR\n"
            assert (out / name / "box.pdb").read_text() == "BOX\n"
        # Last batch is the short one.
        assert json.loads((out / "batch_002" / "names.json").read_text())["names"] == [
            "MOL4_4"
        ]

    print("split_ligands.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Chunk a ligand library into batch folders.")
    parser.add_argument("--library", type=Path, help="ligand library (.sdf or .smi)")
    parser.add_argument("--receptor", type=Path, help="prepared receptor PDBQT")
    parser.add_argument("--box", type=Path, help="docking box PDB")
    parser.add_argument("--out", type=Path, help="output folder of batch directories")
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        _selftest()
        return 0
    if not all((args.library, args.receptor, args.box, args.out)):
        parser.error("--library, --receptor, --box and --out are required")

    run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
