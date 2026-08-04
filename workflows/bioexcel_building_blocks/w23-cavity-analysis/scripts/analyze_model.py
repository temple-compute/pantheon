#!/usr/bin/env python3
"""
Stage 2 (analyze) -- detect and filter cavities on one model. One map clone.

Body of the ``analyze`` task's ``map:`` template. Each clone receives a copy of
one ``model_NNN/`` folder and runs the per-model pipeline from
biobb_vs_workflows/cavity_analysis/cavity_analysis.py:1019-1079:

    extract_molecule (protein, optionally chains)
      -> fpocket_run       (detect cavities)
      -> fpocket_filter    (score / druggability / volume windows)
      -> filter_residue_com  (keep cavities near a residue selection)

``filter_residue_com`` is not a BioBB block -- it is a repo-local step ported
from cavity_analysis.py:243-358. It compares the centre of mass of each
cavity's alpha spheres against the centre of mass of a residue selection and
keeps the cavities within a distance threshold.

Everything lands in a single output folder, which the engine pins at
``analyze.gathered/<i>/`` for the ``summarize`` task to read.

Like the docking clone in W-28, this script tolerates a per-model failure rather
than exiting non-zero: horus-runtime has no per-task ``allow_failure``, so a
clone that fails blocks the gather and costs the whole run. A model that fails
is recorded in ``status.json``. Note this is *stricter* than the source, where a
failing model aborts the run outright.

Usage:
    analyze_model.py --model model_000/ --out analyzed/ \
        [--residue-selection "resid 31 or resid 21"] [--distance-threshold 10] \
        [--chains A] [--skip-extraction]
    analyze_model.py --selftest
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import traceback
import zipfile
from pathlib import Path

# Shared with select_pocket.py in W-28; duplicated rather than imported because
# each pantheon workflow directory is a self-contained uv project.
import re

POCKET_RE = re.compile(r"pocket(\d+)")


def pocket_number(name: str) -> int | None:
    """Extract N from an fpocket member name like ``pocket3_vert.pqr``."""
    match = POCKET_RE.search(name)
    return int(match.group(1)) if match else None


def parse_pqr_coords(text: str) -> list[tuple[float, float, float]]:
    """Pull x/y/z out of a PQR body (whitespace-delimited, fields 5-7)."""
    coords: list[tuple[float, float, float]] = []
    for line in text.splitlines():
        if not line.startswith(("ATOM", "HETATM")):
            continue
        fields = line.split()
        if len(fields) < 8:
            continue
        try:
            coords.append((float(fields[5]), float(fields[6]), float(fields[7])))
        except ValueError:
            continue
    return coords


def center_of_mass(coords: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    """Unweighted centroid of a coordinate list."""
    if not coords:
        raise ValueError("no coordinates")
    n = len(coords)
    return tuple(sum(c[axis] for c in coords) / n for axis in range(3))  # type: ignore[return-value]


def distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    """Euclidean distance between two points."""
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def filter_residue_com(
    pockets_zip: Path,
    structure: Path,
    out_zip: Path,
    residue_selection: str,
    distance_threshold: float,
) -> list[str]:
    """
    Keep the cavities whose centre of mass is near *residue_selection*.

    Port of ``filter_residue_com`` (cavity_analysis.py:243-358). With no
    selection the step is a pass-through that keeps every cavity, mirroring the
    source's ``run_step: false`` behaviour. Returns the surviving pocket names.
    """
    with zipfile.ZipFile(pockets_zip) as zf:
        members = zf.namelist()
    all_pockets = sorted({f"pocket{n}" for n in map(pocket_number, members) if n is not None})

    if not residue_selection:
        shutil.copyfile(pockets_zip, out_zip)
        return all_pockets

    import MDAnalysis as mda  # noqa: PLC0415

    universe = mda.Universe(str(structure))
    selected = universe.select_atoms(residue_selection)
    if len(selected) == 0:
        raise ValueError(f"selection {residue_selection!r} matched no atoms in {structure}")
    residue_com = tuple(float(v) for v in selected.center_of_mass())

    kept: list[str] = []
    with zipfile.ZipFile(pockets_zip) as zf:
        vert = {pocket_number(n): n for n in zf.namelist() if n.endswith("_vert.pqr")}
        for num, member in sorted((k, v) for k, v in vert.items() if k is not None):
            coords = parse_pqr_coords(zf.read(member).decode("utf-8", "replace"))
            if coords and distance(center_of_mass(coords), residue_com) < distance_threshold:
                kept.append(f"pocket{num}")

    keep_nums = {pocket_number(name) for name in kept}
    with zipfile.ZipFile(pockets_zip) as src, zipfile.ZipFile(out_zip, "w") as dst:
        for member in src.namelist():
            if pocket_number(member) in keep_nums:
                dst.writestr(member, src.read(member))
    return kept


def extract_protein(structure: Path, out_pdb: Path, chains: str | None) -> Path:
    """Strip non-protein records, and optionally keep only some chains."""
    from biobb_structure_utils.utils.extract_molecule import extract_molecule  # noqa: PLC0415

    extract_molecule(
        input_structure_path=str(structure),
        output_molecule_path=str(out_pdb),
        properties={"molecule_type": "protein"},
    )
    if not chains:
        return out_pdb

    chains_pdb = out_pdb.with_name("chains.pdb")
    extract_molecule(
        input_structure_path=str(out_pdb),
        output_molecule_path=str(chains_pdb),
        # Quoted on purpose: YAML 1.1 reads a bare N or Y as a boolean, and a
        # chain really can be named "N". Same guard the source workflow uses.
        properties={"molecule_type": "chains", "chains": [str(c) for c in chains.split(",")]},
    )
    return chains_pdb


def detect_cavities(structure: Path, pockets_zip: Path, summary: Path) -> None:
    """Run fpocket with the source workflow's alpha-sphere settings."""
    from biobb_vs.fpocket.fpocket_run import fpocket_run  # noqa: PLC0415

    fpocket_run(
        input_pdb_path=str(structure),
        output_pockets_zip=str(pockets_zip),
        output_summary=str(summary),
        properties={
            "min_radius": 3,
            "max_radius": 6,
            "num_spheres": 35,
            "sort_by": "druggability_score",
        },
    )


