# W-22 · Classical Molecular Interaction Potentials

Classical molecular interaction potentials with CMIP: MIP grids and water/ion titration for a protein, protein-ligand (EGFR-Erlotinib) and protein-protein (RBD-hACE2) interaction energies.

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

Classical Molecular Interaction Potentials (CMIP) with three independent case studies: MIP grids and water/ion titration on a protein (default lysozyme, 1AKI), protein-ligand interaction energies for a PDB complex (default EGFR-Erlotinib, 4HJO with ligand AQ4; ligand parameterized with ACPype/GAFF and minimized with AMBER), and protein-protein interaction energies between two chains of a pre-run AMBER structure (default SARS-CoV-2 RBD-hACE2). The workflow has 29 tasks.

## Pipeline

```
Case 1, protein MIP and titration
fetch_pdb_lysozyme -> cmip_prepare_pdb_lysozyme  Fetch or upload the MIP protein, add CMIP charges
cmip_titration_lysozyme -> cat_pdb_titration     Structural waters and ions
cmip_run_mip_pos / _neg / _neutral               MIP grids

Case 2, protein-ligand complex
fetch_pdb_complex -> remove_pdb_water -> extract_heteroatoms -> reduce_add_hydrogens -> acpype_params_ac
leap_gen_top -> sander_mdrun -> amber_to_pdb     Topology, minimization
cmip_prepare_structure_complex -> remove_ligand  CMIP charges, isolated protein
cmip_ignore_residues_protein -> cmip_run_egfr_interaction   Mask all non-ligand residues, ligand-protein energies

Case 3, protein-protein complex (partners A and B)
cmip_prepare_structure_md -> extract_chain_hace2 (A) / extract_chain_rbd (B)
cmip_run_rbd_box / cmip_run_hace2_box / cmip_run_complex_box
cmip_ignore_residues_rbd -> cmip_run_rbd_interaction       Partner B vs partner A
cmip_ignore_residues_hace2 -> cmip_run_hace2_interaction   Partner A vs partner B
```

## Inputs / Outputs

Outputs (`results/`):
- `protein.*.pdb`, `protein.mip_{pos,neg,neutral}.cube`: MIP protein preparation, titration and MIP grids
- `complex.pdb`, `complex.noHOH.pdb`, `ligand*.pdb`, `ligand_params.*`, `structure.*`: complex, ligand parameters, AMBER topology and minimized complex
- `complex.cmip.pdb`, `complex.noLIG.pdb`, `complex.Prot_ignored.cmip.pdb`: CMIP-ready complex, isolated protein, masked complex
- `complex.energies.log`, `complex.ener.byat.out`: protein-ligand interaction energies
- `pp_complex.*.cmip.pdb`, `partner_{a,b}.cmip.pdb`, `{partner_a,partner_b,pp_complex}.box.json`: CMIP-ready complex, split chains and grid boxes
- `partner_{a,b}.energies.log`, `partner_{a,b}.energies.byat.out`: protein-protein interaction energies

## Parameters

| id | Default | Meaning |
|---|---|---|
| `pdb_id` | `1aki` | Case 1 PDB code; leave empty to use `structure`. |
| `structure` | `examples/1aki.pdb` | Case 1 PDB file used when `pdb_id` is empty. |
| `titration_waters` | 20 | Water molecules placed by the titration (0-500). |
| `titration_ions` | 5 | Positive and negative ions placed by the titration, same count each (0-100). |
| `complex_pdb_id` | `4hjo` | Case 2 PDB code of the protein-ligand complex (EGFR-Erlotinib). |
| `complex_ligand` | `AQ4` | Case 2 ligand residue name (Erlotinib); every other residue is masked as protein for the interaction energy. |
| `complex_ligand_charge` | 0 | Case 2 ligand net charge passed to ACPype (-20 to 20). |
| `md_pdb` | `Files/RBD-hACE2-ZN.pdb` | Case 3 AMBER structure of a two-chain complex; must match `md_top`. |
| `md_top` | `Files/RBD-hACE2-ZN.top` | Case 3 AMBER topology matching `md_pdb`. |
| `partner_a_chain` | `A` | Case 3 chain of the first partner (hACE2). |
| `partner_b_chain` | `B` | Case 3 chain of the second partner (RBD). |

## References

- [CMIP](https://anaconda.org/bioconda/cmip)
- [biobb_cmip](https://github.com/bioexcel/biobb_cmip)
- [AMBER / AmberTools](https://ambermd.org)
- [ACPype](https://github.com/alanwilter/acpype)
- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [BioExcel CMIP tutorial](https://biobb-wf-cmip.readthedocs.io)
