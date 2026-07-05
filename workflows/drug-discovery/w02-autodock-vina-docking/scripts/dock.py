#!/usr/bin/env python3
"""
Stage 2 (dock) — run AutoDock Vina for every prepared ligand.

Untars the archive from the prep stage, then docks each ligand PDBQT against the
receptor using the Vina Python bindings (``from vina import Vina``), writing the
top poses (with their ``REMARK VINA RESULT`` affinities) to per-ligand output
PDBQTs. Results are tarred into a single archive for the summary stage.

A failing ligand is logged and skipped rather than aborting the whole screen, so
one bad structure never sinks the run. The archive assembly / error-manifest
helpers are stdlib and covered by ``--selftest``; the Vina call itself needs the
``vina`` package from the stage's uv environment.

Usage:
    dock.py --inputs vina_inputs.tar.gz --out docking_out.tar.gz \
            --exhaustiveness 16 --n-poses 9 --cpu 0
    dock.py --selftest
"""

from __future__ import annotations  # portable across python3 (>=3.9)

import argparse
import json
import sys
import tarfile
import tempfile
from pathlib import Path


def extract_inputs(inputs: Path, dest: Path) -> tuple[Path, list[Path], dict]:
    """Untar *inputs*; return (receptor_pdbqt, ligand_pdbqts, box)."""
    with tarfile.open(inputs) as tar:
        tar.extractall(dest, filter="data")  # safe extraction
    root = dest / "vina_inputs"
    receptor = root / "receptor.pdbqt"
    box = json.loads((root / "box.json").read_text())
    ligands = sorted((root / "ligands").glob("*.pdbqt"))
    if not receptor.exists():
        raise FileNotFoundError("receptor.pdbqt missing from inputs archive")
    if not ligands:
        raise FileNotFoundError("no ligand PDBQT files in inputs archive")
    return receptor, ligands, box


def make_archive(out_dir: Path, out: Path) -> None:
    """Tar the docking output directory to *out*."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out, "w:gz") as tar:
        tar.add(out_dir, arcname="docking_out")


def dock_all(
    receptor: Path,
    ligands: list[Path],
    box: dict,
    out_dir: Path,
    exhaustiveness: int,
    n_poses: int,
    cpu: int,
) -> list[dict]:
    """Dock every ligand; return a per-ligand manifest (status + best score)."""
    from vina import Vina

    center = box["center"]
    size = box["size"]
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest: list[dict] = []
    for lig in ligands:
        name = lig.stem
        try:
            v = Vina(sf_name="vina", cpu=cpu, verbosity=0)
            v.set_receptor(str(receptor))
            v.set_ligand_from_file(str(lig))
            v.compute_vina_maps(center=center, box_size=size)
            v.dock(exhaustiveness=exhaustiveness, n_poses=n_poses)
            out_pdbqt = out_dir / f"{name}_out.pdbqt"
            v.write_poses(str(out_pdbqt), n_poses=n_poses, overwrite=True)
            # energies()[0][0] is the best pose's total affinity (kcal/mol).
            best = float(v.energies(n_poses=1)[0][0])
            print(f"dock.py: {name} best affinity {best:.2f} kcal/mol")
            manifest.append({"ligand": name, "status": "ok", "best_affinity": best})
        except Exception as exc:  # noqa: BLE001 — keep screening the rest
            print(f"dock.py: WARNING docking failed for {name}: {exc}")
            manifest.append({"ligand": name, "status": "failed", "error": str(exc)})
    return manifest


def run(args: argparse.Namespace) -> int:
    """Extract, dock, write manifest, tar. Returns count of successful ligands."""
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        receptor, ligands, box = extract_inputs(args.inputs, work / "in")
        out_dir = work / "docking_out"
        manifest = dock_all(
            receptor, ligands, box, out_dir,
            args.exhaustiveness, args.n_poses, args.cpu,
        )
        (out_dir).mkdir(parents=True, exist_ok=True)
        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        make_archive(out_dir, args.out)

    ok = sum(1 for m in manifest if m["status"] == "ok")
    print(f"dock.py: docked {ok}/{len(manifest)} ligand(s) → {args.out}")
    return ok


def _selftest() -> None:
    """Exercise the stdlib extract/archive helpers with a synthetic archive."""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)

        # Build a minimal vina_inputs archive by hand.
        staging = d / "vina_inputs"
        (staging / "ligands").mkdir(parents=True)
        (staging / "receptor.pdbqt").write_text("REMARK receptor\n")
        (staging / "ligands" / "benzene.pdbqt").write_text("REMARK ligand\n")
        (staging / "box.json").write_text(
            json.dumps({"center": [1.0, 2.0, 3.0], "size": [20.0, 20.0, 20.0]})
        )
        inputs = d / "vina_inputs.tar.gz"
        with tarfile.open(inputs, "w:gz") as tar:
            tar.add(staging, arcname="vina_inputs")

        receptor, ligands, box = extract_inputs(inputs, d / "x")
        assert receptor.name == "receptor.pdbqt"
        assert [p.name for p in ligands] == ["benzene.pdbqt"], ligands
        assert box["center"] == [1.0, 2.0, 3.0], box

        # Archive assembly round-trips.
        out_dir = d / "docking_out"
        out_dir.mkdir()
        (out_dir / "benzene_out.pdbqt").write_text("MODEL 1\nENDMDL\n")
        out = d / "docking_out.tar.gz"
        make_archive(out_dir, out)
        with tarfile.open(out) as tar:
            names = set(tar.getnames())
        assert "docking_out/benzene_out.pdbqt" in names, names
    print("dock.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run AutoDock Vina docking.")
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--exhaustiveness", type=int, default=16)
    parser.add_argument("--n-poses", type=int, default=9)
    parser.add_argument(
        "--cpu", type=int, default=0, help="Vina CPU count (0 = autodetect)"
    )
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        _selftest()
        return 0
    if not (args.inputs and args.out):
        parser.error("--inputs and --out are required")

    run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