def filter_cavities(
    pockets_zip: Path,
    summary: Path,
    out_zip: Path,
    score: list[float],
    druggability: list[float],
    volume: list[float],
) -> None:
    """Apply the score / druggability / volume windows."""
    from biobb_vs.fpocket.fpocket_filter import fpocket_filter  # noqa: PLC0415

    fpocket_filter(
        input_pockets_zip=str(pockets_zip),
        input_summary=str(summary),
        output_filter_pockets_zip=str(out_zip),
        properties={
            "score": score,
            "druggability_score": druggability,
            "volume": volume,
        },
    )


def run(args: argparse.Namespace) -> dict:
    """Analyse one model. Never raises for a per-model problem."""
    model = args.model.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = out / "work"
    work.mkdir(exist_ok=True)

    name_file = model / "name.txt"
    name = name_file.read_text().strip() if name_file.exists() else model.name

    # Run from `work`: a map clone's directory is named "analyze[0]", and BioBB
    # shells out unquoted, so a bracketed path is glob-expanded and matches
    # nothing. See the W-28 README for the full story.
    previous_cwd = Path.cwd()
    os.chdir(work)
    status: dict = {"model": name, "analyzed": False, "stage": None, "error": None}
    try:
        structure = model / "model.pdb"
        pockets_zip = work / "all_pockets.zip"
        summary = out / "summary.json"
        filtered_zip = work / "filtered_pockets.zip"
        final_zip = out / "filtered_pockets.zip"

        if args.skip_extraction and not args.chains:
            prepared = structure
        else:
            status["stage"] = "extract"
            prepared = extract_protein(structure, work / "protein.pdb", args.chains)

        status["stage"] = "fpocket_run"
        detect_cavities(prepared, pockets_zip, summary)

        status["stage"] = "fpocket_filter"
        filter_cavities(
            pockets_zip, summary, filtered_zip,
            args.score, args.druggability, args.volume,
        )

        status["stage"] = "filter_residue_com"
        if filtered_zip.exists():
            kept = filter_residue_com(
                filtered_zip, prepared, final_zip,
                args.residue_selection, args.distance_threshold,
            )
        else:
            # fpocket_filter writes nothing when no cavity falls inside the
            # windows ("No matches found"). A model with no druggable cavity is
            # a real answer, not a failure -- it is simply absent from the
            # summaries, exactly as in the source workflow.
            kept = []

        shutil.copyfile(prepared, out / "model.pdb")
        status.update({"analyzed": True, "stage": None, "pockets": kept})
        print(f"analyze_model.py: {name} -> {len(kept)} pocket(s) kept")
    except Exception as exc:  # noqa: BLE001 - one bad model must not block the gather
        status["error"] = f"{type(exc).__name__}: {exc}"
        status["pockets"] = []
        traceback.print_exc()
        print(f"analyze_model.py: {name} FAILED at {status['stage']}")
    finally:
        os.chdir(previous_cwd)

    (out / "status.json").write_text(json.dumps(status, indent=2) + "\n")
    return status


