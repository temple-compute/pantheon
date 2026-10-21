# W-01 · Boltz-2 Virtual Screening

Screen a ligand library against a protein sequence with Boltz-2: co-folded complex structures plus predicted binding affinity, ranked into a shortlist.

![Domain: Drug Discovery](https://img.shields.io/badge/domain-drug--discovery-blue)

## Overview

Screens a ligand library against a protein sequence with [Boltz-2](https://github.com/jwohlwend/boltz), which co-folds each protein-ligand pair and predicts binding affinity, then ranks the ligands into a shortlist. The workflow has 3 tasks.

## Pipeline

```
prep    target.fasta + ligands.smi ──► results/boltz_inputs.tar.gz (one YAML per ligand)
predict boltz predict              ──► results/predictions.tar.gz
rank    affinity + confidence      ──► results/top_hits.csv
```

## Inputs / Outputs

- `fasta`: target protein FASTA; the first record is used.
- `ligands`: one `SMILES [name]` per line; the name becomes the output id.
- Outputs: `results/boltz_inputs.tar.gz`, `results/predictions.tar.gz`, `results/top_hits.csv`.

`results/top_hits.csv` is sorted best first (highest binder probability, then lowest predicted value):

| Column | Meaning |
|---|---|
| `rank` | 1 = best |
| `ligand` | name from `ligands.smi` |
| `affinity_probability_binary` | Boltz-2 probability that the ligand binds |
| `affinity_pred_value` | predicted affinity, log10(IC50 in µM); lower is tighter |
| `confidence_score` | structure confidence of the complex |

## Parameters

| id | Default | Meaning |
|---|---|---|
| `use_msa` | on | Fetch the MSA from the ColabFold server; off runs single-sequence |
| `recycling_steps` | 3 | Boltz trunk recycling iterations (1-10) |
| `sampling_steps` | 200 | Diffusion steps per structure (50-500) |
| `diffusion_samples` | 1 | Structure samples per complex (1-10) |
| `accelerator` | `gpu` | `gpu` or `cpu` |

## References

- [Boltz-2 GitHub](https://github.com/jwohlwend/boltz) · [paper](https://www.biorxiv.org/content/10.1101/2024.05.24.595648)
