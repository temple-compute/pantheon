#!/usr/bin/env python3
# Plans the RBFE network like `openfe plan-rbfe-network` (same loaders, mapper,
# scorer, network planner and solvent from openfecli's defaults), but through
# the Python API so the smoke profile can shorten sampling: the CLI settings
# YAML only takes mapper/network/partial_charge keys. Ligands come in already
# charged, so nothing is recharged here. Runs in the openfe conda env.

import argparse
import sys
from pathlib import Path


def protocol_settings(profile: str):
    from openff.units import unit
    from openfe.protocols.openmm_rfe import RelativeHybridTopologyProtocol

    s = RelativeHybridTopologyProtocol.default_settings()
    if profile == "full":
        # Protocol defaults = CLI defaults: 3 repeats, 1 ns eq, 5 ns prod,
        # 11 windows, CUDA.
        return s
    # CPU-sized: the hybrid-topology forces are slow on the OpenMM CPU
    # platform, so 4 windows, 1 ps eq / 2 ps prod and a short minimization.
    # 0.1 ps iterations give 20 samples per state; with fewer, openfe's fixed
    # 1000-sample MBAR bootstrap crawls.
    s.protocol_repeats = 1
    s.lambda_settings.lambda_windows = 4
    s.simulation_settings.n_replicas = 4  # must equal lambda_windows
    s.simulation_settings.time_per_iteration = 0.1 * unit.picosecond
    s.simulation_settings.equilibration_length = 1 * unit.picosecond
    s.simulation_settings.production_length = 2 * unit.picosecond
    s.simulation_settings.minimization_steps = 100
    s.simulation_settings.real_time_analysis_interval = None
    s.output_settings.checkpoint_interval = 1 * unit.picosecond
    s.engine_settings.compute_platform = "cpu"
    return s


def plan(ligands: Path, protein: Path, profile: str, out: Path, graphml: Path):
    from openfe.protocols.openmm_rfe import RelativeHybridTopologyProtocol
    from openfe.setup.alchemical_network_planner.relative_alchemical_network_planner import (
        RBFEAlchemicalNetworkPlanner,
    )
    from openfecli.parameters import MOL_DIR, PROTEIN, YAML_OPTIONS

    small_molecules = MOL_DIR.get(str(ligands))
    for m in small_molecules:
        if m.to_openff().partial_charges is None:
            raise SystemExit(f"{m.name} has no partial charges; run charge_ligands first")
    opts = YAML_OPTIONS.get(None)  # the CLI's defaults: kartograf, MST, NaCl water
    planner = RBFEAlchemicalNetworkPlanner(
        mappers=[opts.mapper],
        mapping_scorer=opts.scorer,
        ligand_network_planner=opts.ligand_network_planner,
        protocol=RelativeHybridTopologyProtocol(protocol_settings(profile)),
    )
    network = planner(
        ligands=small_molecules,
        solvent=opts.solvent,
        protein=PROTEIN.get(str(protein)),
        cofactors=[],
    )
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob("*.json"):  # e.g. full legs left over when re-running smoke
        stale.unlink()
    for t in network.edges:
        t.to_json(out / f"{t.name or t.key}.json")
    graphml.parent.mkdir(parents=True, exist_ok=True)
    graphml.write_text(planner._ligand_network.to_graphml())
    print(f"{len(network.edges)} legs -> {out}")


def selftest() -> None:
    from openff.units import unit
    from openfe.protocols.openmm_rfe import RelativeHybridTopologyProtocol
    from openfe.protocols.openmm_utils import settings_validation as v

    for profile in ("smoke", "full"):
        s = protocol_settings(profile)
        sim, integ = s.simulation_settings, s.integrator_settings
        # The same checks the protocol runs at quickrun time.
        mc = v.convert_steps_per_iteration(sim, integ)
        v.get_simsteps(sim.equilibration_length, integ.timestep, mc)
        v.get_simsteps(sim.production_length, integ.timestep, mc)
        v.convert_checkpoint_interval_to_iterations(
            s.output_settings.checkpoint_interval, sim.time_per_iteration
        )
        v.convert_real_time_analysis_iterations(sim)
        assert sim.n_replicas == s.lambda_settings.lambda_windows
        RelativeHybridTopologyProtocol(s)
    smoke, full = protocol_settings("smoke"), protocol_settings("full")
    assert smoke.protocol_repeats == 1 and full.protocol_repeats == 3
    assert round(smoke.simulation_settings.production_length.m_as("ps"), 6) == 2
    assert full.simulation_settings.production_length == 5 * unit.nanosecond
    assert smoke.engine_settings.compute_platform == "cpu"
    print("selftest ok")


def main() -> None:
    if "--selftest" in sys.argv:
        return selftest()
    ap = argparse.ArgumentParser()
    ap.add_argument("--ligands", type=Path, required=True)
    ap.add_argument("--protein", type=Path, required=True)
    ap.add_argument("--profile", choices=["smoke", "full"], required=True)
    ap.add_argument("--out", type=Path, required=True, help="transformations folder")
    ap.add_argument("--graphml", type=Path, required=True)
    a = ap.parse_args()
    plan(a.ligands, a.protein, a.profile, a.out, a.graphml)


if __name__ == "__main__":
    main()
