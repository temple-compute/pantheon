#!/usr/bin/env python3
"""
Stage 6 (dock) -- dock one batch of ligands. Runs once per map clone.

Body of the ``dock`` task's ``map:`` template. Each clone receives a copy of one
``batch_NNN/`` directory (its ligands plus its own copy of the prepared receptor
and the docking box) and writes every result into a single output folder, which
the engine pins at ``dock.gathered/<i>/`` for the ``rank`` task to read.

Per ligand this is the port of vs_autodock.py:705-809: ``babel_convert`` to
PDBQT, then ``autodock_vina_run``, each wrapped in try/except plus an
output-non-empty check. The BioBB python API is called in-process rather than
through the BioBB CLIs precisely so that guard is possible.

**This script must never exit non-zero.** horus-runtime has no per-task
``allow_failure``: a clone that fails either aborts the run (``fail_fast``) or
blocks the gather task (``continue``), so a single unparseable ligand would cost
the whole screen. A ligand that fails is recorded in ``status.json`` and the
clone still succeeds -- which is exactly the source workflow's semantics, where
a failed ligand is logged and dropped from the ranking.

Usage:
    dock_batch.py --batch batch_000/ --out docked/ --exhaustiveness 8 --cpu 1
    dock_batch.py --selftest
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path


def validate_output(*paths: Path) -> bool:
    """
    True when every path exists and is non-empty.

    Port of ``validate_step`` (vs_autodock.py:141). BioBB tools can return
    cleanly while writing an empty file, so existence alone is not enough.
    """
    return all(path.exists() and path.stat().st_size > 0 for path in paths)


def split_records(text: str, fmt: str) -> list[str]:
    """Split a batch's ligand file back into one record per ligand."""
    if fmt == "sdf":
        chunks = [chunk for chunk in text.split("$$$$\n") if chunk.strip()]
        return [chunk + "$$$$\n" for chunk in chunks]
    return [line + "\n" for line in text.splitlines() if line.strip()]


def prepare_ligand(record_path: Path, pdbqt_path: Path, fmt: str) -> None:
    """
    Convert one ligand to PDBQT via BioBB's babel_convert.

    SMILES input gets 3D coordinates generated and is protonated at pH 7.4
    (``step4_babel_protonate``); SDF input is assumed already protonated and is
    only reformatted (``step4b_babel_convert``), because writing PDBQT straight
    out of a toolkit discards the hydrogens the library author put there.
    """
    from biobb_chemistry.babelm.babel_convert import babel_convert  # noqa: PLC0415

    properties = {"coordinates": 3, "ph": 7.4} if fmt == "smi" else {}
    babel_convert(
        input_path=str(record_path),
        output_path=str(pdbqt_path),
        properties=properties,
    )


def dock_ligand(
    ligand_pdbqt: Path,
    receptor_pdbqt: Path,
    box_pdb: Path,
    out_pdbqt: Path,
    out_log: Path,
    exhaustiveness: int,
    cpu: int,
) -> None:
    """Dock one prepared ligand with AutoDock Vina via BioBB."""
    from biobb_vs.vina.autodock_vina_run import autodock_vina_run  # noqa: PLC0415

    autodock_vina_run(
        input_ligand_pdbqt_path=str(ligand_pdbqt),
        input_receptor_pdbqt_path=str(receptor_pdbqt),
        input_box_path=str(box_pdb),
        output_pdbqt_path=str(out_pdbqt),
        output_log_path=str(out_log),
        properties={"exhaustiveness": int(exhaustiveness), "cpu": int(cpu)},
    )


def run(args: argparse.Namespace) -> dict:
    """
    Dock every ligand in the batch. Returns the status document.

    Never raises for a per-ligand problem; see the module docstring.
    """
    # Created first and unconditionally: the output folder is this clone's
    # declared artifact, so it must exist even if every ligand fails.
    batch = args.batch.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = out / "work"
    work.mkdir(exist_ok=True)

    # Run from `work`, never from the clone's own working directory.
    #
    # A map clone's id is "dock[0]" (MapExpander zero-pads an index in square
    # brackets) and that id becomes its directory name. BioBB stages input
    # files into a sandbox under the *current* directory and shells out to
    # obabel/vina through an unquoted shell command, so a bracketed path makes
    # the shell treat it as a glob, match nothing, and fail with
    # "zsh:1: no matches found". `work` sits under dock.gathered/<i>/, which
    # has no brackets, so every path BioBB constructs is shell-safe.
    import os  # noqa: PLC0415 - only needed for this workaround

    previous_cwd = Path.cwd()
    os.chdir(work)
    try:
        return _dock_all(batch, out, work, args)
    finally:
        os.chdir(previous_cwd)


