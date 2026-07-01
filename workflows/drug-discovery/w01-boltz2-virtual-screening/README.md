# W-01 · Boltz-2 Virtual Screening

![Domain: Drug Discovery](https://img.shields.io/badge/domain-drug--discovery-blue)

## Overview

Given a target protein and a library of candidate ligands, this workflow predicts
binding structure **and** affinity for each protein–ligand pair with
[Boltz-2](https://github.com/jwohlwend/boltz), then returns a ranked shortlist.
Boltz-2 (MIT/Recursion, 2025) gives affinity prediction at a fraction of the cost
of classical free-energy perturbation, making large virtual screens tractable.

The point on Horus: the expensive GPU only runs **one** stage. Cheap CPU prep and
ranking run locally; the GPU stage runs on a remote box (or in a container, or
both) and Horus moves the data across the boundary automatically. Swapping where
and how the GPU stage runs is a one-line config change.

## Pipeline

```
prep (local, CPU)          target.fasta + ligands.smi ──► boltz_inputs.tar.gz
   │   LocalToSSH transfer (automatic)
predict (SSH GPU box)      boltz predict (container)   ──► predictions.tar.gz
   │   SSHToLocal transfer (automatic)
rank (local, CPU)          parse affinity + confidence ──► top_hits.csv
```

## Quick start

```bash
# Install the horus-runtime and plugins (one time)
uv sync

# You can install UV with this command if you don't have it yet:
curl -LsSf https://astral.sh/uv/install.sh | sh

# Otherwise, you can install the horus-runtime and plugins with pip:
pip install horus-runtime horus-environments

# Run the workflow
horus run workflow.yaml
```

Outputs land in `out_dir/`: `boltz_inputs.tar.gz`, `predictions.tar.gz`, and
`top_hits.csv` (ranked best-first).

## Inputs / Outputs

**Inputs**
- `target.fasta` — protein target (first record is used).
- `ligands.smi` — one `SMILES [name]` per line; `name` becomes the ranked-output id.

**Output** — `top_hits.csv`:

## References

- [Boltz-2 GitHub](https://github.com/jwohlwend/boltz) · [paper](https://www.biorxiv.org/content/10.1101/2024.05.24.595648)
