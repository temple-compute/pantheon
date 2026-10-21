# W-15 · AMBER Protein-Ligand Complex MD Setup

Set up, run and analyze AMBER MD of a protein-ligand complex from a PDB entry or an uploaded structure.

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

Runs AmberTools on a protein-ligand complex (default T4 lysozyme L99A/M102Q with 2-propylphenol, PDB 3HTB, ligand JZ4): GAFF ligand parameters via ACPype, a combined LEaP topology, minimization, solvation, ions, heating, NVT/NPT equilibration, sander production MD, and cpptraj analysis. The PO4 and BME removal steps target 3HTB crystallization additives and leave other structures unchanged. The workflow has 30 tasks.

## Pipeline

```
fetch_pdb              Download pdb_id or use the uploaded complex
remove_pdb_water ──► remove_ligand_po4 ──► remove_ligand_bme ──► pdb4amber   Protein branch
extract_heteroatoms ──► reduce_add_hydrogens ──► babel_minimize ──► acpype_params_ac   Ligand branch
leap_gen_top           Complex topology
sander_h_min ──► process_h_min     Minimize ligand hydrogens in vacuo
sander_n_min ──► process_n_min     Minimize full system in vacuo
amber_to_pdb           Convert to PDB
leap_solvate           Truncated octahedron water box
leap_add_ions          Neutralize and add ions
sander_min ──► process_min         Minimize solvated system
sander_heat ──► process_heat       Heat 0 to 300 K
sander_nvt ──► process_nvt         NVT equilibration
sander_npt ──► process_npt         NPT equilibration
sander_free            Free production MD
cpptraj_rms_first / cpptraj_rms_exp / cpptraj_rgyr / cpptraj_image   RMSd, radius of gyration, imaging
```

## Inputs / Outputs

- Input: `pdb_id` (RCSB code) or, when empty, the `structure` upload; the ligand is selected by `ligand_code`.
- Outputs (`results/`): `complex.pdb`, `complex.noBME.pdb`, `ligand.pdb`, `ligand.reduce.H.pdb`, `ligand.H.min.mol2`, `ligand_params.{inpcrd,frcmod,lib,prmtop}`, `structure.leap.{pdb,top,crd}`, `structure.ions.{pdb,parmtop,crd}`, `sander.free.netcdf`, `complex_rms_first.dat`, `complex_rms_exp.dat`, `complex_rgyr.dat`, `complex_imaged_traj.trr`.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `pdb_id` | `3HTB` | RCSB PDB code; clear it to use `structure` |
| `structure` | `examples/3htb.pdb` | Complex used when `pdb_id` is empty; ligand must be HETATM records named `ligand_code` |
| `ligand_code` | `JZ4` | Ligand residue name; extracted, parameterized and restrained in vacuo |
| `ligand_charge` | `0` | Formal net charge of the ligand, passed to ACPype |
| `equilibration_steps` | `500` | sander steps per restrained equilibration stage (2 fs/step) |
| `production_steps` | `2500` | sander steps of the free production run (2 fs/step) |

Force fields, restraints and thermostat are set in `configs/*.yaml`.

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [biobb_amber](https://github.com/bioexcel/biobb_amber)
- [biobb_wf_amber tutorial notebooks](https://github.com/bioexcel/biobb_wf_amber)
- [AmberTools](https://ambermd.org/AmberTools.php)
- [ACPype](https://github.com/alanwilter/acpype)
