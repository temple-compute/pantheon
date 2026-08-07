# W-32 · DrugFlow + Boltz-2 Affinity

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
driver, restaged as a plain linear Horus workflow: one stage per step, each
independently resumable, no fan-out.

## Pipeline

```
download_checkpoint (shell: curl)                 Zenodo drugflow.ckpt (~170 MB)
                                                    ──► drugflow.ckpt
fetch_source        (shell: git)                  DrugFlow repo @ pinned commit
                                                    ──► drugflow_src/
generate            (conda env: conda_env.yaml)   kras.pdb + ref_ligand.sdf + drugflow.ckpt
                                                    ──► results/samples.sdf
prepare_inputs      (uv env: rdkit + biopython)   one YAML per molecule + smiles.json
                                                    ──► results/boltz_inputs/mol_1.yaml, ...
predict             (uv env: boltz)               boltz predict --use_msa_server
                                                    ──► results/predictions/affinity_*.json
rank                (shell, stdlib python3)       parse affinity_*.json, ΔG, sort
                                                    ──► results/deltaG_table.csv
```

`download_checkpoint` and `fetch_source` make the workflow self-contained apart
from the target PDB and the reference ligand: the first pulls the model
checkpoint from Zenodo, the second clones DrugFlow at a pinned commit (the code
is not published as a package, so the conda environment supplies its
dependencies but not the code itself). Both are skipped once their output
exists. `prepare_inputs` writes one Boltz affinity YAML per molecule into a
single folder, which `predict` feeds to a single `boltz predict` call.

## Quick start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install the horus-runtime and plugins (one time)
uv sync
# or: pip install horus-runtime horus-environments

# Run the workflow
uv run horus run workflow.yaml
```

Needs a conda-family tool (`micromamba`, `mamba`, or `conda`) on `PATH` — the
`generate` stage builds a conda environment from `conda_env.yaml` (~520 MB,
built once into `.horus_drugflow_env/` next to `workflow.yaml` and reused). The
checkpoint (~170 MB) is **not** committed to this repo; `download_checkpoint`
fetches it on the first run.

Outputs land in `horus_workflow_results/`, `deltaG_table.csv` under its
`results/`.

> **macOS / Apple Silicon:** `conda_env.yaml` does **not** solve on `osx-arm64`
> — `pyg=2.5.1`, `ProDy=2.4.0` and `pytorch=2.2.1` have no arm64 builds. Use the
> Docker fallback below for the `generate` stage on a Mac.

## Inputs / Outputs

**Inputs**
- `examples/kras.pdb` — target protein structure.
- `examples/kras_ref_ligand.sdf` — reference ligand; defines the pocket.

**Outputs** (all under `horus_workflow_results/`)
- `drugflow.ckpt` — the DrugFlow checkpoint, downloaded by the workflow.
- `drugflow_src/` — DrugFlow source at the pinned commit.
- `results/samples.sdf` — the generated molecules.
- `results/boltz_inputs/` — one Boltz affinity YAML per molecule.
- `results/smiles.json` — `{molecule_name: canonical_smiles}`.
- `results/predictions/` — Boltz-2 output, one `affinity_*.json` per molecule.
- `results/deltaG_table.csv` — columns `molecule, smiles, affinity_pred_value,
  binding_probability, deltaG_kcal_per_mol`, sorted by ascending ΔG (best first).

## Parameterization

| Where | Knob | Default |
|---|---|---|
| `download_checkpoint` command | Zenodo URL | `https://zenodo.org/records/14919171/files/drugflow.ckpt` |
| `fetch_source` command | pinned DrugFlow commit | `ed684167…` |
| `generate` executor | `environment_file` | `conda_env.yaml` (swap for `conda_env_gpu.yaml` on an NVIDIA node) |
| `generate` command | `--n_samples` | `10` — number of molecules to generate |
| `generate` command | `--batch_size` | `32` |
| `generate` command | `--pocket_distance_cutoff` | `8.0` Å |
| `generate` command | `--device` | `cpu` (set `cuda:0` on a GPU box) |
| `generate` command | `--seed` | `42` |
| `generate` command | `--molecule_size` | unset — max atoms per molecule; add e.g. `--molecule_size 15,20` for a range |
| `generate` command | `--n_steps` | unset — denoising steps; add to override the model default |
| `generate` command | `--filter` | off — add the flag to resample until quality filters pass |
| `predict` command | `--diffusion_samples` | `1` |
| `predict` command | `--accelerator` | `cpu` |
| `predict` command | `--use_msa_server` | on (public ColabFold server) |
| inputs | `examples/kras.pdb`, `examples/kras_ref_ligand.sdf` | swap for your own target |

## Implementation Notes

