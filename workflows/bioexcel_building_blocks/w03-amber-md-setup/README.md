# W-05 · AMBER Protein MD Setup

Set up, run and analyze an AMBER MD simulation of a protein from a PDB entry or an uploaded structure.

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

Runs AMBER (LEaP, sander, cpptraj) with ff14SB and TIP3P on a protein (default lysozyme, PDB 1AKI): topology, in vacuo minimization, solvation, NaCl, minimization, heating to 300 K, NVT and NPT equilibration, free production MD, and cpptraj analysis. The workflow has 23 tasks.

## Pipeline

```
fetch_pdb        Download pdb_id or use the uploaded structure
pdb4amber        Prepare PDB for AMBER
gen_top          LEaP topology and coordinates (ff14SB)
sander_h_min ──► process_h_min     Minimize hydrogens in vacuo
sander_n_min ──► process_n_min     Minimize full system in vacuo
amber_to_pdb     Convert minimized structure to PDB
leap_solvate     TIP3P water box
leap_add_ions    Neutralize and add NaCl (salt_mm)
sander_min ──► process_min         Minimize solvated system
sander_heat ──► process_heat       Heat 0 to 300 K
sander_nvt ──► process_nvt         NVT equilibration
sander_npt ──► process_npt         NPT equilibration
sander_free      Free production MD
cpptraj_rms_first / cpptraj_rms_exp / cpptraj_rgyr   RMSd vs first frame, RMSd vs experiment, radius of gyration
cpptraj_image    Image trajectory, strip solvent
```

## Inputs / Outputs

- Input: `pdb_id` (RCSB code) or, when empty, the `structure` upload.
- Outputs: `results/downloaded.pdb`, `structure.leap.top`/`.crd`, `structure.ions.parmtop`/`.crd`, `sander.free.netcdf`, `1aki_rms_first.dat`, `1aki_rms_exp.dat`, `1aki_rgyr.dat`, `1aki_imaged_traj.trr`.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `pdb_id` | `1AKI` | RCSB PDB code; clear it to use `structure` |
| `structure` | `examples/1aki.pdb` | Structure used when `pdb_id` is empty |
| `box_padding_a` | `9.0` | Minimum solute-to-box-edge distance (A), truncated octahedron |
| `salt_mm` | `150` | Ionic concentration on top of neutralizing ions (mM) |
| `equilibration_steps` | `500` | sander steps per restrained equilibration stage (2 fs/step) |
| `production_steps` | `2500` | sander steps of the free production run (2 fs/step) |

Restraints, heating protocol and cpptraj masks are set in `configs/*.yaml`.

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [AMBER](https://ambermd.org)
- [ff14SB force field](https://pubs.acs.org/doi/10.1021/acs.jctc.5b00255)
- [BioExcel AMBER MD setup tutorial](https://biobb-wf-amber-md-setup.readthedocs.io)