def _selftest() -> None:
    """Exercise the pocket filter and the clone loop with BioBB stubbed out."""
    import tempfile

    assert pocket_number("pocket12_vert.pqr") == 12
    assert pocket_number("nothing.pdb") is None
    assert center_of_mass([(0.0, 0.0, 0.0), (2.0, 4.0, 6.0)]) == (1.0, 2.0, 3.0)
    assert abs(distance((0.0, 0.0, 0.0), (0.0, 3.0, 4.0)) - 5.0) < 1e-9

    coords = parse_pqr_coords(
        "ATOM      1 APOL STP   1       1.000   1.000   1.000  0.00  1.00\n"
        "REMARK skipped\n"
    )
    assert coords == [(1.0, 1.0, 1.0)], coords

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)

        # Two cavities: one at the origin, one 100 A away.
        pockets = tmpdir / "pockets.zip"
        with zipfile.ZipFile(pockets, "w") as zf:
            zf.writestr(
                "pocket1_vert.pqr",
                "ATOM      1 APOL STP   1       0.000   0.000   0.000  0.00  1.00\n",
            )
            zf.writestr("pocket1_atm.pdb", "ATOM\n")
            zf.writestr(
                "pocket2_vert.pqr",
                "ATOM      1 APOL STP   1     100.000 100.000 100.000  0.00  1.00\n",
            )
            zf.writestr("pocket2_atm.pdb", "ATOM\n")

        # No selection: pass-through, every cavity kept and the zip copied.
        out_zip = tmpdir / "out.zip"
        assert filter_residue_com(pockets, tmpdir / "x.pdb", out_zip, "", 10.0) == [
            "pocket1",
            "pocket2",
        ]
        assert out_zip.exists()

        # The clone loop must survive a failing model and still write status.
        model = tmpdir / "model_000"
        model.mkdir()
        (model / "model.pdb").write_text("ATOM\n")
        (model / "name.txt").write_text("cluster0\n")

        def boom(*_args, **_kwargs):
            raise RuntimeError("fpocket exploded")

        globals()["extract_protein"] = lambda structure, out_pdb, chains: structure
        globals()["detect_cavities"] = boom

        out = tmpdir / "analyzed"
        status = run(
            argparse.Namespace(
                model=model, out=out, chains=None, skip_extraction=False,
                score=[0.0, 1.0], druggability=[0.0, 1.0], volume=[100.0, 5000.0],
                residue_selection="", distance_threshold=10.0,
            )
        )
        assert status["analyzed"] is False, status
        assert status["stage"] == "fpocket_run", status
        assert status["model"] == "cluster0", status
        assert (out / "status.json").exists()

    print("analyze_model.py selftest: OK")


def _range(text: str) -> list[float]:
    """Parse a ``lo,hi`` filter window."""
    lo, hi = (float(part) for part in text.split(","))
    return [lo, hi]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect and filter cavities on one model.")
    parser.add_argument("--model", type=Path, help="one model_NNN/ folder")
    parser.add_argument("--out", type=Path, help="output folder for this clone")
    parser.add_argument("--chains", default=None, help="comma-separated chains to keep")
    parser.add_argument("--skip-extraction", action="store_true")
    parser.add_argument("--score", type=_range, default=[0.4, 1.0])
    parser.add_argument("--druggability", type=_range, default=[0.4, 1.0])
    parser.add_argument("--volume", type=_range, default=[200.0, 5000.0])
    parser.add_argument("--residue-selection", default="")
    parser.add_argument("--distance-threshold", type=float, default=10.0)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        _selftest()
        return 0
    if not (args.model and args.out):
        parser.error("--model and --out are required")

    run(args)
    # Always 0: a failed model is data. A non-zero exit would block the gather.
    return 0


if __name__ == "__main__":
    sys.exit(main())