**Why `generate` runs in conda, not Docker.** DrugFlow does not need a
container. Upstream ships its own `environment.yaml`, and `gnina` — the only
external binary in its install instructions — is required solely for optional
docking-score metrics, not for generation. `conda_env.yaml` here is that file
with the two CUDA pins relaxed to CPU builds; `conda_env_gpu.yaml` keeps CUDA
12.1. Both were checked with `micromamba create --dry-run` on `linux-64`, and
both add one pin upstream doesn't have: `setuptools<81`. ProDy 2.4.0 does
`import pkg_resources`, which setuptools removed after deprecating it in 81, so
an unpinned solve installs a setuptools that makes `import prody` (and
therefore `src/generate.py`) fail with `ModuleNotFoundError: No module named
'pkg_resources'`.

The environment supplies the dependencies but not the code (DrugFlow isn't
packaged), hence the separate `fetch_source` stage. `generate`'s command
`cd`s into that checkout because `src/generate.py` uses `from src... import`
and so needs the repo root as its working directory; every `${...}` resolves to
an absolute path, so nothing else is affected by the `cd`.

**Docker fallback (macOS / arm64).** `conda_env.yaml` has no `osx-arm64`
solution, so on a Mac swap `generate`'s executor back to `{kind: shell}` and its
command to:

```yaml
command: >-
  docker run --rm --platform linux/amd64
  --user "$(id -u):$(id -g)"
  -v ${drugflow_src}:${drugflow_src}:ro
  -v ${protein}:${protein}:ro
  -v ${ref_ligand}:${ref_ligand}:ro
  -v ${checkpoint}:${checkpoint}:ro
  -v $(dirname ${samples}):$(dirname ${samples})
  igashov/drugflow:0.0.3
  sh -c "cd ${drugflow_src} && python src/generate.py
  --protein ${protein} --ref_ligand ${ref_ligand}
  --checkpoint ${checkpoint} --output ${samples}
  --n_samples 10 --batch_size 32 --pocket_distance_cutoff 8.0
  --device cpu --seed 42"
```

after a `docker pull igashov/drugflow:0.0.3`. The image holds *only* DrugFlow's
pip dependencies and no repo, so `${drugflow_src}` still has to be mounted. It is
a plain shell task rather than `horus_docker`'s `docker_executor` because that
executor's `volumes:` map is never placeholder-substituted, so it can't see
per-task artifact paths; a shell task gets absolute *host* paths for every
`${...}`, so mounting each at its own path means the CLI args need no
translation. `--user` is not optional: without it the container leaves
root-owned outputs on the host.

**Checkpoint download.** `download_checkpoint` downloads to `drugflow.ckpt.part`
and only `mv`s it into place on success — a truncated file left at the final
path would satisfy `skip_if_complete` and be reused as a corrupt checkpoint on
every later run. The task skips once `drugflow.ckpt` exists in the run directory.

**CPU vs GPU.** Both heavy stages default to CPU so the workflow runs anywhere;
generation and Boltz prediction are *slow* this way. On an NVIDIA node, point
`generate`'s `environment_file:` at `conda_env_gpu.yaml` and change
`--device cpu` to `--device cuda:0`; set `--accelerator gpu` on `predict`.

**Boltz input naming.** Each molecule's YAML is named after the molecule,
because the YAML stem becomes Boltz's prediction name (`affinity_<stem>.json`)
and is the key `rank` joins against `smiles.json`.

**ΔG formula.** Boltz-2's `affinity_pred_value` is ~log10(IC50) with IC50 in µM.
Treating IC50 as a Kd proxy at 298 K:

```
ΔG ≈ 1.364 · (affinity_pred_value − 6)   kcal/mol
```

This is an approximation, good for **ranking** candidates, not an exact free
energy.

**MSAs.** The predict stage uses `--use_msa_server`, i.e. the *public* ColabFold
server, so it needs outbound network access from wherever `predict` runs and is
subject to that server's rate limits. The legacy plugin defaulted to the other
mode: a local `colabfold_search` against an on-disk database. That was not
ported because it needs a second environment — `boltz` requires `numpy<2`
while `colabfold` requires `numpy>=2.0.2`, so the two cannot share one env — plus
a multi-hundred-GB sequence database. On a cluster without outbound access this
is the stage that will fail.

**Tests.** `scripts/rank.py` is stdlib-only and unit-tested:

```bash
uv run --no-project --with pytest pytest scripts/test_rank.py
```

## References

- [DrugFlow GitHub](https://github.com/LPDI-EPFL/DrugFlow) · checkpoint on [Zenodo](https://zenodo.org/records/14919171)
- [Boltz-2 GitHub](https://github.com/jwohlwend/boltz)
- Docker image (macOS fallback only): `igashov/drugflow:0.0.3`
