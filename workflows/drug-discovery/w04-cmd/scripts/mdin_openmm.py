"""Run one AMBER .mdin step on OpenMM, with pmemd's command line and outputs.

The `openmm` md_engine: equilibrate.sh and production.sh call this instead of
pmemd/pmemd.cuda when the slot's engine.txt says so, with the same flags
(-O -i -o -p -c -r -inf -ref -x). It runs the &cntrl keys prepare_replicas.py
renders (templates/min.in, md.in) and writes what those scripts, the live
monitor and the report read:

    -r    AMBER ASCII restart (coordinates, velocities, box)
    -x    AMBER NetCDF trajectory (first ntwprt atoms when ntwprt > 0)
    -o    mdout with pmemd-style NSTEP / Etot / Density records, closed by
          the "5.  TIMINGS" section the done-step checks look for
    -inf  mdinfo: last record and ns/day

Supported keys: imin, maxcyc, nstlim, dt, irest, ntx, ig, tempi, temp0, ntc,
cut, ntt=3 (gamma_ln), ntb, ntp, barostat=2 (pres0), ntr (restraintmask,
restraint_wt), ntwx, ntpr, ntwr, ntwprt, nscm, iwrap. Anything else in the
namelist is ignored with a note; ntt other than 3 or barostat other than 2
stops the step, since the result would not be what the mdin asked for.

Platform: CUDA, then OpenCL, then CPU (OPENMM_PLATFORM overrides).
`python mdin_openmm.py --selftest` checks the namelist parser and the
restart round trip.
"""

import argparse
import math
import os
import re
import sys
import time
from pathlib import Path

# AMBER's time unit is 1/20.455 ps; restart velocities are stored in A per it.
AMBER_VEL = 20.455
KCAL = 4.184  # kJ per kcal
SUPPORTED = {
    "imin", "maxcyc", "ncyc", "nstlim", "dt", "irest", "ntx", "ig", "tempi",
    "temp0", "ntc", "ntf", "tol", "cut", "ntt", "gamma_ln", "ntb", "ntp",
    "barostat", "pres0", "ntr", "restraintmask", "restraint_wt", "ntwx",
    "ntwe", "ntwr", "ntpr", "ntwprt", "nscm", "iwrap", "ioutfm", "ntxo",
}


def parse_mdin(text: str) -> tuple[str, dict]:
    """Title line and the &cntrl namelist as {lowercase key: int|float|str}."""
    title = text.splitlines()[0].strip() if text.strip() else ""
    m = re.search(r"&cntrl(.*?)(?:^\s*/\s*$|&end)", text, re.S | re.M | re.I)
    if not m:
        raise SystemExit("mdin has no &cntrl namelist")
    out = {}
    for key, raw in re.findall(r"(\w+)\s*=\s*(\"[^\"]*\"|'[^']*'|[^,\s]+)", m.group(1)):
        raw = raw.strip()
        if raw[0] in "\"'":
            val = raw[1:-1]
        else:
            try:
                val = int(raw)
            except ValueError:
                val = float(raw)
        out[key.lower()] = val
    return title, out


def platform():
    import openmm

    names = [os.environ["OPENMM_PLATFORM"]] if os.environ.get("OPENMM_PLATFORM") else ["CUDA", "OpenCL", "CPU"]
    for name in names:
        try:
            p = openmm.Platform.getPlatformByName(name)
        except Exception:
            continue
        return p
    raise SystemExit(f"no OpenMM platform among {names}")


def write_restart(path: Path, title: str, pos_A, vel_A_ps, box, time_ps: float) -> None:
    """AMBER ASCII restart (ntxo=1), the format pmemd writes and AmberInpcrdFile reads."""
    n = len(pos_A)
    lines = [title[:80], f"{n:6d}{time_ps:15.7e}"]
    def rows(values):
        flat = [c for xyz in values for c in xyz]
        return ["".join(f"{v:12.7f}" for v in flat[i:i + 6]) for i in range(0, len(flat), 6)]
    lines += rows(pos_A)
    if vel_A_ps is not None:
        lines += rows([[v / AMBER_VEL for v in xyz] for xyz in vel_A_ps])
    if box is not None:
        lines.append("".join(f"{v:12.7f}" for v in box))
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text("\n".join(lines) + "\n")
    tmp.replace(path)


