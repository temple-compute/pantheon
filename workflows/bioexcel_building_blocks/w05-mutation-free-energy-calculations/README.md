# W-10 · Mutation Free Energy (pmx, non-equilibrium TI)

Alchemical free energy of a point mutation with pmx and GROMACS, estimated by Crooks, BAR and Jarzynski.

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

Computes a fast-growth non-equilibrium mutation free energy with GROMACS and pmx (default Staphylococcal nuclease, PDB 1STN, Ile10 to Ala). From wild-type (stateA) and mutant (stateB) equilibrium trajectories it builds hybrid structures and topologies, equilibrates, and runs one fast TI transition per direction. The final `pmxanalyse` estimate uses the precomputed dHdl bundles `dhdlA_zip`/`dhdlB_zip` (pmx tutorial, Ile10Ala), not this run's own transitions. The workflow has 23 tasks.

## Pipeline

```
gmx_trjconv_str_ens_stateA / _stateB       Extract snapshots from each equilibrium trajectory
pmxmutate_stateA / _stateB                 Model mutated structures
pdb2gmx_stateA / _stateB                   Topology per state
pmxgentop_stateA / _stateB                 Hybrid dual-topology
make_ndx_stateB                            FREEZE index for stateB dummy atoms
grompp_min_stateB ──► mdrun_min_stateB ──► gmx_energy_min_stateB   Minimize dummy atoms
grompp_eq_stateA ──► mdrun_eq_stateA ──► gmx_energy_eq_stateA      NPT equilibration
grompp_eq_stateB ──► mdrun_eq_stateB ──► gmx_energy_eq_stateB      NPT equilibration
grompp_ti_stateA ──► mdrun_ti_stateA       Fast TI, WT to mutant
grompp_ti_stateB ──► mdrun_ti_stateB       Fast TI, mutant to WT
pmxanalyse                                 Free energy (CGI, BAR, Jarzynski)
```

## Inputs / Outputs

- Inputs: stateA and stateB `.tpr`/`.xtc` equilibrium runs and the dHdl bundles, all bundled in `pmx_tutorial/`.
- Outputs (`results/`): `mutA.pdb`, `mutB.pdb`, `pmxA_top.zip`, `pmxB_top.zip`, `eqoutA.gro`, `eqoutB.gro`, `tiA.gro`, `tiA_dhdl.xvg`, `tiB.gro`, `tiB_dhdl.xvg`, `pmx.txt`, `pmx.plots.png`.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `mutation_resnum` | `10` | Residue number to mutate |
| `wt_residue` | `Ile` | Residue in stateA (wild type) |
| `mut_residue` | `Ala` | Residue in stateB (mutant) |
| `frame_interval_ps` | `200` | Snapshot spacing in each 1 ns trajectory |
| `stateA_tpr`, `stateA_traj` | `pmx_tutorial/stateA.tpr`, `stateA_1ns.xtc` | Wild-type equilibrium run |
| `stateB_tpr`, `stateB_traj` | `pmx_tutorial/stateB.tpr`, `stateB_1ns.xtc` | Mutant equilibrium run |
| `dhdlA_zip`, `dhdlB_zip` | `pmx_tutorial/dhdlA.zip`, `dhdlB.zip` | Precomputed dHdl work curves, WT to mutant and back |

The mutation must match the uploaded trajectories.

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [biobb_pmx](https://github.com/bioexcel/biobb_pmx)
- [pmx](https://github.com/deGrootLab/pmx)
- [Official pmx Sardinia 2018 tutorial](http://pmx.mpibpc.mpg.de/sardinia2018_tutorial1/index.html)
- [BioExcel mutation free energy tutorial](https://biobb-wf-pmx-tutorial.readthedocs.io)
