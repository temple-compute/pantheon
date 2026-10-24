#!/usr/bin/env python3
"""
Relax a structure and run NVT molecular dynamics with Meta's UMA potential.

UMA (fairchem-core) runs in its default inference mode, which is UMA Nitro
for uma-s-1p2p1 on an Ampere-or-newer CUDA GPU; anywhere else fairchem falls
back to a slower mode and says so. The checkpoint is gated on Hugging Face,
so HF_TOKEN must hold a token with access to facebook/UMA.

Usage:
    uma.py relax --structure in.xyz --task omol --steps 200 --fmax 0.05 --out relaxed.xyz
    uma.py md --structure relaxed.xyz --task omol --temperature 300 --timestep 0.5 \
        --steps 10000 --save-every 10 --traj trajectory.xyz --thermo thermo.csv \
        --summary md_summary.json
    uma.py --selftest
"""

import argparse
import csv
import json
import os
import sys
import tempfile
import time
from pathlib import Path

# Download progress bars are \r-only lines, which Horus' line reader chokes on.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

MODEL = "uma-s-1p2p1"  # the checkpoint UMA Nitro serves
FALLBACK_FORMATS = ("extxyz", "cif", "vasp", "xyz", "sdf", "proteindatabank")
THERMO_FIELDS = ["step", "time_ps", "epot_eV", "ekin_eV", "etot_eV", "temperature_K"]


def ns_per_day(steps: int, timestep_fs: float, wall_s: float) -> float:
    """Simulated nanoseconds per wall-clock day."""
    return steps * timestep_fs * 1e-6 / (wall_s / 86400) if wall_s > 0 else 0.0


def read_structure(path: Path):
    """Read any ASE format. An upload that replaces the example keeps the
    example's file name, so a wrong extension falls back to common formats."""
    from ase.io import read

    try:
        return read(path)
    except Exception as first:
        for fmt in FALLBACK_FORMATS:
            try:
                atoms = read(path, format=fmt)
            except Exception:
                continue
            if len(atoms):  # some readers return an empty structure, not an error
                return atoms
        raise first


def calculator(task: str):
    """UMA calculator for *task* on CUDA when present, in fairchem's default mode."""
    import torch
    from fairchem.core import FAIRChemCalculator, pretrained_mlip

    device = "cuda" if torch.cuda.is_available() else "cpu"
    predictor = pretrained_mlip.get_predict_unit(MODEL, device=device)
    return FAIRChemCalculator(predictor, task_name=task), predictor, device


def load(args: argparse.Namespace):
    """Read the structure, set charge/spin (omol only) and attach UMA."""
    atoms = read_structure(args.structure)
    if args.task == "omol":
        atoms.info["charge"] = int(args.charge)
        atoms.info["spin"] = int(args.spin)
    calc, predictor, device = calculator(args.task)
    atoms.calc = calc
    return atoms, predictor, device


def mode(predictor) -> str:
    """The inference mode that actually ran (valid after the first predict)."""
    from fairchem.core.units.mlip_unit.api.inference import (
        describe_inference_settings,
    )

    return describe_inference_settings(predictor.inference_settings)


def relax(args: argparse.Namespace) -> None:
    """FIRE to fmax; the cell relaxes too for periodic inorganic (omat) runs."""
    from ase.filters import FrechetCellFilter
    from ase.optimize import FIRE

    atoms, predictor, device = load(args)
    e0 = atoms.get_potential_energy()
    print(f"UMA {MODEL} task={args.task} mode={mode(predictor)} device={device} atoms={len(atoms)}")
    if args.steps > 0:
        target = FrechetCellFilter(atoms) if args.task == "omat" and all(atoms.pbc) else atoms
        converged = FIRE(target, logfile="-").run(fmax=args.fmax, steps=int(args.steps))
        print(f"relax: E {e0:.4f} -> {atoms.get_potential_energy():.4f} eV, converged={converged}")
    else:
        print("relax: skipped (steps = 0)")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    atoms.write(args.out, format="extxyz")  # named .xyz: Mol* reads it, ASE keeps cell/pbc


