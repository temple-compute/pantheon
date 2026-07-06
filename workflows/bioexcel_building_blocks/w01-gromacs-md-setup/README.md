# W-03 · GROMACS MD Setup

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

This workflow runs a complete molecular dynamics setup for hen egg-white lysozyme (PDB: 1AKI) using GROMACS and the CHARMM36 force field. Starting from the raw PDB file, it builds a topology, solvates the protein in a water box, adds neutralizing NaCl ions, energy-minimizes the system, runs NVT and NPT equilibration, and finishes with a free production MD simulation. Horus provisions the full GROMACS/biobb conda environment automatically for each stage and routes every task to the local machine — swapping any stage to a remote cluster is a one-line `target:` change.

## Pipeline

```
fetch_pdb          Download 1AKI from the PDB
   │
fix_side_chain     Model missing side-chain atoms (biobb_structure_utils)
   │
build_topology     Build GROMACS topology (pdb2gmx, CHARMM36)
   │
editconf           Define cubic simulation box
   │
solvate            Solvate box with SPC water
   │
grompp_ions ──► genion        Add neutralizing NaCl ions
   │
grompp_minimize ──► mdrun_minimize   Energy minimization (steepest descent)
   │
grompp_nvt ──► mdrun_nvt     NVT equilibration (restrained, 10 ps)
   │
grompp_npt ──► mdrun_npt     NPT equilibration (restrained, 10 ps)
   │
grompp_free ──► mdrun_free   Free production MD (100 ps)
   │
gmx_image          Re-center protein, fix periodic boundary conditions
   │
gmx_trjconv_str    Extract final dry protein structure
```

## Prerequisites

- **uv** (recommended) or pip — to install horus-runtime
- **micromamba**, **mamba**, or **conda** — the workflow executor builds a shared conda environment from `conda_env.yaml` to provision GROMACS and the biobb stack

## Quick Start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# From the workflow directory, install horus-runtime
cd workflows/bioexcel_building_blocks/w01-gromacs-md-setup
uv sync
# or: pip install horus-runtime horus-environments

# Run the workflow
uv run horus run workflow.yaml
```

The first run builds the conda environment (this takes a few minutes). Subsequent runs reuse the cached environment at `../.horus_conda_env`.

## Inputs / Outputs

This workflow has no file inputs — it fetches 1AKI from the RCSB PDB automatically.

**Outputs** (all under `workflow_results/`):
- `results/downloaded.pdb` — raw PDB from RCSB
- `results/fixed.pdb` — PDB with modelled side chains
- `results/structure.gro`, `results/topol.top`, `results/posre.itp` — GROMACS topology
- `results/mdrun_nvt.trr`, `results/mdrun_npt.trr` — equilibration trajectories
- `results/mdrun_free.trr` — production MD trajectory
- `results/structure.dry.pdb` — final dry protein structure (solvent stripped)

## Configuration

Config files in `configs/` control GROMACS `mdp` parameters (time step, temperature, pressure, restraints) for each simulation stage. Edit them to adjust simulation length, temperature, force field, or barostat settings before running.

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [GROMACS](https://www.gromacs.org)
- [CHARMM36 force field](http://mackerell.umaryland.edu/charmm_ff.shtml)
- [BioExcel MD setup tutorial](https://biobb-wf-md-setup.readthedocs.io)