def _dock_all(batch: Path, out: Path, work: Path, args: argparse.Namespace) -> dict:
    """Inner loop of :func:`run`, executed from a shell-safe directory."""

    manifest = json.loads((batch / "names.json").read_text())
    fmt = manifest["format"]
    names = manifest["names"]
    records = split_records((batch / f"ligands.{fmt}").read_text(), fmt)

    receptor = batch / "prep_receptor.pdbqt"
    box = batch / "box.pdb"

    ligands: list[dict] = []
    for name, record in zip(names, records):
        entry: dict = {"name": name, "docked": False, "stage": None, "error": None}
        record_path = work / f"{name}.{fmt}"
        ligand_pdbqt = work / f"{name}.pdbqt"
        out_pdbqt = out / f"{name}.pdbqt"
        out_log = out / f"{name}.log"

        record_path.write_text(record)
        try:
            prepare_ligand(record_path, ligand_pdbqt, fmt)
            if not validate_output(ligand_pdbqt):
                raise RuntimeError("babel_convert produced no PDBQT")
        except Exception as exc:  # noqa: BLE001 - one bad ligand must not stop the batch
            entry["stage"] = "prepare"
            entry["error"] = f"{type(exc).__name__}: {exc}"
            traceback.print_exc()
            ligands.append(entry)
            continue

        try:
            dock_ligand(
                ligand_pdbqt, receptor, box, out_pdbqt, out_log,
                args.exhaustiveness, args.cpu,
            )
            if not validate_output(out_pdbqt, out_log):
                raise RuntimeError("autodock_vina_run produced no output")
        except Exception as exc:  # noqa: BLE001 - same
            entry["stage"] = "dock"
            entry["error"] = f"{type(exc).__name__}: {exc}"
            traceback.print_exc()
            ligands.append(entry)
            continue

        entry["docked"] = True
        ligands.append(entry)

    status = {
        "batch": batch.name,
        "format": fmt,
        "total": len(names),
        "docked": sum(1 for entry in ligands if entry["docked"]),
        "ligands": ligands,
    }
    (out / "status.json").write_text(json.dumps(status, indent=2) + "\n")
    print(
        f"dock_batch.py: {status['docked']}/{status['total']} ligand(s) docked "
        f"in {batch.name}"
    )
    return status


def _selftest() -> None:
    """Exercise the batch loop with the BioBB calls stubbed out."""
    import tempfile

    assert split_records("A\n$$$$\nB\n$$$$\n", "sdf") == ["A\n$$$$\n", "B\n$$$$\n"]
    assert split_records("CCO\n\nCCN\n", "smi") == ["CCO\n", "CCN\n"]

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)

        # An empty output file must not count as success -- BioBB tools can
        # return cleanly having written nothing.
        missing = tmpdir / "missing"
        empty = tmpdir / "empty"
        empty.touch()
        filled = tmpdir / "filled"
        filled.write_text("x")
        assert validate_output(filled) is True
        assert validate_output(empty) is False
        assert validate_output(missing) is False
        assert validate_output(filled, empty) is False

        batch = tmpdir / "batch_000"
        batch.mkdir()
        (batch / "ligands.sdf").write_text("GOOD\n$$$$\nBAD\n$$$$\n")
        (batch / "names.json").write_text(
            json.dumps({"format": "sdf", "names": ["good_0", "bad_1"]})
        )
        (batch / "prep_receptor.pdbqt").write_text("RECEPTOR\n")
        (batch / "box.pdb").write_text("BOX\n")

        # Stub the two BioBB calls so the selftest needs no chemistry stack.
        # "bad_1" blows up in preparation; the clone must still finish cleanly
        # with a status document, which is the whole contract of this script.
        def fake_prepare(record_path: Path, pdbqt_path: Path, fmt: str) -> None:
            if "bad" in record_path.name:
                raise RuntimeError("bad ligand")
            pdbqt_path.write_text("LIGAND\n")

        def fake_dock(lig, rec, box, out_pdbqt, out_log, exhaustiveness, cpu) -> None:
            out_pdbqt.write_text("REMARK VINA RESULT:    -9.1  0.0  0.0\n")
            out_log.write_text("log\n")

        globals()["prepare_ligand"] = fake_prepare
        globals()["dock_ligand"] = fake_dock

        out = tmpdir / "docked"
        args = argparse.Namespace(batch=batch, out=out, exhaustiveness=4, cpu=1)
        status = run(args)

        assert status["total"] == 2, status
        assert status["docked"] == 1, status
        assert status["ligands"][0]["docked"] is True
        assert status["ligands"][1]["docked"] is False
        assert status["ligands"][1]["stage"] == "prepare"
        assert (out / "good_0.pdbqt").exists()
        assert not (out / "bad_1.pdbqt").exists()
        assert json.loads((out / "status.json").read_text())["docked"] == 1

    print("dock_batch.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dock one batch of ligands with AutoDock Vina.")
    parser.add_argument("--batch", type=Path, help="one batch_NNN/ folder")
    parser.add_argument("--out", type=Path, help="output folder for this clone")
    parser.add_argument("--exhaustiveness", type=int, default=8)
    parser.add_argument("--cpu", type=int, default=1)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        _selftest()
        return 0
    if not (args.batch and args.out):
        parser.error("--batch and --out are required")

    run(args)
    # Always 0: a failed ligand is data, not a task failure. See the module
    # docstring -- a non-zero exit here would block the gather task.
    return 0


if __name__ == "__main__":
    sys.exit(main())