def box_lengths_angles(vectors_nm):
    a, b, c = ([v * 10 for v in vec] for vec in vectors_nm)
    norm = lambda u: math.sqrt(sum(x * x for x in u))
    ang = lambda u, w: math.degrees(math.acos(sum(x * y for x, y in zip(u, w)) / (norm(u) * norm(w))))
    return [norm(a), norm(b), norm(c), ang(b, c), ang(a, c), ang(a, b)]


def run(args) -> None:
    import openmm
    from openmm import app, unit
    from parmed.amber import AmberMask, AmberParm, NetCDFTraj

    title, c = parse_mdin(Path(args.i).read_text())
    unknown = sorted(set(c) - SUPPORTED)
    if unknown:
        print(f"note: ignoring mdin keys OpenMM does not need here: {', '.join(unknown)}")
    if c.get("imin", 0) == 0 and c.get("ntt", 3) != 3:
        raise SystemExit(f"ntt={c['ntt']}: only ntt=3 (Langevin) is supported")
    if c.get("ntp", 0) and c.get("barostat", 2) != 2:
        raise SystemExit(f"barostat={c['barostat']}: only barostat=2 (Monte Carlo) is supported")

    prmtop = app.AmberPrmtopFile(args.p)
    crd = app.AmberInpcrdFile(args.c)
    periodic = c.get("ntb", 1) > 0
    system = prmtop.createSystem(
        nonbondedMethod=app.PME if periodic else app.CutoffNonPeriodic,
        nonbondedCutoff=c.get("cut", 8.0) * unit.angstrom,
        constraints=app.HBonds if c.get("ntc", 1) == 2 else None,
        rigidWater=True,
        removeCMMotion=c.get("nscm", 1000) != 0,
    )
    temp0 = c.get("temp0", 300.0) * unit.kelvin

    if c.get("ntr", 0) == 1 and c.get("restraint_wt", 0) > 0:
        parm = AmberParm(args.p)
        atoms = [i for i, sel in enumerate(AmberMask(parm, c["restraintmask"]).Selection()) if sel]
        ref = app.AmberInpcrdFile(args.ref or args.c).getPositions(asNumpy=True).value_in_unit(unit.nanometer)
        k = c["restraint_wt"] * KCAL * 100  # kcal/mol/A^2 -> kJ/mol/nm^2
        force = openmm.CustomExternalForce("k*periodicdistance(x, y, z, x0, y0, z0)^2" if periodic
                                           else "k*((x-x0)^2+(y-y0)^2+(z-z0)^2)")
        force.addGlobalParameter("k", k)
        for name in ("x0", "y0", "z0"):
            force.addPerParticleParameter(name)
        for i in atoms:
            force.addParticle(i, list(ref[i]))
        system.addForce(force)
        print(f"restraint {c['restraint_wt']} kcal/mol/A^2 on {len(atoms)} atoms ({c['restraintmask']})")
    if c.get("ntp", 0) and periodic:
        system.addForce(openmm.MonteCarloBarostat(c.get("pres0", 1.0) * unit.bar, temp0))

    dt = c.get("dt", 0.002) * unit.picosecond
    integrator = openmm.LangevinMiddleIntegrator(temp0, c.get("gamma_ln", 1.0) / unit.picosecond, dt)
    seed = c.get("ig", -1)
    integrator.setRandomNumberSeed(seed if seed > 0 else 0)  # 0 = OpenMM picks one, like ig=-1
    plat = platform()
    sim = app.Simulation(prmtop.topology, system, integrator, plat)
    sim.context.setPositions(crd.positions)
    if crd.boxVectors is not None:
        sim.context.setPeriodicBoxVectors(*crd.boxVectors)
    print(f"OpenMM {openmm.__version__} on {plat.getName()}: {prmtop.topology.getNumAtoms()} atoms, {title}")

    natom = system.getNumParticles()
    masses = [system.getParticleMass(i).value_in_unit(unit.dalton) for i in range(natom)]
    dof = 3 * natom - system.getNumConstraints() - (3 if c.get("nscm", 1000) != 0 else 0)
    out = open(args.o, "w")
    out.write(f"\n          -------------------------------------------------------\n"
              f"          OpenMM {openmm.__version__} ({plat.getName()}) running {Path(args.i).name}\n"
              f"          -------------------------------------------------------\n\n{title}\n\n")
    t0 = time.time()
    wrap = c.get("iwrap", 0) == 1

    def state(**kw):
        return sim.context.getState(getEnergy=True, getPositions=True, enforcePeriodicBox=wrap, **kw)

    def save_restart(st, time_ps, with_vel=True):
        pos = st.getPositions(asNumpy=True).value_in_unit(unit.angstrom)
        vel = st.getVelocities(asNumpy=True).value_in_unit(unit.angstrom / unit.picosecond) if with_vel else None
        box = box_lengths_angles(st.getPeriodicBoxVectors().value_in_unit(unit.nanometer)) if periodic else None
        write_restart(Path(args.r), title, pos.tolist(), None if vel is None else vel.tolist(), box, time_ps)

    if c.get("imin", 0) == 1:
        e0 = state().getPotentialEnergy().value_in_unit(unit.kilocalorie_per_mole)
        sim.minimizeEnergy(maxIterations=int(c.get("maxcyc", 1000)))
        st = state()
        e1 = st.getPotentialEnergy().value_in_unit(unit.kilocalorie_per_mole)
        out.write("   NSTEP       ENERGY          RMS            GMAX         NAME    NUMBER\n"
                  f"      1  {e0:13.4E}\n"
                  f"{int(c.get('maxcyc', 1000)):8d}  {e1:13.4E}\n\n"
                  "                    FINAL RESULTS\n\n"
                  f"   NSTEP       ENERGY\n{int(c.get('maxcyc', 1000)):8d}  {e1:13.4E}\n")
        save_restart(st, 0.0, with_vel=False)
        print(f"minimized: {e0:.1f} -> {e1:.1f} kcal/mol")
    else:
        if c.get("ntx", 1) == 5 and c.get("irest", 0) == 1 and crd.velocities is not None:
            sim.context.setVelocities(crd.velocities)
        else:
            sim.context.setVelocitiesToTemperature(c.get("tempi", c.get("temp0", 300.0)) * unit.kelvin,
                                                   seed if seed > 0 else 0)
        nstlim = int(c.get("nstlim", 0))
        ntpr = int(c.get("ntpr", 0)) or nstlim
        ntwx = int(c.get("ntwx", 0))
        ntwr = int(c.get("ntwr", 0)) or nstlim
        ntwprt = int(c.get("ntwprt", 0)) or natom
        dt_ps = dt.value_in_unit(unit.picosecond)
        traj = NetCDFTraj.open_new(args.x, ntwprt, box=periodic, crds=True) if (ntwx and args.x) else None
        info = Path(args.inf) if args.inf else None
        step = 0
        stops = sorted({s for every in (ntpr, ntwx, ntwr) if every for s in range(every, nstlim + 1, every)} | {nstlim})
        for stop in stops:
            sim.step(stop - step)
            step = stop
            need_vel = stop % ntwr == 0 or stop == nstlim
            st = state(getVelocities=need_vel)
            t_ps = step * dt_ps
            if stop % ntpr == 0 or stop == nstlim:
                ke = st.getKineticEnergy().value_in_unit(unit.kilocalorie_per_mole)
                pe = st.getPotentialEnergy().value_in_unit(unit.kilocalorie_per_mole)
                temp = 2 * ke * 4184 / (dof * 8.314462618) if dof > 0 else 0.0
                vec = st.getPeriodicBoxVectors().value_in_unit(unit.nanometer)
                vol_A3 = (vec[0][0] * vec[1][1] * vec[2][2]) * 1000 if periodic else 0.0
                dens = sum(masses) * 1.66053906660 / vol_A3 if vol_A3 else 0.0
                rec = (f" NSTEP = {step:8d}   TIME(PS) = {t_ps:11.3f}  TEMP(K) = {temp:8.2f}  PRESS =     0.0\n"
                       f" Etot   = {ke + pe:14.4f}  EKtot   = {ke:14.4f}  EPtot      = {pe:14.4f}\n"
                       f" Density    = {dens:11.4f}\n"
                       " ------------------------------------------------------------------------------\n\n")
                out.write(rec)
                out.flush()
                if info:
                    elapsed = time.time() - t0
                    nsday = t_ps / 1000 / (elapsed / 86400) if elapsed > 0 else 0.0
                    info.write_text(rec + f" ns/day = {nsday:.2f}   steps {step}/{nstlim}\n")
            if traj is not None and ntwx and stop % ntwx == 0:
                traj.add_coordinates(st.getPositions(asNumpy=True).value_in_unit(unit.angstrom)[:ntwprt])
                if periodic:
                    traj.add_box(box_lengths_angles(st.getPeriodicBoxVectors().value_in_unit(unit.nanometer)))
                traj.add_time(t_ps)
            if need_vel:
                save_restart(st, t_ps)
        if traj is not None:
            traj.close()
    elapsed = time.time() - t0
    out.write(f"\n--------------------------------------------------------------------------------\n"
              f"   5.  TIMINGS\n--------------------------------------------------------------------------------\n"
              f"|  Total wall time: {elapsed:10.1f} seconds\n")
    out.close()


