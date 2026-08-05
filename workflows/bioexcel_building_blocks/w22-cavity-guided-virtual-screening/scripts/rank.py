#!/usr/bin/env python3
"""
Stage 7 (rank) -- fan-in. Rank every docked ligand by binding affinity.

Reads the map's gathered folder, which holds one numbered slot per ``dock``
clone (``dock.gathered/0/``, ``dock.gathered/1/``, ...), each containing that
batch's PDBQT outputs and its ``status.json``. Produces the run's actual
deliverables: a ranking, a screening summary, and the top-K poses.

Affinity comes from the first ``REMARK VINA RESULT`` line of each PDBQT --
Vina writes poses best-first, so the first one is the best one. This is the
port of ``get_affinity``/``get_ranking``/``save_ranking``
(vs_autodock.py:62-139, 244-299).

One deliberate fix on port: the source tests ``if affinity:``, which silently
drops a ligand whose best affinity is exactly 0.0. This tests against None.

Pose conversion needs ``obabel`` on PATH; if it is missing the ranking is still
written and only the poses are skipped, because the CSV is the result that
matters and a missing viewer binary should not fail the run.

Usage:
    rank.py --results dock.gathered/ --scores scores.csv \
        --summary summary.json --poses poses/ --top 10
    rank.py --selftest
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

AFFINITY_PATTERN = re.compile(r"REMARK VINA RESULT:\s+(-?\d+\.\d+)")


def get_affinity(pdbqt_path: Path) -> float | None:
    """
    Best affinity in a Vina output PDBQT, or None if it holds no result.

    Only the first match is read: Vina orders poses best-first, so scanning
    further would find worse poses of the same ligand.
    """
    try:
        text = pdbqt_path.read_text(errors="replace")
    except OSError:
        return None
    match = AFFINITY_PATTERN.search(text)
    return float(match.group(1)) if match else None


def collect(results: Path) -> tuple[list[dict], list[dict]]:
    """
    Walk the gathered slots. Returns ``(ranked, attempted)``.

    ``attempted`` is every ligand any clone tried, taken from the per-batch
    ``status.json`` -- that is what makes the success rate meaningful, since a
    ligand that failed to convert leaves no PDBQT behind to be counted.
    """
    ranked: list[dict] = []
    attempted: list[dict] = []

    for slot in sorted(results.iterdir(), key=lambda p: p.name):
        if not slot.is_dir():
            continue
        # The engine pins a clone's folder output straight at the slot
        # (MapExpander._set_output_path), so status.json normally sits directly
        # in the slot -- but one nested level is tolerated so the reducer does
        # not depend on that pinning detail. First hit wins; never both.
        for docked in [slot, *(p for p in slot.iterdir() if p.is_dir())]:
            status_path = docked / "status.json"
            if not status_path.exists():
                continue
            status = json.loads(status_path.read_text())
            attempted.extend(status.get("ligands", []))
            for entry in status.get("ligands", []):
                if not entry.get("docked"):
                    continue
                pdbqt = docked / f"{entry['name']}.pdbqt"
                affinity = get_affinity(pdbqt)
                if affinity is not None:
                    ranked.append(
                        {
                            "name": entry["name"],
                            "affinity": affinity,
                            "pdbqt": str(pdbqt),
                        }
                    )
            break

    ranked.sort(key=lambda item: (item["affinity"], item["name"]))
    return ranked, attempted


def write_scores(ranked: list[dict], scores_path: Path, top: int) -> list[dict]:
    """
    Write the ranking CSV. Returns the rows actually written.

    Header matches ``save_ranking`` (vs_autodock.py:92) so the output is
    drop-in comparable with the original CLI's scores.csv.
    """
    rows = ranked[:top] if top > 0 else ranked
    scores_path.parent.mkdir(parents=True, exist_ok=True)
    with scores_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Rank", "Affinity", "Index", "Identifier"])
        for rank, item in enumerate(rows, start=1):
            writer.writerow([rank, item["affinity"], rank - 1, item["name"]])
    return rows


def write_poses(rows: list[dict], poses_dir: Path) -> int:
    """
    Convert the ranked ligands' PDBQT poses to PDB. Returns the count written.

    Port of ``step6_babel_prepare_pose``. Shelling out to obabel rather than
    importing a toolkit keeps this task runnable in a bare environment.
    """
    if not rows:
        return 0
    if shutil.which("obabel") is None:
        print("rank.py: obabel not on PATH, skipping pose conversion")
        return 0

    poses_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for item in rows:
        target = poses_dir / f"{item['name']}_poses.pdb"
        result = subprocess.run(
            ["obabel", "-ipdbqt", item["pdbqt"], "-opdb", "-O", str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and target.exists() and target.stat().st_size > 0:
            written += 1
        else:
            print(f"rank.py: obabel failed for {item['name']}: {result.stderr.strip()}")
    return written


def run(args: argparse.Namespace) -> dict:
    """Rank the gathered results and write scores, summary, and poses."""
    ranked, attempted = collect(args.results)
    rows = write_scores(ranked, args.scores, args.top)
    poses_written = write_poses(rows, args.poses) if args.poses else 0

    total = len(attempted)
    summary = {
        "total_ligands": total,
        "docked": len(ranked),
        "failed": total - len(ranked),
        "success_rate_percent": round(len(ranked) / total * 100, 2) if total else 0.0,
        "ranked_written": len(rows),
        "poses_written": poses_written,
        "best": (
            {"name": ranked[0]["name"], "affinity": ranked[0]["affinity"]}
            if ranked
            else None
        ),
        "failures": [
            {"name": e["name"], "stage": e.get("stage"), "error": e.get("error")}
            for e in attempted
            if not e.get("docked")
        ],
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2) + "\n")

    print(
        f"rank.py: {summary['docked']}/{total} ligand(s) docked "
        f"({summary['success_rate_percent']}%), {len(rows)} ranked"
    )
    return summary


def _selftest() -> None:
    """Rank a synthetic gathered tree covering the edge cases that bit the source."""
    import tempfile

    assert get_affinity(Path("/nonexistent/nope.pdbqt")) is None

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        results = tmpdir / "dock.gathered"

        def make_slot(index: int, ligands: list[dict], pdbqts: dict[str, str]) -> None:
            slot = results / str(index) / "docked"
            slot.mkdir(parents=True)
            (slot / "status.json").write_text(
                json.dumps({"batch": f"batch_{index}", "ligands": ligands})
            )
            for name, text in pdbqts.items():
                (slot / f"{name}.pdbqt").write_text(text)

        result_line = "REMARK VINA RESULT:  {:>8}      0.000      0.000\n"
        make_slot(
            0,
            [
                {"name": "good_0", "docked": True},
                {"name": "bad_1", "docked": False, "stage": "prepare", "error": "boom"},
            ],
            {"good_0": result_line.format("-9.8")},
        )
        make_slot(
            1,
            [
                {"name": "best_2", "docked": True},
                # Affinity exactly 0.0: the source's `if affinity:` dropped this.
                {"name": "zero_3", "docked": True},
                # Claims success but wrote no VINA RESULT line.
                {"name": "empty_4", "docked": True},
            ],
            {
                "best_2": result_line.format("-11.2"),
                "zero_3": result_line.format("0.0"),
                "empty_4": "REMARK nothing useful here\n",
            },
        )

        args = argparse.Namespace(
            results=results,
            scores=tmpdir / "scores.csv",
            summary=tmpdir / "summary.json",
            poses=None,
            top=0,
        )
        summary = run(args)

        assert summary["total_ligands"] == 5, summary
        # good_0, best_2, zero_3 rank; bad_1 never docked, empty_4 has no result.
        assert summary["docked"] == 3, summary
        assert summary["failed"] == 2, summary
        assert summary["best"] == {"name": "best_2", "affinity": -11.2}, summary["best"]

        rows = list(csv.DictReader(args.scores.open()))
        assert [r["Identifier"] for r in rows] == ["best_2", "good_0", "zero_3"], rows
        assert [r["Rank"] for r in rows] == ["1", "2", "3"], rows
        # The 0.0 ligand survived, which is the fix over the source workflow.
        assert rows[-1]["Affinity"] == "0.0", rows

        # --top truncates the CSV but not the summary's counts.
        args.scores = tmpdir / "top1.csv"
        args.top = 1
        summary = run(args)
        assert summary["ranked_written"] == 1
        assert summary["docked"] == 3
        assert len(list(csv.DictReader(args.scores.open()))) == 1

    print("rank.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rank gathered docking results.")
    parser.add_argument("--results", type=Path, help="the map's gathered folder")
    parser.add_argument("--scores", type=Path, help="output ranking CSV")
    parser.add_argument("--summary", type=Path, help="output screening summary JSON")
    parser.add_argument("--poses", type=Path, default=None, help="output poses folder")
    parser.add_argument(
        "--top", type=int, default=0, help="keep only the top N; 0 keeps every ligand"
    )
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        _selftest()
        return 0
    if not all((args.results, args.scores, args.summary)):
        parser.error("--results, --scores and --summary are required")

    run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
