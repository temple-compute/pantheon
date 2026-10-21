# W-20 · Protein Conformational Transitions

Compute a conformational transition pathway between two states of a protein with GOdMD (discrete MD guided by a Maxwell-demon bias), from two PDB IDs or two uploaded structures.

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

Computes a conformational transition pathway between two states of a protein with GOdMD (discrete MD with a Maxwell-demon bias), illustrated with adenylate kinase closed (1AKE) to open (4AKE). The residue mapping between the two structures comes from an EMBOSS alignment, so both must be the same protein. The workflow has 8 tasks.

## Pipeline

```
fetch_pdb_origin -> extract_chain_origin -> remove_molecules_origin   Origin structure, ligand removed
fetch_pdb_target -> extract_chain_target                              Target structure
godmd_prep                  Residue mapping (EMBOSS water alignment)
godmd_run                   GOdMD transition simulation
cpptraj_convert             Trajectory mdcrd -> XTC
```

## Inputs / Outputs

Outputs (`results/`):
- `origin.pdb`, `target.pdb`: origin and target structures
- `origin.chains.pdb`, `target.chains.pdb`: selected chains; `origin.chains.nolig.pdb`: origin without ligand
- `origin.aln`, `target.aln`: residue-mapping alignments
- `transition.godmd.mdcrd`, `.pdb`, `.xtc`: transition trajectory, reference structure and XTC conversion

## Parameters

| id | Default | Meaning |
|---|---|---|
| `origin_pdb_id` | `1ake` | Origin PDB code; leave empty to use `origin_structure`. |
| `origin_structure` | `examples/1ake.pdb` | Origin PDB file used when the code is empty. |
| `target_pdb_id` | `4ake` | Target PDB code; leave empty to use `target_structure`. |
| `target_structure` | `examples/4ake.pdb` | Target PDB file used when the code is empty. |
| `origin_chain` | `A` | Origin chain. |
| `target_chain` | `A` | Target chain. |
| `ligand_to_remove` | `AP5` | Residue name of the ligand removed from the origin. |
| `temperature_k` | 400 | Temperature of the discrete MD run (200-600). |

## References

- [GOdMD web server](https://mmb.irbbarcelona.org/GOdMD/)
- [biobb_godmd](https://github.com/bioexcel/biobb_godmd)
- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [biobb_wf_godmd tutorial notebook](https://github.com/bioexcel/biobb_wf_godmd)
- [Exploration of conformational transition pathways from coarse-grained simulations (Sfriso et al., Bioinformatics)](https://doi.org/10.1093/bioinformatics/btt324)
- [EMBOSS](https://www.ebi.ac.uk/Tools/emboss/)