def selftest() -> None:
    import tempfile

    title, c = parse_mdin("""2_heat: heat
 &cntrl
  imin = 0, nstlim = 500, dt = 0.002,
  irest = 0, ntx = 1, ig = -1,
  tempi = 100, temp0 = 300,
  ntc = 2, ntf = 2, tol = 0.00001,
  cut = 9, ntb = 2, ntp = 1, barostat = 2, pres0 = 1,
  ntr = 1, restraintmask = ":1-129&!@H=", restraint_wt = 100,
  ioutfm = 1, ntxo = 1,
 /
""")
    assert title == "2_heat: heat"
    assert c["nstlim"] == 500 and c["dt"] == 0.002 and c["ig"] == -1 and c["tempi"] == 100
    assert c["restraintmask"] == ":1-129&!@H=" and c["restraint_wt"] == 100 and c["barostat"] == 2
    try:
        parse_mdin("title\n no namelist\n")
        raise AssertionError("missing &cntrl must fail")
    except SystemExit:
        pass
    # restart round trip through OpenMM's own reader, velocities included
    from openmm import app, unit
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "x.rst"
        write_restart(p, "t", [[1.0, 2.0, 3.0], [4.5, 5.5, 6.5]], [[10.0, -20.0, 30.0], [0.0, 1.0, 2.0]],
                      [30.0, 31.0, 32.0, 90.0, 90.0, 90.0], 12.5)
        r = app.AmberInpcrdFile(str(p))
        pos = r.getPositions(asNumpy=True).value_in_unit(unit.angstrom)
        vel = r.getVelocities(asNumpy=True).value_in_unit(unit.angstrom / unit.picosecond)
        assert abs(pos[1][2] - 6.5) < 1e-6 and abs(vel[0][1] + 20.0) < 1e-3, (pos, vel)
        assert abs(r.getBoxVectors(asNumpy=True)[2][2].value_in_unit(unit.angstrom) - 32.0) < 1e-6
    print("selftest ok")


def main() -> None:
    if "--selftest" in sys.argv:
        return selftest()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-O", action="store_true", help="overwrite outputs (always; pmemd compatibility)")
    for flag in ("i", "o", "p", "c", "r"):
        ap.add_argument(f"-{flag}", required=True)
    for flag in ("inf", "ref", "x"):
        ap.add_argument(f"-{flag}")
    run(ap.parse_args())


if __name__ == "__main__":
    main()
