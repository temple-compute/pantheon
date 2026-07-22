# W-28 · DrugFlow + Boltz-2 Affinity

![Domain: Drug Discovery](https://img.shields.io/badge/domain-drug--discovery-blue)

## Overview

Given a protein and a reference ligand that defines a binding pocket, this
workflow generates novel drug-like molecules for that pocket with
[DrugFlow](https://github.com/LPDI-EPFL/DrugFlow) (LPDI-EPFL) and then scores
each generated molecule for binding affinity with
[Boltz-2](https://github.com/jwohlwend/boltz), returning a ΔG table ranked
best-first. It is a full de-novo design loop: propose, then score.

This **replaces the legacy `boltz-drugflow` Horus plugin**. The science logic
(sequence extraction, SDF parsing, Boltz YAML generation, affinity → ΔG
conversion) is lifted verbatim from that plugin's `run_boltz_affinity.py`
driver; what changes is the orchestration: instead of one monolithic block that
loops over molecules serially, the scoring stage is a `map:` fan-out with one
Boltz clone per molecule, running concurrently and independently retryable.

## Pipeline

```
generate       (docker: igashov/drugflow:0.0.3)   kras.pdb + ref_ligand.sdf + drugflow.ckpt
                                                    ──► samples.sdf
prepare_inputs (uv env: rdkit + biopython)         one dir per molecule + smiles.json
                                                    ──► boltz_inputs/000_mol_1/mol_1.yaml, ...
predict        (uv env: boltz, N concurrent clones) boltz predict --use_msa_server
                                                    ──► predict.gathered/<i>/prediction/
rank           (shell, stdlib python3)              parse affinity_*.json, ΔG, sort
                                                    ──► deltaG_table.csv
```

`predict` has no static inputs of its own: its `map:` block fans out over the
**child directories** of `prepare_inputs`'s `boltz_inputs/` folder, sorted by
name (hence the zero-padded `000_`, `001_`, … prefixes — clone order matches SDF
order), and gathers every clone's `prediction/` folder into `rank`'s
`predictions` input.

## Quick start

```bash
# One-time: uv, the runtime and plugins
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync

# One-time: the DrugFlow model checkpoint (~170 MB) and the DrugFlow image
wget -P examples/ https://zenodo.org/records/14919171/files/drugflow.ckpt
docker pull igashov/drugflow:0.0.3

uv run horus run workflow.yaml
```

The checkpoint is **not** committed to this repo — download it into `examples/`
before the first run.

## Inputs / Outputs

**Inputs**
- `examples/kras.pdb` — target protein structure.
- `examples/kras_ref_ligand.sdf` — reference ligand; defines the pocket.
- `examples/drugflow.ckpt` — DrugFlow model checkpoint (downloaded, see above).

**Outputs**
- `samples.sdf` — the generated molecules.
- `boltz_inputs/` — one directory per molecule, each with its Boltz affinity YAML.
- `smiles.json` — `{molecule_name: canonical_smiles}`.
- `deltaG_table.csv` — columns `molecule, smiles, affinity_pred_value,
  binding_probability, deltaG_kcal_per_mol`, sorted by ascending ΔG (best first).

## Parameterization

| Where | Knob | Default |
|---|---|---|
| `generate` command | `--n_samples` | `10` — number of molecules to generate |
| `generate` command | `--batch_size` | `32` |
| `generate` command | `--pocket_distance_cutoff` | `8.0` Å |
| `generate` command | `--device` | `cpu` (set `cuda:0` on a GPU box) |
| `generate` command | `--seed` | `42` |
| `predict` command | `--diffusion_samples` | `1` |
| `predict` command | `--accelerator` | `cpu` |
| `predict` command | `--use_msa_server` | on (public ColabFold server) |
| inputs | `examples/kras.pdb`, `examples/kras_ref_ligand.sdf` | swap for your own target |

## Implementation Notes

**CPU vs GPU.** Both heavy stages default to CPU so the workflow runs anywhere;
generation and Boltz prediction are *slow* this way. On a GPU host, uncomment
`gpus: all` on the `generate` docker executor and drop `--device cpu` from its
command; set `--accelerator gpu` on `predict`. The `gpus` field requires a
`horus-docker` that has it (currently on branch `feat/gpus-flag`) plus the
NVIDIA Container Toolkit.

**HPC / remote execution.** On a cluster without Docker, swap the `generate`
executor for Singularity via the (new, private) `horus-singularity` plugin:

```yaml
executor:
  kind: singularity
  image: /path/boltz.sif
  nv: true
```

and route any stage off the login node with `target: {kind: ssh_target}` or
`target: {kind: slurm_target}` instead of `target: {kind: local}`.

**Docker root ownership.** The container runs as **root** by default, so
`samples.sdf` and any directory the daemon creates end up root-owned on the
host. Set `user: "1000:1000"` on the docker executor to run as your uid/gid.
Relatedly, `generate`'s output is written at the run-dir root rather than in a
subdirectory: the docker executor bind-mounts each artifact's *parent*
directory, and a not-yet-existing parent would be created by the daemon as
root.

**Boltz input naming.** Each molecule gets its own directory (that is what the
map fans out over) and the YAML inside is named after the molecule, because the
YAML stem becomes Boltz's prediction name (`affinity_<stem>.json`) and is the
key `rank` joins against `smiles.json`.

**ΔG formula.** Boltz-2's `affinity_pred_value` is ~log10(IC50) with IC50 in µM.
Treating IC50 as a Kd proxy at 298 K:

```
ΔG ≈ 1.364 · (affinity_pred_value − 6)   kcal/mol
```

This is an approximation, good for **ranking** candidates, not an exact free
energy.

**MSAs.** The predict stage uses `--use_msa_server` (public ColabFold server),
so it needs outbound network access. The legacy plugin's local-database MSA mode
(`colabfold_search`) was not ported.

**Tests.** `scripts/rank.py` is stdlib-only and unit-tested:

```bash
uv run --no-project --with pytest pytest scripts/test_rank.py
```

## References

- [DrugFlow GitHub](https://github.com/LPDI-EPFL/DrugFlow) · checkpoint on [Zenodo](https://zenodo.org/records/14919171)
- [Boltz-2 GitHub](https://github.com/jwohlwend/boltz)
- Docker image: `igashov/drugflow:0.0.3`
