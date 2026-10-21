# W-23 · Molecular Structure Checking

Check and repair a PDB entry before MD: model/chain selection, alternate locations, disulfides, amides, chirality, missing side chains and backbone (Modeller), then a short AMBER minimization and a final quality report.

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

Checks and repairs a raw PDB entry before MD (default: human adenylate kinase 1A with AP5A, PDB 1Z83). It selects a model and chain, resolves alternate locations and disulfides, strips metals, ligands, waters and hydrogens, fixes amides and chirality, models missing side-chain and backbone atoms (Modeller), minimizes with sander, and writes a final quality report. The workflow has 20 tasks.

## Pipeline

```
fetch_pdb -> structure_check                  Download, initial quality report
extract_model -> extract_chain                Model 1, selected chain
fix_altlocs -> fix_ssbonds                    Alternate locations, disulfides (CYX)
remove_molecules_metals / _ligands            Remove listed metal ions and ligands
reduce_remove_hydrogens -> remove_pdb_water   Strip hydrogens and waters
fix_amides -> fix_chirality -> fix_side_chain
canonical_fasta -> fix_backbone               Missing backbone via Modeller
leap_gen_top -> sander_mdrun -> amber_to_pdb  AMBER topology, minimization
fix_pdb -> structure_check_final              Renumber, final quality report
```

## Inputs / Outputs

Outputs (`results/`):
- `downloaded.pdb`, `report.json`: raw structure and initial report
- `models.pdb`, `chains.pdb`, `altloc.pdb`, `ssbonds.pdb`, `metals.pdb`, `ligands.pdb`, `hydrogens.pdb`, `water.pdb`, `amides.pdb`, `chiral.pdb`, `sidechains.pdb`: one structure per repair step
- `canonical.fasta`, `backbone.pdb`: canonical sequence and backbone-completed structure
- `amber.pdb`, `amber.top`, `amber.crd`, `trj.*`, `amber_min.pdb`: AMBER topology, coordinates and minimization output
- `final.pdb`, `report_final.json`: final structure and quality report

## Parameters

| id | Default | Meaning |
|---|---|---|
| `pdb_id` | `1z83` | PDB code to check and repair. |
| `chain` | `A` | Chain to keep. |
| `altlocs` | `["A45:A","A67:A","A85:A"]` | JSON list of alternate-location picks, one per residue (chain, residue, altloc kept); `[]` skips the step. Default is for 1Z83. |
| `remove_metals` | `ZN` | Comma-separated metal ion residue names to strip; empty keeps all. Fails if none is present. |
| `remove_ligands` | `SO4,AP5` | Comma-separated ligand residue names to strip; empty keeps all. Fails if none is present. |
| `minimization_steps` | 500 | sander minimization cycles (0-20000). |

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [biobb_structure_utils](https://github.com/bioexcel/biobb_structure_utils)
- [biobb_model](https://github.com/bioexcel/biobb_model)
- [Modeller](https://salilab.org/modeller/)
- [AMBER / AmberTools](https://ambermd.org)
- [BioExcel structure checking tutorial](https://biobb-wf-structure-checking.readthedocs.io)