def md(args: argparse.Namespace) -> None:
    """Langevin NVT; writes the trajectory, a thermo table and a speed summary."""
    import numpy as np
    from ase import units
    from ase.md.langevin import Langevin
    from ase.md.velocitydistribution import MaxwellBoltzmannDistribution

    atoms, predictor, device = load(args)
    # Warm-up predict: Nitro builds its CUDA graphs here, so the timed loop
    # measures steady-state speed.
    atoms.get_forces()
    ran = mode(predictor)
    print(f"UMA {MODEL} task={args.task} mode={ran} device={device} atoms={len(atoms)}")

    rng = np.random.default_rng(int(args.seed))
    MaxwellBoltzmannDistribution(atoms, temperature_K=args.temperature, rng=rng)
    dyn = Langevin(
        atoms,
        timestep=args.timestep * units.fs,
        temperature_K=args.temperature,
        friction=args.friction / units.fs,
        rng=rng,
    )

    for p in (args.traj, args.thermo, args.summary):
        p.parent.mkdir(parents=True, exist_ok=True)
    args.traj.unlink(missing_ok=True)
    every = max(1, int(args.save_every))
    with args.thermo.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(THERMO_FIELDS)

        def record() -> None:
            epot, ekin = atoms.get_potential_energy(), atoms.get_kinetic_energy()
            step = dyn.nsteps
            writer.writerow([
                step, f"{step * args.timestep / 1000:.4f}", f"{epot:.5f}",
                f"{ekin:.5f}", f"{epot + ekin:.5f}", f"{atoms.get_temperature():.2f}",
            ])
            atoms.write(args.traj, format="extxyz", append=True)
            if step % (every * 10) == 0:
                print(f"step {step}: T={atoms.get_temperature():.1f} K Etot={epot + ekin:.4f} eV", flush=True)

        dyn.attach(record, interval=every)
        t0 = time.perf_counter()
        dyn.run(int(args.steps))
        wall = time.perf_counter() - t0

    import torch

    summary = {
        "model": MODEL,
        "task": args.task,
        "inference_mode": ran,
        "device": torch.cuda.get_device_name() if device == "cuda" else "cpu",
        "atoms": len(atoms),
        "steps": int(args.steps),
        "timestep_fs": args.timestep,
        "temperature_K": args.temperature,
        "simulated_ps": int(args.steps) * args.timestep / 1000,
        "wall_s": round(wall, 2),
        "ns_per_day": round(ns_per_day(int(args.steps), args.timestep, wall), 4),
    }
    args.summary.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))


def _selftest() -> None:
    """The pure helpers, without fairchem or a GPU."""
    assert abs(ns_per_day(1000, 1.0, 86.4) - 1.0) < 1e-9  # 1 ps in 86.4 s = 1 ns/day
    assert ns_per_day(10, 0.5, 0) == 0.0
    try:
        import ase  # noqa: F401
    except ImportError:
        print("uma.py selftest: OK (ase not installed, read_structure not checked)")
        return
    from ase.build import molecule

    with tempfile.TemporaryDirectory() as tmp:
        wrong = Path(tmp) / "structure.extxyz"  # a CIF under the example's name
        for fmt in ("cif", "vasp", "proteindatabank"):
            molecule("H2O", cell=[5, 5, 5], pbc=True).write(wrong, format=fmt)
            assert read_structure(wrong).get_chemical_formula() == "H2O", fmt
    print("uma.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    if argv is None and sys.argv[1:] == ["--selftest"]:
        _selftest()
        return 0
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("relax", "md"):
        p = sub.add_parser(name)
        p.add_argument("--structure", type=Path, required=True)
        p.add_argument("--task", required=True)
        p.add_argument("--charge", type=float, default=0)
        p.add_argument("--spin", type=float, default=1)
        p.add_argument("--steps", type=float, required=True)
    r = sub.choices["relax"]
    r.add_argument("--fmax", type=float, default=0.05)
    r.add_argument("--out", type=Path, required=True)
    m = sub.choices["md"]
    m.add_argument("--temperature", type=float, default=300)
    m.add_argument("--timestep", type=float, default=0.5, help="fs")
    m.add_argument("--friction", type=float, default=0.01, help="1/fs")
    m.add_argument("--save-every", type=float, default=10)
    m.add_argument("--seed", type=float, default=0)
    m.add_argument("--traj", type=Path, required=True)
    m.add_argument("--thermo", type=Path, required=True)
    m.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args(argv)
    {"relax": relax, "md": md}[args.cmd](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
