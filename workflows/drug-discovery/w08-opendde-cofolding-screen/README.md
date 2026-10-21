# W-36 · OpenDDE Co-folding Screen

Co-fold every ligand in a SMILES library with a protein sequence using OpenDDE and rank the predicted complexes by interface confidence.

![Domain: Drug Discovery](https://img.shields.io/badge/domain-drug--discovery-blue)

## Overview

Co-folds each ligand in a SMILES library with a protein sequence using [OpenDDE](https://github.com/aurekaresearch/OpenDDE) (Aureka Research, Apache-2.0) and ranks the predicted complexes by interface confidence. OpenDDE has no affinity head. The workflow has 3 tasks.

## Pipeline

```
prep    target.fasta + ligands.smi ──► results/opendde_inputs.tar.gz (jobs.json)
predict opendde pred (+ MSA search) ──► results/predictions.tar.gz
rank    parse summary confidence    ──► results/top_hits.csv
```

## Inputs / Outputs

- `fasta`: target protein; the first record is used.
- `ligands`: one `SMILES [name]` per line; the name becomes the job and output id.
- `results/predictions.tar.gz`: CIF structures and confidence JSONs.
- `results/top_hits.csv`: `rank, ligand, iptm, ranking_score, ptm, plddt, has_clash, cif`. `iptm` is interface confidence, not binding affinity.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `fasta` | `examples/target.fasta` | Target protein |
| `ligands` | `examples/ligands.smi` | Ligand library |
| `use_msa` | on | Fetch a protein MSA via the ColabFold API before co-folding |
| `n_samples` | 1 | Diffusion samples per job (1-10); the best per ligand is kept |

## References

- [OpenDDE GitHub](https://github.com/aurekaresearch/OpenDDE) · [PyPI](https://pypi.org/project/opendde/)
