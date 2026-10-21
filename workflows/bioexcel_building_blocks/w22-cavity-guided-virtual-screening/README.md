# W-30 · Cavity-Guided Virtual Screening

Find the most druggable cavity of a receptor with fpocket, box it, and dock a ligand library into it with AutoDock Vina as a parallel map, ranked by affinity.

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

Structure-based virtual screening: fetches a receptor, detects cavities with fpocket, boxes the most druggable one, and docks a ligand library into it with AutoDock Vina, ranked by binding affinity. The docking task is a parallel map with one clone per ligand batch. The workflow has 11 tasks.

## Pipeline

```
fetch_pdb -> extract_protein
fpocket_run -> fpocket_filter -> select_pocket -> fpocket_select -> box   Cavity detection, pocket choice, docking box
str_check_add_hydrogens                                                   Receptor protonation
split_ligands                                                             Split library into batches
dock[00..NN]                                                              AutoDock Vina, one clone per batch
rank                                                                      Rank by affinity, write top poses
```

## Inputs / Outputs

Outputs (`results/`):
- `scores.csv`: ranking, most negative affinity first (`Rank,Affinity,Index,Identifier`)
- `screening_summary.json`: docked/failed counts, best hit, per-ligand failures
- `poses/<ligand>_poses.pdb`: top poses
- `pocket_report.json`: candidate cavities, filtering result and why the winner won
- `docked/<slot>/`: per-batch PDBQT outputs, Vina logs and `status.json`

A ligand that fails to dock is recorded in `status.json` and the summary; it does not fail the task.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `pdb_id` | `3HEC` | Receptor PDB code; leave empty to use `structure`. |
| `structure` | `examples/3hec.pdb` | Receptor PDB file used when `pdb_id` is empty. |
| `ligand_library` | `examples/ligands.sdf` | Ligands to screen, SDF or SMILES (`.smi`). |
| `rank_by` | `druggability_score` | fpocket metric used to pick the cavity (`druggability_score`, `score`, `volume`). |
| `residue_selection` | empty | MDAnalysis selection of a known site (e.g. `resid 71 or resid 104`); only cavities within 10 Å of its centre of mass can be picked. Empty considers every filtered cavity. |
| `ph` | 7 | pH used to protonate the receptor before docking (0-14). |
| `batch_size` | 2 | Ligands docked per parallel clone (1-500). |
| `exhaustiveness` | 8 | Vina search exhaustiveness per ligand (1-64). |
| `top_n` | 10 | Best-ranked ligands whose poses are written (1-1000). |

## References

- [BioExcel Building Blocks (biobb_vs)](https://github.com/bioexcel/biobb_vs)
- [fpocket](https://github.com/Discngine/fpocket)
- [AutoDock Vina](https://github.com/ccsb-scripps/AutoDock-Vina)
- [Open Babel](https://github.com/openbabel/openbabel)
- [MDAnalysis](https://github.com/MDAnalysis/mdanalysis)
- [Source workflow: biobb_wf_virtual-screening](https://github.com/bioexcel/biobb_wf_virtual-screening)
- [BioExcel Building Blocks](https://mmb.irbbarcelona.org/biobb/) documentation
- fpocket: Le Guilloux, Schmidtke & Tuffery, *BMC Bioinformatics* (2009)
- AutoDock Vina: Eberhardt, Santos-Martins, Tillack & Forli, *J. Chem. Inf. Model.* (2021)
- Related: [W-13 Protein-Ligand Docking (fpocket)](../w08-protein-ligand-docking-fpocket/README.md) — single-ligand version of the same chemistry
- Related: [W-06 Fan-out / Map / Gather](../../engine-showcases/w01-fanout-map-gather/README.md) — the engine construct this workflow is built on
