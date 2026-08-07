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
generate            (singularity on slurm)        kras.pdb + ref_ligand.sdf + drugflow.ckpt
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
is not published as a package, so the container supplies its dependencies but
not the code itself). Both are skipped once their output exists. `prepare_inputs` writes one Boltz affinity YAML per molecule into a
single folder, which `predict` feeds to a single `boltz predict` call.

## Quick start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install the horus-runtime and plugins (one time)
uv sync
# or: pip install horus-runtime horus-environments horus-singularity horus-slurm

# Build the DrugFlow image once, on the cluster
#   see boltz-drugflow/examples/build_drugflow_sif.sh
# then set the `drugflow_sif` artifact's `path:` at the top of workflow.yaml

# Run the workflow
uv run horus run workflow.yaml
```

Run this from a Slurm login node: `generate` submits an sbatch job that runs
`singularity exec --nv`, so you need `sbatch` and `singularity` (or `apptainer`)
reachable there, plus the `drugflow.sif` built beforehand — the executor has no
build or pull step. The other stages run locally and still need a conda-family
tool only if you take the conda fallback below. The checkpoint (~170 MB) is
**not** committed to this repo; `download_checkpoint` fetches it on the first
run.

Outputs land in `horus_workflow_results/`, `deltaG_table.csv` under its
`results/`.

> **macOS / Apple Silicon:** neither path runs `generate` locally on a Mac —
> there is no Singularity, and `conda_env.yaml` does **not** solve on `osx-arm64`
> (`pyg=2.5.1`, `ProDy=2.4.0` and `pytorch=2.2.1` have no arm64 builds). Use the
> cluster, or the Docker note under Implementation Notes.

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
| `drugflow_sif` artifact | `path` | path to `drugflow.sif` on the cluster — **must be set**; `generate` reads it as `${drugflow_sif}` |
| `generate` executor | `exe` | `singularity` (set the cluster's absolute path if it isn't on `PATH`) |
| `generate` executor | `nv` | `true` — drop to `false` for a CPU-only run |
| `generate` target | `gres`, `time_limit` | `gpu:1`, `02:00:00`; add `partition`/`account`/`qos` if your Slurm needs them |
| `generate` command | `--n_samples` | `10` — number of molecules to generate |
| `generate` command | `--batch_size` | `32` |
| `generate` command | `--pocket_distance_cutoff` | `8.0` Å |
| `generate` command | `--device` | `cuda:0` (set `cpu`, and `nv: false`, without a GPU) |
| `generate` command | `--seed` | `42` |
| `generate` command | `--molecule_size` | unset — max atoms per molecule; add e.g. `--molecule_size 15,20` for a range |
| `generate` command | `--n_steps` | unset — denoising steps; add to override the model default |
| `generate` command | `--filter` | off — add the flag to resample until quality filters pass |
| `predict` command | `--diffusion_samples` | `1` |
| `predict` command | `--accelerator` | `cpu` |
| `predict` command | `--use_msa_server` | on (public ColabFold server) |
| inputs | `examples/kras.pdb`, `examples/kras_ref_ligand.sdf` | swap for your own target |

## Implementation Notes

**Why `generate` runs in Singularity, on Slurm.** The heavy stage wants a GPU,
and GPUs live on the cluster — where the Docker daemon is not available but
Singularity/Apptainer is. `generate` therefore uses `horus-singularity`'s
`kind: singularity` executor with a `kind: slurm` target, so the container runs
inside an sbatch job. The `.sif` is built once, off-workflow, with
`boltz-drugflow/examples/build_drugflow_sif.sh`
(`singularity build drugflow.sif docker://igashov/drugflow:0.0.3`); the executor
has no build or pull step, so the image must already exist on the cluster.

**The image path is a declared artifact, not an executor field.** `drugflow_sif`
sits in the `artifacts:` block at the top of `workflow.yaml`, alongside `protein`
and `ref_ligand`, and `generate` reads it as `image: ${drugflow_sif}`. Its
location is site-specific, so committing it inside the task would mean the
workflow always carries a path that is wrong for everyone but its author; this
way every path an operator has to set lives in one block. (Needs
`horus-singularity >= 0.3.0`, which added placeholder substitution on `image` —
a Docker image is a registry tag with nothing to substitute, a Singularity image
is a file.)

Three things about this that are easy to get wrong:

1. **The image ships DrugFlow's dependencies, not its code.** DrugFlow isn't
   packaged, so `src/generate.py` comes from the separate `fetch_source` stage
   and the checkout has to be visible inside the container. The executor
   auto-binds every input/output artifact's parent directory at its own path,
   which covers it.
2. **Singularity does no path translation.** Unlike a Docker port of this stage,
   which would rewrite paths to `/work` and `/checkpoint`, a bound host path is
   visible inside the container at the same location. So every `${...}` in the
   command is valid on both sides and needs no rewriting. Add an explicit
   `binds:` entry only for a path outside the task working directory (a shared
   checkpoint on `/scratch`, say).
3. **`cd ${drugflow_src}` is still required**, because `src/generate.py` uses
   `from src... import` and needs the repo root as its working directory. Don't
   also set the executor's `working_dir:` (`--pwd`) — the `cd` is enough, and
   the two interact confusingly.

**Conda fallback (no cluster, or macOS).** The stage previously ran under
`kind: conda_python_environment`, and that still works anywhere with a GPU or
enough patience:

```yaml
executor:
  kind: conda_python_environment
  conda: micromamba
  environment_dir: "../.horus_drugflow_env"
  environment_file: conda_env.yaml     # conda_env_gpu.yaml on an NVIDIA node
target:
  kind: local
```

`conda_env.yaml` is upstream's own `environment.yaml` with the two CUDA pins
relaxed to CPU builds; `conda_env_gpu.yaml` keeps CUDA 12.1. Both were checked
with `micromamba create --dry-run` on `linux-64`, and both add one pin upstream
doesn't have: `setuptools<81`. ProDy 2.4.0 does `import pkg_resources`, which
setuptools removed after deprecating it in 81, so an unpinned solve installs a
setuptools that makes `import prody` (and therefore `src/generate.py`) fail with
`ModuleNotFoundError: No module named 'pkg_resources'`.

Note `conda_env.yaml` has **no `osx-arm64` solution** (`pyg=2.5.1`, `ProDy=2.4.0`
and `pytorch=2.2.1` have no arm64 builds), so on Apple Silicon neither the conda
nor the Singularity path works locally — use the cluster, or Docker with
`--platform linux/amd64` via `horus-docker`'s `kind: docker` executor (its
`volumes:` map *is* placeholder-substituted, so it can mount `${protein}` and
friends directly; set `user:` or the container leaves root-owned outputs behind).

**Checkpoint download.** `download_checkpoint` downloads to `drugflow.ckpt.part`
and only `mv`s it into place on success — a truncated file left at the final
path would satisfy `skip_if_complete` and be reused as a corrupt checkpoint on
every later run. The task skips once `drugflow.ckpt` exists in the run directory.

**CPU vs GPU.** `generate` defaults to GPU (`nv: true`, `--device cuda:0`,
`gres: gpu:1`); `--nv` and `--device` must agree, or the container either can't
see the driver stack or won't ask for it. `predict` still defaults to
`--accelerator cpu` so it runs anywhere — set `gpu` there too if you move it
onto the cluster. Both stages are *slow* on CPU.

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
