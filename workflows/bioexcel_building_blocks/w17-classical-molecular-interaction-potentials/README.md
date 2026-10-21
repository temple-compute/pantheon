# W-22 · Classical Molecular Interaction Potentials

Classical molecular interaction potentials with CMIP: MIP grids and water/ion titration for a protein, protein-ligand (EGFR-Erlotinib) and protein-protein (RBD-hACE2) interaction energies.

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

Classical Molecular Interaction Potentials (CMIP) with three independent case studies: MIP grids and water/ion titration on lysozyme (1AKI), EGFR-Erlotinib protein-ligand interaction energies (4HJO, ligand parameterized with ACPype/GAFF and minimized with AMBER), and SARS-CoV-2 RBD-hACE2 protein-protein interaction energies from a pre-run AMBER structure. The workflow has 29 tasks.

## Pipeline

```
Case 1, lysozyme MIP and titration
fetch_pdb_lysozyme -> cmip_prepare_pdb_lysozyme
cmip_titration_lysozyme -> cat_pdb_titration     Structural waters and ions
cmip_run_mip_pos / _neg / _neutral               MIP grids

Case 2, EGFR-Erlotinib (fixed to 4HJO, ligand AQ4)
fetch_pdb_complex -> remove_pdb_water -> extract_heteroatoms -> reduce_add_hydrogens -> acpype_params_ac
leap_gen_top -> sander_mdrun -> amber_to_pdb     Topology, minimization
cmip_prepare_structure_complex -> remove_ligand
cmip_ignore_residues_protein -> cmip_run_egfr_interaction

Case 3, RBD-hACE2
cmip_prepare_structure_md -> extract_chain_hace2 / extract_chain_rbd
cmip_run_rbd_box / cmip_run_hace2_box / cmip_run_complex_box
cmip_ignore_residues_rbd -> cmip_run_rbd_interaction
cmip_ignore_residues_hace2 -> cmip_run_hace2_interaction
```

## Inputs / Outputs

Outputs (`results/`, file names keep the tutorial prefixes):
- `1aki.*.pdb`, `1aki.mip_{pos,neg,neutral}.cube`: lysozyme preparation, titration and MIP grids
- `4hjo.pdb`, `AQ4*.pdb`, `AQ4params.*`, `structure.*`: EGFR complex, ligand parameters, AMBER topology and minimized complex
- `4hjo.EGFR.energies.log`, `4hjo.EGFR.ener.byat.out`: EGFR-Erlotinib interaction energies
- `RBD-hACE2-ZN.*.cmip.pdb`, `{RBD,hACE2,COMPLEX}.box.json`: split chains and grid boxes
- `{RBD,hACE2}.energies.log`, `.byat.out`: RBD-hACE2 interaction energies

## Parameters

| id | Default | Meaning |
|---|---|---|
| `pdb_id` | `1aki` | Case 1 PDB code; leave empty to use `structure`. |
| `structure` | `examples/1aki.pdb` | Case 1 PDB file used when `pdb_id` is empty. |
| `titration_waters` | 20 | Water molecules placed by the titration (0-500). |
| `titration_ions` | 5 | Positive and negative ions placed by the titration, same count each (0-100). |
| `md_pdb` | `Files/RBD-hACE2-ZN.pdb` | Case 3 AMBER structure of a two-chain complex (chains A and B); must match `md_top`. |
| `md_top` | `Files/RBD-hACE2-ZN.top` | Case 3 AMBER topology matching `md_pdb`. |

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [biobb_cmip](https://github.com/bioexcel/biobb_cmip)
- [CMIP](https://anaconda.org/bioconda/cmip)
- [AMBER / AmberTools](https://ambermd.org)
- [ACPype](https://github.com/alanwilter/acpype)
- [BioExcel CMIP tutorial](https://biobb-wf-cmip.readthedocs.io)
