# W-09 · AMBER Protein MD Setup

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

This workflow runs a complete molecular dynamics setup for hen egg-white lysozyme (PDB: 1AKI) using the **AMBER** package (via AmberTools/sander/cpptraj), mirroring the GROMACS MD-setup workflow but with the AMBER toolchain end to end. Starting from the raw PDB file, it prepares the structure for AMBER, builds a LEaP topology, minimizes hydrogens and then the whole system in vacuo, solvates and neutralizes the system, runs a further minimization, heats it from 0 to 300 K, equilibrates under NVT and NPT, and finishes with a free production MD simulation followed by trajectory analysis (RMSd, radius of gyration, imaging). Horus provisions the biobb conda environment (biobb_io, biobb_structure_utils, biobb_chemistry, biobb_analysis) automatically for pure-Python tasks and routes AMBER-specific tasks to a Docker container — swapping any stage to a remote cluster is a one-line `target:` change.

## Pipeline

```
fetch_pdb              Download 1AKI structure from PDB
   │
pdb4amber              Prepare PDB for AMBER (pdb4amber)
   │
gen_top                Create protein system topology (leap)
   │
sander_h_min ──► process_h_min   Minimize hydrogens in vacuo (sander)
   │
sander_n_min ──► process_n_min   Minimize system in vacuo (sander)
   │
amber_to_pdb            Convert minimized structure to PDB (ambpdb)
   │
leap_solvate             Create solvent box and solvate system (leap)
   │
leap_add_ions             Neutralize and add ions (leap)
   │
sander_min ──► process_min       Energy minimize the solvated system (sander)
   │
sander_heat ──► process_heat     Heat the system 0 → 300 K (sander)
   │
sander_nvt ──► process_nvt       NVT equilibration (sander)
   │
sander_npt ──► process_npt       NPT equilibration (sander)
   │
sander_free              Free production MD simulation (sander)
   │
cpptraj_rms_first / cpptraj_rms_exp / cpptraj_rgyr   RMSd and radius of gyration analysis (cpptraj)
   │
cpptraj_image            Image trajectory and strip solvent (cpptraj)
```

## Prerequisites

- **uv** (recommended) or pip — to install horus-runtime
- **micromamba**, **mamba**, or **conda** — the workflow executor builds a shared conda environment from `conda_env.yaml` for pure-Python biobb tasks
- **Docker** — required for AMBER-specific tasks on macOS ARM64; the `quay.io/biocontainers/biobb_amber` image is pulled automatically on first run

## Quick Start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# From the workflow directory, install horus-runtime
cd workflows/bioexcel_building_blocks/w09-amber-protein-md-setup
uv sync
# or: pip install horus-runtime horus-environments

# Run the workflow
uv run horus run workflow.yaml
```

The first run builds the conda environment (this takes a few minutes). Subsequent runs reuse the cached environment at `../.horus_conda_env`.

## Inputs / Outputs

This workflow has no file inputs — it fetches 1AKI from the RCSB PDB automatically.

**Outputs** (all under `results/`):
- `1aki.pdb`, `structure.pdb4amber.pdb` — fetched and AMBER-prepared structures
- `structure.leap.pdb`, `structure.leap.top`, `structure.leap.crd` — protein system topology
- `sander.h_min.*`, `sander.n_min.*` — in-vacuo minimization outputs and energy traces
- `structure.ambpdb.pdb` — minimized structure converted to PDB
- `structure.solv.*`, `structure.ions.*` — solvated and neutralized system (topology/coords)
- `sander.min.*`, `sander.heat.*`, `sander.nvt.*`, `sander.npt.*` — minimization/heating/equilibration outputs and energy/temperature/pressure traces
- `sander.free.*` — free production MD trajectory
- `1aki_rms_first.dat`, `1aki_rms_exp.dat`, `1aki_rgyr.dat` — RMSd and radius-of-gyration analysis
- `1aki_imaged_traj.trr` — final imaged, solvent-stripped trajectory

## Configuration

- `configs/fetch_pdb.yaml` — target PDB code (1AKI)
- `configs/gen_top.yaml` — AMBER force field used by LEaP
- `configs/sander_h_min.yaml`, `configs/sander_n_min.yaml`, `configs/sander_min.yaml`, `configs/sander_heat.yaml`, `configs/sander_nvt.yaml`, `configs/sander_npt.yaml`, `configs/sander_free.yaml` — sander MD input parameters (restraints, time step, temperature, pressure, simulation length) for each stage
- `configs/leap_solvate.yaml`, `configs/leap_add_ions.yaml` — solvent box geometry and ion concentration
- `configs/process_energy.yaml`, `configs/process_temp.yaml`, `configs/process_npt.yaml` — which energy/temperature/pressure terms to extract from sander logs
- `configs/cpptraj_rms_first.yaml`, `configs/cpptraj_rms_exp.yaml`, `configs/cpptraj_rgyr.yaml`, `configs/cpptraj_image.yaml` — cpptraj analysis/imaging options

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [biobb_amber](https://github.com/bioexcel/biobb_amber)
- [AmberTools](https://ambermd.org/AmberTools.php)
- [MDWeb AMBER FULL MD Setup tutorial](https://mmb.irbbarcelona.org/MDWeb2/help.php?id=workflows#AmberWorkflowFULL)
- [BioExcel AMBER protein MD setup tutorial](https://biobb-wf-amber-md-setup.readthedocs.io)
