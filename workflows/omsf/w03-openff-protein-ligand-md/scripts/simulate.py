#!/usr/bin/env python3
# Runs one replica: minimize, then NVT Langevin (300 K, 1/ps, 2 fs) with a DCD
# reporter. Uses CUDA when OpenMM can load it, else CPU with capped threads.

import argparse
import shutil
import sys
from pathlib import Path

# steps, report interval, minimizer max iterations (0 = until converged)
PROFILES = {
    "smoke": (2_500, 250, 200),  # 5 ps
    "full": (500_000, 5_000, 0),  # 1 ns
}


def pick_platform(threads: int):
    import openmm

    try:
        return openmm.Platform.getPlatformByName("CUDA"), {"Precision": "mixed"}
    except openmm.OpenMMException:
        return openmm.Platform.getPlatformByName("CPU"), {"Threads": str(threads)}


def run(slot: Path, out: Path, profile: str, threads: int) -> None:
    import openmm
    import openmm.app as app
    from openmm import unit

    steps, interval, max_iter = PROFILES[profile]
    out.mkdir(parents=True, exist_ok=True)
    for name in ("complex.pdb", "seed"):
        shutil.copy(slot / name, out / name)
    seed = int((slot / "seed").read_text())
    pdb = app.PDBFile(str(slot / "complex.pdb"))
    system = openmm.XmlSerializer.deserialize((slot / "system.xml").read_text())

    integrator = openmm.LangevinMiddleIntegrator(
        300 * unit.kelvin, 1 / unit.picosecond, 0.002 * unit.picoseconds)
    integrator.setRandomNumberSeed(seed)
    platform, props = pick_platform(threads)
    sim = app.Simulation(pdb.topology, system, integrator, platform, props)
    sim.context.setPositions(pdb.positions)
    print(f"platform {platform.getName()} {props}; {system.getNumParticles()} atoms; "
          f"seed {seed}; {steps} steps", flush=True)

    e0 = sim.context.getState(getEnergy=True).getPotentialEnergy()
    sim.minimizeEnergy(maxIterations=max_iter)
    e1 = sim.context.getState(getEnergy=True).getPotentialEnergy()
    print(f"minimized {e0} -> {e1}", flush=True)

    sim.context.setVelocitiesToTemperature(300 * unit.kelvin, seed)
    # unwrapped, so the ligand never jumps a box length between frames
    sim.reporters.append(app.DCDReporter(
        str(out / "trajectory.dcd"), interval, enforcePeriodicBox=False))
    sim.reporters.append(app.StateDataReporter(
        str(out / "log.csv"), interval, step=True, time=True, potentialEnergy=True,
        temperature=True, speed=True))
    sim.reporters.append(app.StateDataReporter(
        sys.stdout, max(interval, steps // 10), step=True, temperature=True,
        speed=True, remainingTime=True, totalSteps=steps))
    sim.step(steps)
    print(f"done: {out / 'trajectory.dcd'}", flush=True)


def selftest() -> None:
    for steps, interval, max_iter in PROFILES.values():
        assert steps % interval == 0 and steps // interval >= 10, (steps, interval)
        assert max_iter >= 0
    assert PROFILES["smoke"][0] * 0.002 == 5.0  # ps
    assert PROFILES["full"][0] * 0.002 == 1000.0
    print("selftest ok")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--profile", choices=sorted(PROFILES))
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not (a.slot and a.out and a.profile):
        sys.exit("--slot, --out and --profile are required")
    run(a.slot, a.out, a.profile, a.threads)


if __name__ == "__main__":
    main()
