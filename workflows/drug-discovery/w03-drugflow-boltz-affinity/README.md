# W-32 · DrugFlow + Boltz-2 Affinity

Design new molecules for a binding pocket with DrugFlow, then score every design with Boltz-2 affinity and get a ΔG table ranked best-first.

![Domain: Drug Discovery](https://img.shields.io/badge/domain-drug--discovery-blue)

## Overview

Generates novel molecules for a binding pocket with [DrugFlow](https://github.com/LPDI-EPFL/DrugFlow), then scores each with [Boltz-2](https://github.com/jwohlwend/boltz) affinity and ranks them by estimated ΔG. The pocket is defined by a protein and a reference ligand. The workflow has 6 tasks.

## Pipeline

```
download_checkpoint  Zenodo checkpoint            ──► drugflow.ckpt
fetch_source         DrugFlow @ pinned commit     ──► drugflow_src/
generate             protein + ref ligand + ckpt  ──► results/samples.sdf
prepare_inputs       one Boltz YAML per molecule  ──► results/boltz_inputs/, results/smiles.json
predict              boltz predict                ──► results/predictions/affinity_*.json
rank                 affinity -> ΔG, sort         ──► results/deltaG_table.csv
```

## Inputs / Outputs

- `examples/kras.pdb`: target protein.
- `examples/kras_ref_ligand.sdf`: reference ligand; defines the pocket.
- `results/samples.sdf`: generated molecules.
- `results/deltaG_table.csv`: `molecule, smiles, affinity_pred_value, binding_probability, deltaG_kcal_per_mol`, sorted by ascending ΔG (best first).

ΔG = 1.364 · (affinity_pred_value − 6) kcal/mol, treating IC50 as a Kd proxy at 298 K. It is meant for ranking, not as an exact free energy.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `protein` | `examples/kras.pdb` | Target protein, same frame as the reference ligand |
| `ref_ligand` | `examples/kras_ref_ligand.sdf` | Bound reference ligand |
| `n_samples` | 10 | Molecules DrugFlow generates (1-1000) |
| `pocket_cutoff` | 8.0 | Pocket residues within this distance (Å) of the ligand (4-12) |
| `seed` | 42 | Seed for DrugFlow and Boltz-2 |
| `use_gpu` | on | Run DrugFlow and Boltz-2 on GPU; off runs both on CPU (slow) |
| `use_msa` | on | Boltz-2 MSA server; off is single sequence |
| `diffusion_samples` | 1 | Boltz-2 structure samples per molecule (1-10) |

## References

- [DrugFlow GitHub](https://github.com/LPDI-EPFL/DrugFlow) · checkpoint on [Zenodo](https://zenodo.org/records/14919171)
- [Boltz-2 GitHub](https://github.com/jwohlwend/boltz)
- [RDKit](https://github.com/rdkit/rdkit)
