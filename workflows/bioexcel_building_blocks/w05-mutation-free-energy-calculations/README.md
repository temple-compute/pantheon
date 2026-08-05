# W-10 · Mutation Free Energy Calculations

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

This workflow computes a **fast-growth non-equilibrium mutation free energy** (ΔΔG) using GROMACS and **pmx**, on the Staphylococcal nuclease protein (PDB: 1STN), mutating residue Ile10 to Ala (and back). Starting from pre-equilibrated wild-type (stateA) and mutant (stateB) trajectories, it models the alchemical hybrid structure and topology for each state, minimizes and equilibrates the dummy atoms introduced by the mutation, runs fast thermodynamic-integration (TI) transitions in both directions (WT→Mut and Mut→WT), and estimates the free-energy difference from the accumulated dHdl work values using the Crooks Gaussian Intersection (CGI), BAR, and Jarzynski estimators. Horus provisions the GROMACS/pmx/biobb conda environment automatically and runs all stages locally.

## Pipeline

```
gmx_trjconv_str_ens_stateA    Extract snapshots from WT (stateA) equilibrium trajectory
gmx_trjconv_str_ens_stateB    Extract snapshots from Mutant (stateB) equilibrium trajectory
   │
pmxmutate_stateA               Model stateA mutated structure (Ile10 → Ala, WT→Mut)
pmxmutate_stateB               Model stateB mutated structure (Ala10 → Ile, Mut→WT)
   │
pdb2gmx_stateA / pdb2gmx_stateB      Build GROMACS topology per state (pdb2gmx)
   │
pmxgentop_stateA / pmxgentop_stateB   Generate hybrid dual-topology parameters (pmxgentop)
   │
make_ndx_stateB                 Create FREEZE index for stateB dummy atoms (make_ndx)
   │
grompp_min_stateB ──► mdrun_min_stateB ──► gmx_energy_min_stateB   Minimize stateB dummy atoms
   │
grompp_eq_stateA ──► mdrun_eq_stateA ──► gmx_energy_eq_stateA      NPT equilibration, stateA
grompp_eq_stateB ──► mdrun_eq_stateB ──► gmx_energy_eq_stateB      NPT equilibration, stateB
   │
grompp_ti_stateA ──► mdrun_ti_stateA    Fast thermodynamic integration, WT→Mut
grompp_ti_stateB ──► mdrun_ti_stateB    Fast thermodynamic integration, Mut→WT
   │
pmxanalyse                      Compute ΔΔG (CGI / BAR / Jarzynski) from dhdl work values
```

## Prerequisites

- **uv** (recommended) or pip — to install horus-runtime
- **micromamba**, **mamba**, or **conda** — the workflow executor builds a shared conda environment from `conda_env.yaml` to provision GROMACS, pmx, and the biobb stack

## Quick Start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# From the workflow directory, install horus-runtime
cd workflows/bioexcel_building_blocks/w05-mutation-free-energy-calculations
uv sync
# or: pip install horus-runtime horus-environments

# Run the workflow
uv run horus run workflow.yaml
```

The first run builds the conda environment (this takes a few minutes). Subsequent runs reuse the cached environment at `../.horus_conda_env`.

## Inputs / Outputs

**Inputs** — pre-generated equilibrium trajectories bundled in `pmx_tutorial/`: `stateA_1ns.xtc`/`stateA.tpr` (wild type) and `stateB_1ns.xtc`/`stateB.tpr` (mutant). The final `pmxanalyse` step also reads `pmx_tutorial/dhdlA.zip` and `pmx_tutorial/dhdlB.zip` — bundles of many pre-computed replicate dHdl curves, since the CGI/BAR/Jarzynski estimators need dozens of independent transitions to converge (the single `tiA_dhdl.xvg`/`tiB_dhdl.xvg` this workflow's own `mdrun_ti_stateA`/`mdrun_ti_stateB` steps produce are illustrative of the method, not the statistical sample analyzed).

**Outputs** (all under `workflow_results/results/`):
- `mutA.pdb`, `mutB.pdb` — modelled mutant structures per state
- `pmxA_top.zip`, `pmxB_top.zip` — hybrid dual-topology files
- `eqoutA.gro`, `eqoutB.gro` — equilibrated structures per state
- `tiA.gro`, `tiA_dhdl.xvg` / `tiB.gro`, `tiB_dhdl.xvg` — TI run outputs per direction
- `pmx.txt` — computed free energy estimate and statistics
- `pmx.plots.png` — work-distribution and convergence plots

## Configuration

- `configs/pmxmutate_stateA.yaml`, `configs/pmxmutate_stateB.yaml` — mutation list and force field (amber99sb-star-ildn-mut)
- `configs/pdb2gmx_stateA.yaml`, `configs/pdb2gmx_stateB.yaml` — protein topology settings per state
- `configs/grompp_min_stateB.yaml`, `configs/grompp_eq_stateA.yaml`, `configs/grompp_eq_stateB.yaml`, `configs/grompp_ti_stateA.yaml`, `configs/grompp_ti_stateB.yaml` — GROMACS `mdp` parameters for each minimization/equilibration/TI run
- `configs/pmxanalyse.yaml` — free-energy estimator selection and analysis options

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [biobb_pmx](https://github.com/bioexcel/biobb_pmx)
- [pmx](https://github.com/deGrootLab/pmx)
- [Official pmx Sardinia 2018 tutorial](http://pmx.mpibpc.mpg.de/sardinia2018_tutorial1/index.html)
- [BioExcel mutation free energy tutorial](https://biobb-wf-pmx-tutorial.readthedocs.io)
