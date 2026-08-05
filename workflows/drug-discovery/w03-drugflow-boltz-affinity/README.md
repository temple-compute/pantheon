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
driver; what changes is the orchestration: instead of one monolithic block that
loops over molecules serially, the scoring stage is a `map:` fan-out with one
Boltz clone per molecule, running concurrently and independently retryable.

## Pipeline

```
generate       (shell: docker run igashov/drugflow:0.0.3) kras.pdb + ref_ligand.sdf + drugflow.ckpt
                                                    ──► samples.sdf
prepare_inputs (uv env: rdkit + biopython)         one dir per molecule + smiles.json
                                                    ──► boltz_inputs/000_mol_1/mol_1.yaml, ...
setup_boltz_env (uv env: boltz, runs once)         provisions <run>/.horus_boltz_env
predict        (uv env: N concurrent clones,       boltz predict --use_msa_server
                 sharing the boltz env above)       ──► predict.gathered/<i>/prediction/
rank           (shell, stdlib python3)              parse affinity_*.json, ΔG, sort
                                                    ──► deltaG_table.csv
```

`predict` has no static inputs of its own: its `map:` block fans out over the
**child directories** of `prepare_inputs`'s `boltz_inputs/` folder, sorted by
name (hence the zero-padded `000_`, `001_`, … prefixes — clone order matches SDF
order), and gathers every clone's `prediction/` folder into `rank`'s
`predictions` input.

`setup_boltz_env` builds the uv environment that holds Boltz into
`<run>/.horus_boltz_env`, and every `predict` clone reuses that exact
environment (each clone's working dir is `<run>/predict[N]`, so its
`../.horus_boltz_env` resolves to the same path). This makes the expensive
`boltz` install happen **once**, up front, instead of N clones racing to create
the same environment on the first run. After the first time it is a fast
"reuse existing env" no-op.

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
| `setup_boltz_env` executor | `requirements` | `[boltz]` — installed once into the shared env |
| `setup_boltz_env` executor | `environment_dir` | `../.horus_boltz_env` — shared by all predict clones |
| `predict` clones | `environment_dir` | `../.horus_boltz_env` — reuses the env from `setup_boltz_env` |
| `predict` command | `--diffusion_samples` | `1` |
| `predict` command | `--accelerator` | `cpu` |
| `predict` command | `--use_msa_server` | on (public ColabFold server) |
| inputs | `examples/kras.pdb`, `examples/kras_ref_ligand.sdf` | swap for your own target |

## Implementation Notes

**Why `generate` is a shell task that calls `docker run` itself, not a
`docker_executor` task.** Two things about `igashov/drugflow:0.0.3` and
`horus_docker` are easy to assume and both turn out to be wrong:

1. The image is *just* the DrugFlow Python dependencies (CUDA base + the pip
   packages in its own `/requirements.txt` — torch, rdkit, lightning, …). It
   does **not** contain the DrugFlow git repo, so there's no `src/generate.py`
   anywhere in the image to run.
2. `horus_docker`'s `docker_executor` has no automatic input/output mounting.
   Its `volumes:` map is a plain `dict[str, str]` that is never
   placeholder-substituted, so there is no way to reference a task's
   `${protein}`-style artifact paths in it — nothing bind-mounts a task's
   inputs into the container for you.

So `generate` uses `executor: {kind: shell}` and drives `docker run` from the
command string instead. `${protein}`, `${ref_ligand}`, `${checkpoint}`, and
`${samples}` are substituted by Horus to their **absolute host paths** before
the shell ever sees the command (this substitution happens for any
`CommandRuntime`, regardless of executor), so each one is bind-mounted at that
same absolute path inside the container (`-v ${protein}:${protein}:ro`, …) —
the path the DrugFlow CLI is given never needs translating between host and
container. The command also `git init` + `git fetch --depth 1 <sha>` +
`checkout`s the pinned DrugFlow commit into `/tmp/drugflow` inside the
container before invoking `generate.py`, since the image doesn't ship it.

**CPU vs GPU.** Both heavy stages default to CPU so the workflow runs anywhere;
generation and Boltz prediction are *slow* this way. On a GPU host, add
`--gpus all` to the `docker run` invocation in `generate`'s command and drop
`--device cpu` from the `generate.py` args; set `--accelerator gpu` on
`predict`. This needs the NVIDIA Container Toolkit on the host.

**Shared Boltz environment.** The `predict` map fans out N clones that all run
`boltz predict` concurrently. If each clone built its own uv environment you
would pay N full `boltz` installs; if they all built the *same* one
concurrently they would race (`rm -rf` + `uv venv` on one directory from many
processes), corrupting it on first run. The dedicated `setup_boltz_env` task
solves both: it installs Boltz once into `<run>/.horus_boltz_env` before the
map, and the clones reuse that path. `setup_boltz_env` declares no outputs, so
it always runs, but once the environment exists the executor's reuse branch is
a no-op. If you ever change the `requirements`, bump `recreate: true` on that
task (or point `environment_dir` somewhere fresh) to force a rebuild.

**Two ordering edges you must keep.** Both are non-obvious and the workflow
breaks without them on current horus-runtime (0.3.2):

1. `setup_boltz_env` is chained off `generate` (`generate →
   setup_boltz_env → predict`) because the scheduler only runs tasks that are
   ancestors/descendants of the trigger task. Left disconnected, the env-setup
   task is dropped from the run scope and the map silently never executes.
2. `predict → rank` explicitly gates the gather task behind the map expander.
   horus-runtime ≥0.3.2 stopped emitting this edge at load time for
   YAML-defined maps (0.2.1 did), so without it `rank` is dispatched
   concurrently with the expander and reads `predict.gathered/` before the
   expander pins it, failing with `Input artifact 'predictions' does not
   exist`.

Both edges are ordering-only (`transfer` carries no data); see the comments in
`workflow.yaml`.

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
`samples.sdf` ends up root-owned on the host. Add `--user "$(id -u):$(id -g)"`
to the `docker run` invocation to run as your uid/gid instead. Relatedly,
`generate`'s output is written at the run-dir root rather than in a
subdirectory: the task only bind-mounts `$(dirname ${samples})`, and a
not-yet-existing parent would be created by the daemon (as root) the first
time Docker sees it.

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
