# W-36 · OpenDDE Co-folding Screen

![Domain: Drug Discovery](https://img.shields.io/badge/domain-drug--discovery-blue)

## Overview

Given a target protein and a library of candidate ligands, this workflow co-folds
each protein–ligand pair with [OpenDDE](https://github.com/aurekaresearch/OpenDDE)
(Aureka Research, Apache-2.0), an open-source all-atom biomolecular foundation
model, then returns a ranked shortlist with the predicted complex structures.

It mirrors the Boltz-2 screen (W-01): cheap CPU prep and ranking run locally; the
single expensive stage is co-folding. Unlike Boltz-2, OpenDDE has **no affinity
head** — see the ranking note below.

> **Preview release.** OpenDDE's maintainers warn that CLI flags, I/O formats and
> checkpoints may change between versions and that it is not meant for production
> pipelines. Pin the `opendde` version once you have a working run.

## Pipeline

```
prep (local, CPU)     target.fasta + ligands.smi ──► opendde_inputs.tar.gz  (jobs.json)
   │
predict (local)       [opendde msa]  →  opendde pred ──► predictions.tar.gz
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

Executor: `uv_python_environment` (Python 3.11, `opendde` from PyPI). The first run
downloads the OpenDDE checkpoint to `~/.cache/opendde` (override with
`OPENDDE_ROOT_DIR`).

Outputs land in `horus_workflow_results/results/`: `opendde_inputs.tar.gz`,
`predictions.tar.gz` (CIF structures + confidence JSONs) and `top_hits.csv`.

## Parameterization

| Parameter | Where | Default | Meaning |
|---|---|---|---|
| `use_msa` | `use_msa` boolean artifact (UI toggle) | `true` | Fetch a protein MSA via the public ColabFold MMseqs2 API before co-folding. Needs internet; turn off for an offline smoke test (poses are weaker). |
| `--sample` | `predict` command | `1` | Diffusion samples per job; `rank.py` keeps the best per ligand. |
| `modelSeeds` | `scripts/prep.py` | `[101]` | Seed(s) per job. |
| target | `predict` task | `local` | Switch to an SSH GPU target with `opendde[gpu]` (CUDA 12.6) for real screens. |

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
- `opendde msa` is called once on the full `jobs.json`; check on large libraries
  that it does not re-query the ColabFold server for the identical protein per job.
- Template and RNA-MSA features are disabled (protein–ligand only).

## References

- [OpenDDE GitHub](https://github.com/aurekaresearch/OpenDDE) · [PyPI](https://pypi.org/project/opendde/)
