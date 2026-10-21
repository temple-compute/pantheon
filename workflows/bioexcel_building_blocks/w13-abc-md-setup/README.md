# W-18 · ABC MD Setup

Ascona B-DNA Consortium MD setup for a DNA duplex with AmberTools: parmbsc1 topology, OPC water box, salt, hydrogen mass repartitioning, 10-step equilibration and free MD.

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

Ascona B-DNA Consortium (ABC) MD setup for the Drew-Dickerson dodecamer (CGCGAATTCGCG) with AmberTools. It builds a parmbsc1 DNA topology, solvates it in a truncated octahedron OPC water box, adds KCl (100 mM by default), randomizes ion positions with cpptraj, applies hydrogen-mass repartitioning with parmed for a 4 fs timestep, runs the 10-step Roe & Brooks equilibration with sander, and finishes with a free production MD run. The workflow has 26 tasks.

## Pipeline

```
leap_gen_top               Build DNA topology (parmbsc1, leap)
leap_solvate               Solvate in truncated octahedron box (leap)
leap_add_ions              Neutralize + add salt (leap)
cpptraj_randomize_ions     Randomize ion positions (cpptraj)
parmed_hmassrepartition    Hydrogen-mass repartition for 4 fs (parmed)
sander_eq1..eq10           10 equilibration steps (minimization, heating, NPT)
process_eq1..eq10          Extract energy and pressure/density per step
sander_md                  Free production MD (4 fs)
```

## Inputs / Outputs

Inputs: the parameters below (starting structure and the 11 sander MDIN files `ABCix_config_files/step1.in` ... `step10.in`, `md.in`).

Outputs (`results/`):
- `structure.leap.*`, `structure.solv.*`, `structure.ions.*`, `structure.randIons.*`: topology and coordinates at each build stage
- `structure.leap.4fs.top`: hydrogen-mass-repartitioned topology
- `sander.eq1.nc` ... `sander.eq10.nc`: equilibration trajectories, with `.log`, `.mdinfo`, `.ncrst` and energy/pressure-density `.dat` files per step
- `sander.md.nc`: production trajectory

## Parameters

| id | Default | Meaning |
|---|---|---|
| `dna_pdb` | `CGCGAATTCGCG.pdb` | Initial DNA duplex structure (PDB). |
| `positive_ion` | `K+` | Counter-ion (`K+`, `Na+`). |
| `box_padding_a` | 15.0 | Minimum distance in angstrom between the DNA and the box edge (8-25). |
| `ionic_concentration_mm` | 100 | Added salt in mM on top of neutralization (0-1000). |
| `md_steps` | 500 | Production steps at 4 fs (500 = 2 ps; 25,000,000 = 100 ns). |
| `step1_mdin` ... `step10_mdin`, `md_mdin` | `ABCix_config_files/*.in` | sander MDIN files for equilibration and production (expert). |

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [biobb_amber](https://github.com/bioexcel/biobb_amber)
- [biobb_wf_amber tutorial notebooks](https://github.com/bioexcel/biobb_wf_amber)
- [AmberTools](https://ambermd.org/AmberTools.php)
- [Ascona B-DNA Consortium / NAFlex ABC](http://mmb.irbbarcelona.org/NAFlex/ABC)
- [The static and dynamic structural heterogeneities of B-DNA](https://doi.org/10.1093/nar/gkz905)
