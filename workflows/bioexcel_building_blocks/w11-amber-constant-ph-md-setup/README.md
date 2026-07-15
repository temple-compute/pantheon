# W-16 · AMBER Constant pH MD Setup

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

This workflow sets up and runs a constant-pH molecular dynamics simulation using AmberTools, illustrated with Bovine Pancreatic Trypsin Inhibitor (BPTI, PDB: 6PTI). Starting from the raw PDB file, it prepares the structure for constant-pH AMBER, builds a protein topology with the ff14SB force field and `constph` residue templates, solvates in a truncated octahedron box, neutralizes with ions, generates the constant-pH input file (`cpinutil`) for titratable residues (ASP, GLU, CYS, LYS, TYR), runs a heat/NVT/NPT equilibration protocol, performs the constant-pH production MD with `sander`, and finishes by analyzing protonation states to predict per-residue pKa values with `cphstats`. Horus provisions the AmberTools/biobb conda environment automatically and runs all stages locally.

## Pipeline

```
fetch_pdb          Download 6PTI from the PDB (biobb_io)
   │
pdb4amber          Prepare structure for constant-pH AMBER
   │
leap_gen_top       Build protein topology (ff14SB + constph, leap)
   │
leap_solvate       Solvate in truncated octahedron box (TIP3P, leap)
   │
leap_add_ions      Neutralize and add ions (leap)
   │
parmed_cpinutil    Generate constant-pH input file (cpinutil, titratable residues)
   │
sander_min ──► process_min       Energy minimize with backbone restraints
   │
sander_heat ──► process_heat      Heat 0 → 300 K
   │
sander_nvt ──► process_nvt         NVT equilibration
   │
sander_npt ──► process_npt          NPT equilibration
   │
sander_cph_free    Constant pH production MD (sander, solvph 7.0)
   │
cphstats           Analyse protonation states, predict pKa values
```

## Prerequisites

- **uv** (recommended) or pip — to install horus-runtime
- **micromamba**, **mamba**, or **conda** — the workflow executor builds a shared conda environment from `conda_env.yaml` to provision AmberTools and the biobb stack

## Quick Start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# From the workflow directory, install horus-runtime
cd workflows/bioexcel_building_blocks/w11-amber-constant-ph-md-setup
uv sync
# or: pip install horus-runtime horus-environments

# Run the workflow
uv run horus run workflow.yaml
```

The first run builds the conda environment (this takes a few minutes). Subsequent runs reuse the cached environment at `../.horus_conda_env`.

## Inputs / Outputs

This workflow has no file inputs — it fetches PDB 6PTI automatically from the RCSB (`configs/fetch_pdb.yaml`).

**Outputs** (all under `workflow_results/`):
- `results/6PTI.pdb` — downloaded structure
- `results/structure.pdb4amber.pdb` — AMBER-ready structure
- `results/structure.leap.{pdb,top,crd}` — protein topology (ff14SB + constph)
- `results/structure.ions.{pdb,parmtop,crd}` — solvated, ion-neutralized system
- `results/structure.cpin`, `results/structure.cpH.parmtop` — constant-pH input file and topology
- `results/sander.pH.{netcdf,rst,cpout,cprst,log,mdinfo}` — constant-pH production MD outputs
- `results/cphstats.pH.dat`, `results/cphstats.pH.pop.dat` — pKa predictions and protonation-state populations

## Configuration

`configs/fetch_pdb.yaml` sets the PDB code. `configs/leap_*.yaml` control force field, water model, box geometry, and ion neutralization. `configs/parmed_cpinutil.yaml` sets the Generalized Born model (`igb`) and the list of titratable residue names. `configs/sander_*.yaml` control simulation length, restraints, and constant-pH parameters (`solvph`, `icnstph`, `ntcnstph`) for each stage. `configs/cphstats.yaml` controls the pKa-analysis running-average window.

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [biobb_amber](https://github.com/bioexcel/biobb_amber)
- [biobb_wf_amber tutorial notebooks](https://github.com/bioexcel/biobb_wf_amber)
- [AmberTools](https://ambermd.org/AmberTools.php)
- [AMBER Constant pH MD Tutorial](https://ambermd.org/tutorials/advanced/tutorial18/index.htm)
