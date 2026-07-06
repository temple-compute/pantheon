# W-05 · AMBER MD Setup

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

This workflow runs a complete molecular dynamics setup and analysis for hen egg-white lysozyme (PDB: 1AKI) using the AMBER toolchain (LEaP, sander, cpptraj) and the ff14SB + TIP3P force field. Starting from the raw PDB, it builds an AMBER topology, minimizes the structure in vacuo, solvates in a TIP3P water box, adds neutralizing ions, energy-minimizes the solvated system, heats from 0 to 300 K, runs NVT and NPT equilibration, and finishes with a free production MD simulation. Post-processing with cpptraj computes RMSd (vs. first snapshot and vs. the experimental structure), radius of gyration, and produces an imaged trajectory with solvent stripped. Horus provisions the full AMBER/biobb conda environment automatically for each stage.

## Pipeline

```
fetch_pdb              Download 1AKI from the PDB
   │
pdb4amber              Prepare PDB for AMBER (rename residues, strip waters)
   │
gen_top                Build AMBER topology and coordinates (LEaP, ff14SB)
   │                   → structure.leap.pdb / .top / .crd
   ├──► sander_h_min ──► process_h_min   Minimize hydrogens in vacuo; extract energy
   │
sander_n_min ──► process_n_min           Minimize full system in vacuo; extract energy
   │
amber_to_pdb           Convert minimized structure to PDB (ambpdb)
   │
leap_solvate           Solvate in TIP3P water box (LEaP)
   │
leap_add_ions          Neutralize and add 0.15 M NaCl (LEaP)
   │
sander_min ──► process_min               Energy minimize solvated system
   │
sander_heat ──► process_heat             Heat 0 → 300 K (NVT, 2 ns)
   │
sander_nvt ──► process_nvt               NVT equilibration at 300 K
   │
sander_npt ──► process_npt               NPT equilibration (pressure coupling)
   │
sander_free            Free production MD simulation
   │
   ├──► cpptraj_rms_first   RMSd vs. first trajectory snapshot
   ├──► cpptraj_rms_exp     RMSd vs. experimental crystal structure
   ├──► cpptraj_rgyr        Radius of gyration over trajectory
   └──► cpptraj_image       Image trajectory, strip solvent → .trr
```

## Prerequisites

- **uv** (recommended) or pip, to install horus-runtime and horus-environments.
- **micromamba**, **mamba**, or **conda**. The workflow executor builds a shared conda environment from `conda_env.yaml` to provision AMBER and the biobb stack

## Quick Start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# From the workflow directory, install horus-runtime
cd workflows/bioexcel_building_blocks/w03-amber-md-setup
uv sync
# or: pip install horus-runtime horus-environments

# Run the workflow
uv run horus run workflow.yaml
```

The first run builds the conda environment (this takes a few minutes). Subsequent runs reuse the cached environment at `../.horus_conda_env`.

## Inputs / Outputs

This workflow has no file inputs, it fetches 1AKI from the RCSB PDB automatically.

**Outputs** (all under `workflow_results/`):
- `results/downloaded.pdb` — raw PDB from RCSB
- `results/structure.leap.top`, `.crd` — AMBER topology and coordinates
- `results/structure.ions.parmtop`, `.crd` — solvated + ionized system
- `results/sander.free.netcdf` — production MD trajectory
- `results/1aki_rms_first.dat` — RMSd vs. first snapshot (per-frame)
- `results/1aki_rms_exp.dat` — RMSd vs. experimental structure (per-frame)
- `results/1aki_rgyr.dat` — radius of gyration (per-frame)
- `results/1aki_imaged_traj.trr` — imaged, solvent-stripped trajectory

## Configuration

Config files in `configs/` control sander `mdin` parameters (time step, temperature, pressure, restraints, output frequency) and cpptraj analysis options for each stage. Edit them before running to adjust simulation length, force field, or thermostat/barostat settings.

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [AMBER](https://ambermd.org)
- [ff14SB force field](https://pubs.acs.org/doi/10.1021/acs.jctc.5b00255)
- [BioExcel AMBER MD setup tutorial](https://biobb-wf-amber-md-setup.readthedocs.io)
