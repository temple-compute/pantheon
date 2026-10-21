# W-24 · HADDOCK3 Protein-Protein Docking

Information-driven antibody-antigen docking with HADDOCK3: prepare gevokizumab and IL-1β, build ambiguous restraints from the paratope and epitope, then rigid-body docking, refinement, clustering and CAPRI evaluation.

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

Antibody-antigen docking with HADDOCK3, following the official tutorial: gevokizumab (PDB 4G6K) against interleukin-1 beta (4I1B), scored against the known complex (4G6M). The heavy and light chains are cleaned, trimmed to the variable domains and merged with biobb_pdb_tools; paratope/epitope residues become ambiguous restraints; docking then runs rigid-body sampling, flexible refinement, energy minimization and FCC clustering, with CAPRI evaluation at each stage. The workflow has 80 tasks.

## Pipeline

```
fetch_antibody / fetch_antigen / fetch_complex    Download 4G6K, 4I1B, 4G6M
ab_H_* / ab_L_*  -> ab_zip_HL -> ab_merge -> ab_reres -> ab_chain -> ab_chainxseg -> ab_tidy_final   Antibody (VH 1-120, VL 1-107)
ag_*                                              Antigen, chain B
cx_*                                              Reference complex, same preparation
write_ab_actpass -> passive_from_active -> actpass_to_ambig    Active/passive residues, ambiguous restraints
restrain_bodies                                   Restraints tying the antibody H and L chains
topology -> rigid_body -> capri_eval_1 -> sele_top -> flex_ref -> capri_eval_2
  -> em_ref -> capri_eval_3 -> clust_fcc -> sele_top_clusts -> capri_eval_4 -> contact_map
```

## Inputs / Outputs

The structures are fixed: the chain IDs, domain ranges and residue lists in `configs/` are specific to these entries. Outputs (`results/`):
- `4G6K_clean.pdb`, `4I1B_clean.pdb`, `4G6M_clean.pdb`: prepared antibody, antigen and reference complex
- `4G6K_actpass.txt`, `4I1B_actpass.txt`, `ambig-paratope-NMR-epitope.tbl`, `antibody-unambig.tbl`: residue lists and restraint tables
- `2_docking.zip`, `5_flexref.zip`, `7_emref.zip`: models after rigid-body, flexible refinement and minimization
- `3_caprieval.zip`, `6_caprieval2.zip`, `8_caprieval3.zip`, `11_caprieval4.zip`: CAPRI scores per stage
- `4_selected.zip`, `9_clustfcc.zip`, `10_seletopclusts.zip`: selections and clusters
- `12_contact_map.zip`: contact maps of the final cluster representatives

## Parameters

| id | Default | Meaning |
|---|---|---|
| `rigid_body_models` | 10 | Models sampled by rigid-body docking (10-10000; production runs use 1000). |
| `refine_top_models` | 8 | Best rigid-body models passed to refinement (1-1000); keep at or below `rigid_body_models`. |
| `models_per_cluster` | 4 | Top models kept per FCC cluster (1-50). |

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [biobb_haddock](https://github.com/bioexcel/biobb_haddock)
- [biobb_pdb_tools](https://github.com/bioexcel/biobb_pdb_tools)
- [HADDOCK3](https://github.com/haddocking/haddock3)
- [HADDOCK3 antibody-antigen tutorial](https://www.bonvinlab.org/education/HADDOCK3/HADDOCK3-antibody-antigen/)
- [BioExcel HADDOCK3 tutorial](https://biobb-wf-haddock.readthedocs.io)
