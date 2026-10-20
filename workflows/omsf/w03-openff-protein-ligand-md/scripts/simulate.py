#!/usr/bin/env python3
# Runs one replica: minimize until converged, then NVT Langevin (1/ps friction;
# temperature, timestep and length from the workflow variables) with a DCD
# reporter. Uses CUDA, then OpenCL, then CPU with capped threads, falling back
# when a platform cannot create a context. REQUIRE_GPU=1 (set by the _gpu
# target) makes a missing GPU an error instead of a CPU fallback.

import argparse
import os
import shutil
import sys
from pathlib import Path


def whole(name: str, value: str, lo: int, hi: int) -> int:
    """value as an int in lo..hi (horus may render 2500 as 2500.0)."""
    try:
        n = float(value)
    except ValueError:
        n = float("nan")
    if not (n.is_integer() and lo <= n <= hi):
        sys.exit(f"{name} must be a whole number between {lo} and {hi}, got {value!r}")
    return int(n)


def between(name: str, value: float, lo: float, hi: float) -> float:
    if not lo <= value <= hi:
        sys.exit(f"{name} must be between {lo} and {hi}, got {value}")
    return value


def candidates(threads: int, require_gpu: bool) -> list[tuple[str, dict]]:
    gpu = [("CUDA", {"Precision": "mixed"}), ("OpenCL", {"Precision": "mixed"})]
    return gpu if require_gpu else gpu + [("CPU", {"Threads": str(threads)})]


def make_simulation(topology, system, integrator, threads: int, require_gpu: bool):
    """First platform that can create a context; a plugin that loads can still fail here."""
    import openmm
    import openmm.app as app

    errors = []
    for name, props in candidates(threads, require_gpu):
        try:
            sim = app.Simulation(topology, system, integrator,
                                 openmm.Platform.getPlatformByName(name), props)
            return sim, name, props
        except openmm.OpenMMException as e:
            # the integrator stays bound to a failed context; retry with a copy
            integrator = openmm.XmlSerializer.clone(integrator)
            errors.append(f"{name}: {e}")
            print(f"platform {name} unavailable: {e}", flush=True)
    sys.exit("no usable OpenMM platform" + (" (REQUIRE_GPU=1, CPU not allowed)"
             if require_gpu else "") + ":\n" + "\n".join(errors))


def run(slot: Path, out: Path, steps: int, interval: int, temperature: float,
        timestep_fs: float, threads: int) -> None:
    import openmm
    import openmm.app as app
    from openmm import unit

    out.mkdir(parents=True, exist_ok=True)
    for name in ("complex.pdb", "seed"):
        shutil.copy(slot / name, out / name)
    seed = int((slot / "seed").read_text())
    pdb = app.PDBFile(str(slot / "complex.pdb"))
    system = openmm.XmlSerializer.deserialize((slot / "system.xml").read_text())

    integrator = openmm.LangevinMiddleIntegrator(
        temperature * unit.kelvin, 1 / unit.picosecond, timestep_fs * unit.femtoseconds)
    integrator.setRandomNumberSeed(seed)
    sim, platform, props = make_simulation(
        pdb.topology, system, integrator, threads, os.environ.get("REQUIRE_GPU") == "1")
    sim.context.setPositions(pdb.positions)
    print(f"platform {platform} {props}; {system.getNumParticles()} atoms; "
          f"seed {seed}; {steps} steps of {timestep_fs} fs at {temperature} K", flush=True)

    e0 = sim.context.getState(getEnergy=True).getPotentialEnergy()
    sim.minimizeEnergy()  # until converged
    e1 = sim.context.getState(getEnergy=True).getPotentialEnergy()
    print(f"minimized {e0} -> {e1}", flush=True)

    sim.context.setVelocitiesToTemperature(temperature * unit.kelvin, seed)
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
    assert whole("n_steps", "500000", 1, 10**9) == 500_000
    assert whole("n_steps", "2500.0", 1, 10**9) == 2_500
    assert between("timestep_fs", 2.0, 0.1, 4.0) == 2.0
    for check in (lambda: whole("n_steps", "0", 1, 10), lambda: whole("n_steps", "1.5", 1, 10),
                  lambda: whole("n_steps", "x", 1, 10),
                  lambda: between("temperature_k", 0.0, 1.0, 1000.0)):
        try:
            check()
            raise AssertionError("out-of-range value accepted")
        except SystemExit as e:
            assert "must be" in str(e)
    assert [n for n, _ in candidates(2, False)] == ["CUDA", "OpenCL", "CPU"]
    assert [n for n, _ in candidates(2, True)] == ["CUDA", "OpenCL"]
    print("selftest ok")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--steps")
    ap.add_argument("--report-interval")
    ap.add_argument("--temperature", type=float, help="K")
    ap.add_argument("--timestep-fs", type=float)
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not (a.slot and a.out and a.steps and a.report_interval
            and a.temperature is not None and a.timestep_fs is not None):
        sys.exit("--slot, --out, --steps, --report-interval, --temperature and "
                 "--timestep-fs are required")
    steps = whole("n_steps", a.steps, 1, 10**9)
    interval = whole("report_interval_steps", a.report_interval, 1, steps)
    temperature = between("temperature_k", a.temperature, 1.0, 1000.0)
    # bonds to H are constrained but masses are not repartitioned
    timestep = between("timestep_fs", a.timestep_fs, 0.1, 4.0)
    run(a.slot, a.out, steps, interval, temperature, timestep, a.threads)


if __name__ == "__main__":
    main()
