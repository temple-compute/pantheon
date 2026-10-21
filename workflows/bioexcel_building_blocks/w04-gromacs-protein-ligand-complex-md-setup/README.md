# W-09 · GROMACS Protein-Ligand Complex MD Setup

Set up and run GROMACS MD of a protein-ligand complex from a PDB entry or an uploaded structure.

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

Runs GROMACS on a protein-ligand complex (default T4 lysozyme L99A/M102Q with 2-propylphenol, PDB 3HTB, ligand JZ4). The structure is split into protein (AMBER99SB-ILDN) and ligand (GAFF via ACPype), merged into a restrained complex, solvated, ionized, minimized, equilibrated, and run as free MD with analysis. The workflow has 35 tasks.

## Pipeline

```
fetch_pdb              Download pdb_id or use the uploaded complex
Ligand branch:
extract_heteroatoms ──► reduce_add_hydrogens ──► babel_minimize ──► acpype_params_gmx
make_ndx_ligand ──► genrestr          Ligand position restraints
Protein branch:
extract_molecule ──► fix_side_chain ──► pdb2gmx
Merge:
trjconv_protein, trjconv_ligand ──► cat_pdb_complex ──► append_ligand
editconf               Truncated octahedron box
solvate                SPC water
grompp_ions ──► genion               Neutralizing NaCl
grompp_minimize ──► mdrun_minimize ──► gmx_energy_min
make_ndx_complex       Complex index groups
grompp_nvt ──► mdrun_nvt ──► gmx_energy_nvt
grompp_npt ──► mdrun_npt ──► gmx_energy_npt
grompp_free ──► mdrun_free           Free production MD
gmx_rms_first / gmx_rms_exp / gmx_rgyr   RMSd and radius of gyration
gmx_image ──► gmx_trjconv_str_dry    Re-center, extract dry structure
```

## Inputs / Outputs

- Input: `pdb_id` (RCSB code) or, when empty, the `structure` upload; the ligand is extracted by `ligand_code`.
- Outputs (`results/`): `downloaded.pdb`, `ligand.pdb`, `protein.pdb`, `fixed.pdb`, `pdb2gmx.gro`, `ligand.params.{gro,itp,top}`, `ligand_posres.itp`, `complex_H.pdb`, `ionized.gro`, `min_energy.xvg`, `nvt_temp.xvg`, `npt_PD.xvg`, `md.gro`, `md.trr`, `rms_first.xvg`, `rms_exp.xvg`, `rgyr.xvg`, `dry.gro`.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `pdb_id` | `3HTB` | RCSB PDB code; clear it to use `structure` |
| `structure` | `examples/3htb.pdb` | Complex used when `pdb_id` is empty; ligand must be HETATM records named `ligand_code` |
| `ligand_code` | `JZ4` | Ligand residue name; selects, parameterizes and restrains the ligand |
| `ligand_charge` | `0` | Formal net charge of the ligand, passed to ACPype |
| `equilibration_steps` | `5000` | Steps per restrained equilibration stage (2 fs/step) |
| `production_steps` | `25000` | Steps of the free production run (2 fs/step) |

Force field, box, ions and restraints are set in `configs/*.yaml`.

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [GROMACS](https://www.gromacs.org)
- [ACPype](https://github.com/alanwilter/acpype)
- [Open Babel](https://github.com/openbabel/openbabel)
- [biobb_gromacs](https://github.com/bioexcel/biobb_gromacs)
- [biobb_chemistry](https://github.com/bioexcel/biobb_chemistry)
- [biobb_model](https://github.com/bioexcel/biobb_model)
- [biobb_structure_utils](https://github.com/bioexcel/biobb_structure_utils)
- [Official GROMACS protein-ligand complex tutorial](http://www.mdtutorials.com/gmx/complex/index.html)
- [BioExcel protein-ligand complex MD setup tutorial](https://biobb-wf-protein-complex-md-setup.readthedocs.io)
