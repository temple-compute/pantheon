#!/usr/bin/env python3
# Plans the RBFE network like `openfe plan-rbfe-network` (same loaders, mapper,
# scorer, network planner and solvent from openfecli's defaults), but through
# the Python API so the protocol's sampling settings can be set from the
# workflow variables: the CLI settings YAML only takes mapper/network/
# partial_charge keys. Ligands come in already charged, so nothing is
# recharged here. Runs in the openfe conda env.

import argparse
import sys
from pathlib import Path

PLATFORMS = ("cuda", "opencl", "cpu")

# Upstream RelativeHybridTopologyProtocol defaults (openfe 1.13.0), which are
# also the `openfe plan-rbfe-network` defaults. The workflow variables carry
# the same values; the selftest checks that they still match openfe.
DEFAULTS = dict(
    n_repeats=3,
    lambda_windows=11,
    equilibration_ns=1.0,
    production_ns=5.0,
    time_per_iteration_ps=2.5,
    minimization_steps=5000,
    real_time_analysis_ps=250.0,
    checkpoint_interval_ns=1.0,
    compute_platform="cuda",
)


def _int(name: str, text: str, lo: int) -> int:
    try:
        v = int(text)
    except ValueError:
        raise SystemExit(f"{name} must be a whole number, got {text!r}") from None
    if v < lo:
        raise SystemExit(f"{name} must be >= {lo}, got {v}")
    return v


def _pos(name: str, text: str, allow_zero: bool = False) -> float:
    try:
        v = float(text)
    except ValueError:
        raise SystemExit(f"{name} must be a number, got {text!r}") from None
    if not (v > 0 or (allow_zero and v == 0)) or v != v or v == float("inf"):
        raise SystemExit(f"{name} must be {'>= 0' if allow_zero else '> 0'}, got {text}")
    return v


def validate(**raw: str) -> dict:
    """Parse and range-check the workflow variables (all passed as text)."""
    v = dict(
        n_repeats=_int("n_repeats", raw["n_repeats"], 1),
        lambda_windows=_int("lambda_windows", raw["lambda_windows"], 2),
        equilibration_ns=_pos("equilibration_ns", raw["equilibration_ns"]),
        production_ns=_pos("production_ns", raw["production_ns"]),
        time_per_iteration_ps=_pos("time_per_iteration_ps", raw["time_per_iteration_ps"]),
        minimization_steps=_int("minimization_steps", raw["minimization_steps"], 0),
        real_time_analysis_ps=_pos(
            "real_time_analysis_ps", raw["real_time_analysis_ps"], allow_zero=True
        ),
        checkpoint_interval_ns=_pos("checkpoint_interval_ns", raw["checkpoint_interval_ns"]),
        compute_platform=raw["compute_platform"].strip().lower(),
    )
    if v["compute_platform"] not in PLATFORMS:
        raise SystemExit(
            f"compute_platform must be one of {', '.join(PLATFORMS)}, "
            f"got {raw['compute_platform']!r}"
        )
    return v


def protocol_settings(v: dict):
    from openff.units import unit
    from openfe.protocols.openmm_rfe import RelativeHybridTopologyProtocol
    from openfe.protocols.openmm_utils import settings_validation as sv

    s = RelativeHybridTopologyProtocol.default_settings()
    s.protocol_repeats = v["n_repeats"]
    s.lambda_settings.lambda_windows = v["lambda_windows"]
    s.simulation_settings.n_replicas = v["lambda_windows"]  # must equal lambda_windows
    s.simulation_settings.time_per_iteration = v["time_per_iteration_ps"] * unit.picosecond
    s.simulation_settings.equilibration_length = v["equilibration_ns"] * unit.nanosecond
    s.simulation_settings.production_length = v["production_ns"] * unit.nanosecond
    s.simulation_settings.minimization_steps = v["minimization_steps"]
    # 0 turns real-time analysis off (openfe's None).
    rta = v["real_time_analysis_ps"]
    s.simulation_settings.real_time_analysis_interval = rta * unit.picosecond if rta else None
    s.output_settings.checkpoint_interval = v["checkpoint_interval_ns"] * unit.nanosecond
    s.engine_settings.compute_platform = v["compute_platform"]

    # The same divisibility checks the protocol runs at quickrun time, so a
    # bad combination fails here instead of after hours of setup.
    sim, integ = s.simulation_settings, s.integrator_settings
    try:
        mc = sv.convert_steps_per_iteration(sim, integ)
        sv.get_simsteps(sim.equilibration_length, integ.timestep, mc)
        sv.get_simsteps(sim.production_length, integ.timestep, mc)
        sv.convert_checkpoint_interval_to_iterations(
            s.output_settings.checkpoint_interval, sim.time_per_iteration
        )
        sv.convert_real_time_analysis_iterations(sim)
    except ValueError as e:
        raise SystemExit(f"invalid sampling settings: {e}") from None
    return s


