# W-36 · OpenDDE Co-folding Screen

<img src="assets/logo.png" width="96" align="right" alt="W-36 logo">

Co-fold every ligand in a SMILES library with a protein sequence using OpenDDE and rank the predicted complexes by interface confidence.

![Domain: Drug Discovery](https://img.shields.io/badge/domain-drug--discovery-blue)

![W-36 cover](assets/cover.png)

## Overview

Given a target protein and a library of candidate ligands, this workflow co-folds
each protein–ligand pair with [OpenDDE](https://github.com/aurekaresearch/OpenDDE)
(Aureka Research, Apache-2.0), an open-source all-atom biomolecular foundation
model, then returns a ranked shortlist with the predicted complex structures.

It mirrors the Boltz-2 screen (W-01): cheap CPU prep and ranking; the single
expensive stage is co-folding, which asks for one GPU. Unlike Boltz-2, OpenDDE has **no affinity
head** — see the ranking note below.

> **Preview release.** OpenDDE's maintainers warn that CLI flags, I/O formats and
> checkpoints may change between versions and that it is not meant for production
> pipelines. Pin the `opendde` version once you have a working run.

## Pipeline

```
prep (CPU, stdlib)    target.fasta + ligands.smi ──► opendde_inputs.tar.gz  (jobs.json)
   │
predict (1 GPU)       opendde pred (+ MSA search) ──► predictions.tar.gz
   │                  device auto: CUDA → Apple MPS → CPU
rank (local, CPU)     parse summary confidence    ──► top_hits.csv
```

## Quick start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install the horus-runtime and plugins (one time)
uv sync

# Run the workflow
uv run horus run workflow.yaml
```

Executor: `uv_python_environment` (Python 3.11, `opendde[gpu]` from PyPI; the GPU
extra only installs on linux x86_64). The first run
downloads the OpenDDE checkpoint to `~/.cache/opendde` (override with
`OPENDDE_ROOT_DIR`).

Outputs land in `horus_workflow_results/results/`: `opendde_inputs.tar.gz`,
`predictions.tar.gz` (CIF structures + confidence JSONs) and `top_hits.csv`.

## Parameters

| id | Kind | Default | Range | Meaning |
|---|---|---|---|---|
| `fasta` | file | `examples/target.fasta` | FASTA | Target protein; the first record is used |
| `ligands` | file | `examples/ligands.smi` | SMILES | One `SMILES [name]` per line; the name becomes the job and output id |
| `use_msa` | boolean | on | on / off | Fetch a protein MSA via the public ColabFold MMseqs2 API before co-folding. Needs internet; off is faster but poses are weaker |
| `n_samples` | number | 1 | 1–10 | Diffusion samples per job (`--sample`); `rank.py` keeps the best per ligand |

Fixed: `modelSeeds` `[101]` in `scripts/prep.py`, and `--device auto` (CUDA, then
Apple MPS, then CPU).

To change a value locally, edit its `value:` in `workflow.yaml`, then `rm -rf params/`:
Horus writes `params/<id>` only when it is missing, so a stale file keeps the old value.

## Running in Temple Compute

Start a campaign from the library entry: the form shows the FASTA and SMILES uploads,
the MSA toggle and the samples slider. `predict` carries
`resources: {cpus: 4, gpus: 1, memory_gb: 16, walltime: 8h}`, so an auto-provisioned
target gives it a single-GPU node; `prep` and `rank` are stdlib-only and light.

## Inputs / Outputs

**Inputs**
- `target.fasta` — protein target (first record is used).
- `ligands.smi` — one `SMILES [name]` per line; `name` becomes the job and ranked-output id.

**Output** — `top_hits.csv`: `rank, ligand, iptm, ranking_score, ptm, plddt, has_clash, cif`.

## Ranking note

`iptm` is the model's **interface confidence**, not a binding affinity. It tells
you how well-defined the predicted ligand pose is, which is useful for
triaging, but it is not ΔG or a potency estimate. Use it to narrow a library, then
validate with docking / free-energy methods (e.g. W-02) and, ultimately, the lab.

## Implementation notes

- Ligands are passed as raw SMILES in OpenDDE's `ligand` entity; CCD codes
  (`CCD_XXX`) and `FILE_` paths are also supported by OpenDDE but not by `prep.py`.
- `opendde pred` (pinned 1.2.0) preprocesses `jobs.json` itself, including the MSA
  search when `use_msa` is on; earlier releases needed a separate `opendde msa` step
  whose output naming changed. Check on large libraries that it does not re-query
  the ColabFold server for the identical protein per job.
- Template and RNA-MSA features are disabled (protein–ligand only).

## References

- [OpenDDE GitHub](https://github.com/aurekaresearch/OpenDDE) · [PyPI](https://pypi.org/project/opendde/)
