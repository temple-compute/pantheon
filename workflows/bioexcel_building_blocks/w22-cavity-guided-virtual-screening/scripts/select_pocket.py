#!/usr/bin/env python3
"""
Stage 4 (select_pocket) -- pick which fpocket cavity to dock into.

Bridges the two halves of the pipeline. Takes the cavities that survived
``fpocket_filter``, optionally drops the ones that sit far from a residue
selection of interest, ranks what is left, and names the winner.

The winner is emitted as a *generated BioBB config file*, not as a number:
``fpocket_select`` only accepts its pocket number through ``--config``, so the
downstream step's config is this step's output artifact, wired by an ordinary
edge. That is what makes a runtime-chosen pocket reachable from a CLI that has
no ``--pocket`` flag.

The distance filter is a port of ``filter_residue_com`` from
biobb_vs_workflows/cavity_analysis/cavity_analysis.py:243-358 -- compare the
centre of mass of each pocket's alpha spheres against the centre of mass of a
residue selection, and keep the pockets within ``--distance-threshold``.

Usage:
    select_pocket.py --pockets filtered_pockets.zip --summary summary.json \
        --structure protein.pdb --out-config fpocket_select.yaml \
        --out-report pocket_report.json \
        [--residue-selection "resid 37 or resid 49"] \
        [--distance-threshold 10] [--rank-by druggability_score]
    select_pocket.py --selftest
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

import yaml

# Ranking keys fpocket reports per pocket in its summary JSON. All are
# "bigger is better", which is what makes the ranking a plain max().
RANK_KEYS = ("druggability_score", "score", "volume")


def pocket_number(name: str) -> int | None:
    """Extract N from an fpocket member name like ``pocket3_atm.pdb``."""
    match = re.search(r"pocket(\d+)", name)
    return int(match.group(1)) if match else None


def read_summary(summary_path: Path) -> dict[int, dict]:
    """
    Load fpocket's summary JSON into ``{pocket_number: {metric: value}}``.

    fpocket writes ``{"pocket1": {"score": ..., ...}, ...}``; the numeric key is
    what every other step (and ``--pocket``) refers to a pocket by.
    """
    raw = json.loads(summary_path.read_text())
    pockets: dict[int, dict] = {}
    for key, metrics in raw.items():
        num = pocket_number(key)
        if num is not None and isinstance(metrics, dict):
            pockets[num] = metrics
    return pockets


def pockets_in_zip(pockets_zip: Path) -> list[int]:
    """The pocket numbers present in a filtered-pockets zip, sorted."""
    with zipfile.ZipFile(pockets_zip) as zf:
        nums = {pocket_number(n) for n in zf.namelist()}
    return sorted(n for n in nums if n is not None)


def _center_of_mass(coords: "list[tuple[float, float, float]]") -> tuple[float, float, float]:
    """Unweighted centroid of a coordinate list. Empty list -> ValueError."""
    if not coords:
        raise ValueError("no coordinates")
    n = len(coords)
    return (
        sum(c[0] for c in coords) / n,
        sum(c[1] for c in coords) / n,
        sum(c[2] for c in coords) / n,
    )


def _distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    """Euclidean distance between two points."""
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def parse_pqr_coords(text: str) -> list[tuple[float, float, float]]:
    """
    Pull x/y/z out of a PQR body.

    fpocket's ``pocketN_vert.pqr`` holds the alpha-sphere vertices. PQR is
    whitespace-delimited rather than column-fixed like PDB, so the coordinates
    are fields 5-7 counting from the record name.
    """
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


def filter_by_distance(
    pockets_zip: Path,
    structure: Path,
    candidates: list[int],
    residue_selection: str,
    distance_threshold: float,
) -> list[int]:
    """
    Keep only the pockets whose centre of mass is within *distance_threshold*
    of the centre of mass of *residue_selection* on *structure*.

    MDAnalysis is imported here rather than at module scope so that
    ``--selftest`` and the no-selection path stay stdlib-only, and so a missing
    MDAnalysis never breaks a run that was not going to use it.
    """
    import MDAnalysis as mda  # noqa: PLC0415

    universe = mda.Universe(str(structure))
    selected = universe.select_atoms(residue_selection)
    if len(selected) == 0:
        raise ValueError(
            f"residue selection {residue_selection!r} matched no atoms in {structure}"
        )
    residue_com = tuple(float(v) for v in selected.center_of_mass())

    kept: list[int] = []
    with zipfile.ZipFile(pockets_zip) as zf:
        vert_members = {
            pocket_number(n): n for n in zf.namelist() if n.endswith("_vert.pqr")
        }
        for num in candidates:
            member = vert_members.get(num)
            if member is None:
                continue
            coords = parse_pqr_coords(zf.read(member).decode("utf-8", "replace"))
            if not coords:
                continue
            if _distance(_center_of_mass(coords), residue_com) < distance_threshold:
                kept.append(num)
    return kept


def rank_pockets(
    candidates: list[int], summary: dict[int, dict], rank_by: str
) -> list[tuple[int, float]]:
    """
    Order *candidates* best-first by *rank_by*, as ``(pocket, value)`` pairs.

    A pocket missing the metric sorts last rather than raising: fpocket
    occasionally omits a score for a degenerate cavity, and losing the whole
    run over one such pocket would be worse than ranking it bottom.
    """
    scored = [(num, float(summary.get(num, {}).get(rank_by, float("-inf")))) for num in candidates]
    return sorted(scored, key=lambda pair: (-pair[1], pair[0]))


def run(args: argparse.Namespace) -> int:
    """Select a pocket, write the config + report, and return the pocket number."""
    summary = read_summary(args.summary)
    candidates = pockets_in_zip(args.pockets)
    if not candidates:
        raise SystemExit(
            f"{args.pockets} contains no pockets -- loosen configs/fpocket_filter.yaml"
        )

    surviving = candidates
    if args.residue_selection:
        surviving = filter_by_distance(
            args.pockets,
            args.structure,
            candidates,
            args.residue_selection,
            args.distance_threshold,
        )
        if not surviving:
            raise SystemExit(
                f"no pocket within {args.distance_threshold} A of "
                f"{args.residue_selection!r} -- raise --distance-threshold"
            )

    ranking = rank_pockets(surviving, summary, args.rank_by)
    best = ranking[0][0]

    args.out_config.parent.mkdir(parents=True, exist_ok=True)
    args.out_config.write_text(yaml.safe_dump({"properties": {"pocket": best}}))

    args.out_report.parent.mkdir(parents=True, exist_ok=True)
    args.out_report.write_text(
        json.dumps(
            {
                "selected_pocket": best,
                "rank_by": args.rank_by,
                "residue_selection": args.residue_selection or None,
                "distance_threshold": args.distance_threshold,
                "candidates": candidates,
                "surviving": surviving,
                "ranking": [
                    {"pocket": num, args.rank_by: value, **summary.get(num, {})}
                    for num, value in ranking
                ],
            },
            indent=2,
        )
        + "\n"
    )
    print(
        f"select_pocket.py: {len(candidates)} candidate(s) -> {len(surviving)} "
        f"surviving -> pocket {best} (best {args.rank_by})"
    )
    return best


def _selftest() -> None:
    """Rank a synthetic pocket set and assert the emitted config round-trips."""
    import tempfile

    assert pocket_number("pocket12_atm.pdb") == 12
    assert pocket_number("no_number_here.pdb") is None

    coords = parse_pqr_coords(
        "ATOM      1 APOL STP   1       1.000   2.000   3.000  0.00  1.00\n"
        "ATOM      2 APOL STP   1       3.000   4.000   5.000  0.00  1.00\n"
        "REMARK ignored\n"
    )
    assert coords == [(1.0, 2.0, 3.0), (3.0, 4.0, 5.0)], coords
    assert _center_of_mass(coords) == (2.0, 3.0, 4.0)
    assert abs(_distance((0.0, 0.0, 0.0), (3.0, 4.0, 0.0)) - 5.0) < 1e-9

    summary = {
        1: {"druggability_score": 0.5, "volume": 900},
        2: {"druggability_score": 0.9, "volume": 300},
        3: {"volume": 5000},  # no druggability at all -> must sort last, not raise
    }
    assert rank_pockets([1, 2, 3], summary, "druggability_score")[0] == (2, 0.9)
    assert rank_pockets([1, 2, 3], summary, "druggability_score")[-1][0] == 3
    # --rank-by actually changes the answer, which is the point of the flag.
    assert rank_pockets([1, 2, 3], summary, "volume")[0] == (3, 5000.0)

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        summary_path = tmpdir / "summary.json"
        summary_path.write_text(
            json.dumps({f"pocket{n}": m for n, m in summary.items()})
        )
        assert read_summary(summary_path) == summary

        pockets_zip = tmpdir / "filtered.zip"
        with zipfile.ZipFile(pockets_zip, "w") as zf:
            for num in (1, 2):
                zf.writestr(f"pocket{num}_atm.pdb", "ATOM\n")
        assert pockets_in_zip(pockets_zip) == [1, 2]

        args = argparse.Namespace(
            pockets=pockets_zip,
            summary=summary_path,
            structure=tmpdir / "unused.pdb",
            out_config=tmpdir / "fpocket_select.yaml",
            out_report=tmpdir / "pocket_report.json",
            residue_selection="",
            distance_threshold=10.0,
            rank_by="druggability_score",
        )
        assert run(args) == 2
        loaded = yaml.safe_load(args.out_config.read_text())
        assert loaded == {"properties": {"pocket": 2}}, loaded
        assert json.loads(args.out_report.read_text())["selected_pocket"] == 2

    print("select_pocket.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Select the fpocket cavity to dock into.")
    parser.add_argument("--pockets", type=Path, help="filtered pockets zip")
    parser.add_argument("--summary", type=Path, help="fpocket summary JSON")
    parser.add_argument("--structure", type=Path, help="protein PDB the pockets came from")
    parser.add_argument("--out-config", type=Path, help="generated fpocket_select config")
    parser.add_argument("--out-report", type=Path, help="JSON record of the selection")
    parser.add_argument(
        "--residue-selection",
        default="",
        help="MDAnalysis selection; keep only pockets near it. Empty = keep all.",
    )
    parser.add_argument("--distance-threshold", type=float, default=10.0)
    parser.add_argument("--rank-by", choices=RANK_KEYS, default="druggability_score")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        _selftest()
        return 0
    required = (args.pockets, args.summary, args.out_config, args.out_report)
    if not all(required):
        parser.error("--pockets, --summary, --out-config and --out-report are required")
    if args.residue_selection and not args.structure:
        parser.error("--residue-selection needs --structure")

    run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
