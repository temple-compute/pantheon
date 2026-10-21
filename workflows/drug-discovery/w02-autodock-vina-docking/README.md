# W-02 · AutoDock Vina Docking

Dock a ligand library into a receptor (uploaded or fetched by PDB ID) with AutoDock Vina and get ranked binding energies per ligand and per pose.

![Domain: Drug Discovery](https://img.shields.io/badge/domain-drug--discovery-blue)

## Overview

Docks a ligand library into a receptor (uploaded PDB or fetched from RCSB) with [AutoDock Vina](https://github.com/ccsb-scripps/AutoDock-Vina). Receptors are prepared with OpenBabel and ligands with Meeko (SMILES are embedded to 3D with RDKit). Output is ranked binding energies per ligand and per pose. The workflow has 3 tasks.

## Pipeline

```
prep    receptor.pdb (or RCSB pdb_id) + ligands ──► results/vina_inputs.tar.gz
dock    AutoDock Vina per ligand                ──► results/docking_out.tar.gz
summary parse affinities                        ──► results/summary.csv + results/poses.csv
```

## Inputs / Outputs

- `receptor`: PDB file, or `pdb_id` to fetch from RCSB (first-model protein atoms only; hydrogens added at pH 7.4). The example is chain A of 1IEP (Abl kinase).
- `ligands`: one `SMILES [name]` per line, or a 3D `.sdf`.
- `results/summary.csv`: one row per ligand, best (most negative) first: `rank, ligand, best_affinity_kcal_mol, mean_affinity_kcal_mol, num_poses`.
- `results/poses.csv`: one row per pose: `ligand, pose, affinity_kcal_mol, rmsd_lb, rmsd_ub`.
- Ligands that fail to dock are skipped and recorded in `manifest.json`.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `receptor` | `examples/receptor.pdb` | Receptor, used when `pdb_id` is empty |
| `pdb_id` | empty | 4-character PDB code to fetch instead of the upload |
| `ligands` | `examples/ligands.smi` | Ligand library (SMILES or SDF) |
| `box_center` | `15.190 53.903 16.917` | Box center `X Y Z` in Å (1IEP ATP pocket); empty = blind docking on the centroid |
| `box_size` | 20 | Cubic box edge in Å (10-60) |
| `exhaustiveness` | 16 | Vina search effort per ligand (1-64) |
| `n_poses` | 9 | Poses per ligand (1-20) |

`box_center` must match the receptor used.

## References

- [AutoDock Vina](https://github.com/ccsb-scripps/AutoDock-Vina)
- [AutoDock Vina docs](https://autodock-vina.readthedocs.io)
- [AutoDock Vina 1.2.0 paper (JCIM)](https://pubs.acs.org/doi/10.1021/acs.jcim.1c00203)
- [Meeko](https://github.com/forlilab/Meeko)
- [Open Babel](https://openbabel.org)