def plan(ligands: Path, protein: Path, settings, out: Path, graphml: Path):
    from openfe.protocols.openmm_rfe import RelativeHybridTopologyProtocol
    from openfe.setup.alchemical_network_planner.relative_alchemical_network_planner import (
        RBFEAlchemicalNetworkPlanner,
    )
    from openfecli.parameters import MOL_DIR, PROTEIN, YAML_OPTIONS

    small_molecules = MOL_DIR.get(str(ligands))
    if len(small_molecules) < 2:
        raise SystemExit(f"need at least 2 ligands, {ligands} has {len(small_molecules)}")
    for m in small_molecules:
        if m.to_openff().partial_charges is None:
            raise SystemExit(f"{m.name} has no partial charges; run charge_ligands first")
    opts = YAML_OPTIONS.get(None)  # the CLI's defaults: kartograf, MST, NaCl water
    planner = RBFEAlchemicalNetworkPlanner(
        mappers=[opts.mapper],
        mapping_scorer=opts.scorer,
        ligand_network_planner=opts.ligand_network_planner,
        protocol=RelativeHybridTopologyProtocol(settings),
    )
    network = planner(
        ligands=small_molecules,
        solvent=opts.solvent,
        protein=PROTEIN.get(str(protein)),
        cofactors=[],
    )
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob("*.json"):  # legs left over from a different network
        stale.unlink()
    for t in network.edges:
        t.to_json(out / f"{t.name or t.key}.json")
    graphml.parent.mkdir(parents=True, exist_ok=True)
    graphml.write_text(planner._ligand_network.to_graphml())
    # As plan-rbfe-network does; not next to the legs, which the map runs over.
    network.to_json(graphml.parent / "alchemicalNetwork.json")
    print(f"{len(network.edges)} legs -> {out}")


def selftest() -> None:
    """Unit test of the variable parsing and the settings mapping."""
    from openfe.protocols.openmm_rfe import RelativeHybridTopologyProtocol

    text = {k: str(v) for k, v in DEFAULTS.items()}
    s = protocol_settings(validate(**text))
    up = RelativeHybridTopologyProtocol.default_settings()
    # The defaults reproduce the upstream protocol settings exactly.
    assert s == up, "DEFAULTS no longer match openfe's protocol defaults"

    small = dict(text, n_repeats="1", lambda_windows="4", equilibration_ns="0.001",
                 production_ns="0.002", time_per_iteration_ps="0.1",
                 minimization_steps="100", real_time_analysis_ps="0",
                 checkpoint_interval_ns="0.001", compute_platform="CPU")
    s = protocol_settings(validate(**small))
    assert s.protocol_repeats == 1 and s.simulation_settings.n_replicas == 4
    assert s.simulation_settings.real_time_analysis_interval is None
    assert s.engine_settings.compute_platform == "cpu"
    RelativeHybridTopologyProtocol(s)

    for bad in (dict(n_repeats="0"), dict(n_repeats="3.0"), dict(lambda_windows="1"),
                dict(production_ns="-1"), dict(production_ns="nan"),
                dict(compute_platform="metal"), dict(minimization_steps="-5"),
                dict(time_per_iteration_ps="0.3")):  # 0.3 ps does not divide 1 ns
        try:
            protocol_settings(validate(**dict(text, **bad)))
        except SystemExit:
            continue
        raise AssertionError(f"accepted {bad}")
    print("selftest ok")


def main() -> None:
    if "--selftest" in sys.argv:
        return selftest()
    ap = argparse.ArgumentParser()
    ap.add_argument("--ligands", type=Path, required=True)
    ap.add_argument("--protein", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True, help="transformations folder")
    ap.add_argument("--graphml", type=Path, required=True)
    for k in DEFAULTS:
        ap.add_argument(f"--{k.replace('_', '-')}", dest=k, required=True)
    a = vars(ap.parse_args())
    paths = {k: a.pop(k) for k in ("ligands", "protein", "out", "graphml")}
    settings = protocol_settings(validate(**a))
    plan(paths["ligands"], paths["protein"], settings, paths["out"], paths["graphml"])


if __name__ == "__main__":
    main()
