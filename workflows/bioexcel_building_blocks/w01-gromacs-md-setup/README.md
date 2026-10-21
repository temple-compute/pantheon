# W-03 · GROMACS Protein MD Setup

Set up and run a GROMACS MD simulation of a protein from a PDB entry or an uploaded structure.

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

Runs GROMACS with the CHARMM36 force field on a protein (default hen egg-white lysozyme, PDB 1AKI): topology, solvation, NaCl ions, minimization, NVT and NPT equilibration, free production MD, and trajectory re-centering. The workflow has 17 tasks.

## Pipeline

```
fetch_pdb          Download pdb_id or use the uploaded structure
fix_side_chain     Model missing side-chain atoms
build_topology     pdb2gmx, CHARMM36
editconf           Cubic box
solvate            SPC water
grompp_ions ──► genion               Neutralizing NaCl
grompp_minimize ──► mdrun_minimize   Steepest-descent minimization
grompp_nvt ──► mdrun_nvt             NVT equilibration, restrained
grompp_npt ──► mdrun_npt             NPT equilibration, restrained
grompp_free ──► mdrun_free           Free production MD
gmx_image          Re-center, fix periodic boundary artifacts
gmx_trjconv_str    Extract final dry structure
```

## Inputs / Outputs

- Input: `pdb_id` (RCSB code) or, when empty, the `structure` upload.
- Outputs: `results/downloaded.pdb`, `fixed.pdb`, `system.gro`, `pdb2gmx_top.zip`, `boxed.gro`, `solvated.gro`, `ionized.gro`, `minimized.gro`, `nvt.gro`, `npt.gro`, `md.gro`, `md.trr`, `imaged.trr`, `dry.gro`.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `pdb_id` | `1AKI` | RCSB PDB code; clear it to use `structure` |
| `structure` | `examples/1aki.pdb` | Structure used when `pdb_id` is empty |
| `box_padding_nm` | `1.0` | Minimum protein-to-box-edge distance (nm) |
| `ion_concentration_m` | `0` | NaCl added on top of neutralizing ions (M) |
| `equilibration_steps` | `5000` | Steps per restrained equilibration stage (2 fs/step) |
| `production_steps` | `50000` | Steps of the free production run (2 fs/step) |

Force field, thermostat and restraints are set in `configs/*.yaml`.

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [GROMACS](https://www.gromacs.org)
- [biobb_gromacs](https://github.com/bioexcel/biobb_gromacs)
- [biobb_model](https://github.com/bioexcel/biobb_model)
- [biobb_io](https://github.com/bioexcel/biobb_io)
- [biobb_analysis](https://github.com/bioexcel/biobb_analysis)
- [CHARMM36 force field](http://mackerell.umaryland.edu/charmm_ff.shtml)
- [BioExcel MD setup tutorial](https://biobb-wf-md-setup.readthedocs.io)
