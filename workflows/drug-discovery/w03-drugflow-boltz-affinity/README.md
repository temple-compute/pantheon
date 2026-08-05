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
download_checkpoint (shell: wget)                 Zenodo drugflow.ckpt (~170 MB)
                                                    ──► drugflow.ckpt
generate            (shell: docker run igashov/drugflow:0.0.3) kras.pdb + ref_ligand.sdf + drugflow.ckpt
                                                    ──► samples.sdf
prepare_inputs      (uv env: rdkit + biopython)   one YAML per molecule + smiles.json
                                                    ──► boltz_inputs/mol_1.yaml, ...
predict             (uv env: boltz)               boltz predict --use_msa_server
                                                    ──► predictions/affinity_*.json
rank                (shell, stdlib python3)       parse affinity_*.json, ΔG, sort
                                                    ──► deltaG_table.csv
```

`download_checkpoint` fetches the DrugFlow model checkpoint from Zenodo
automatically (skipped once `drugflow.ckpt` exists in the run dir), so the
workflow is self-contained apart from the target PDB, the reference ligand, and
the `igashov/drugflow:0.0.3` Docker image. `prepare_inputs` writes one Boltz
affinity YAML per molecule into a single folder, which `predict` feeds to a
single `boltz predict` call.

## Quick start

```bash
# One-time: uv, the runtime and plugins
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync

# One-time: the DrugFlow container image (the checkpoint is downloaded by the workflow)
docker pull igashov/drugflow:0.0.3

uv run horus run workflow.yaml
```

The checkpoint (~170 MB) is **not** committed to this repo; the
`download_checkpoint` task fetches it on the first run.

## Inputs / Outputs

**Inputs**
- `examples/kras.pdb` — target protein structure.
- `examples/kras_ref_ligand.sdf` — reference ligand; defines the pocket.

**Outputs**
- `drugflow.ckpt` — the DrugFlow checkpoint, downloaded by the workflow.
- `samples.sdf` — the generated molecules.
- `boltz_inputs/` — one Boltz affinity YAML per molecule.
- `smiles.json` — `{molecule_name: canonical_smiles}`.
- `predictions/` — Boltz-2 output, one `affinity_*.json` per molecule.
- `deltaG_table.csv` — columns `molecule, smiles, affinity_pred_value,
  binding_probability, deltaG_kcal_per_mol`, sorted by ascending ΔG (best first).

## Parameterization

| Where | Knob | Default |
|---|---|---|
| `download_checkpoint` command | Zenodo URL | `https://zenodo.org/records/14919171/files/drugflow.ckpt` |
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

**Checkpoint download.** `download_checkpoint` uses `wget`. If `wget` is not on
the target (macOS ships `curl` by default), swap the command for
`curl -L -o ${checkpoint} https://zenodo.org/records/14919171/files/drugflow.ckpt`.
The task skips automatically once `drugflow.ckpt` exists in the run directory.

**CPU vs GPU.** Both heavy stages default to CPU so the workflow runs anywhere;
generation and Boltz prediction are *slow* this way. On a GPU host, add
`--gpus all` to the `docker run` invocation in `generate`'s command and drop
`--device cpu` from the `generate.py` args; set `--accelerator gpu` on
`predict`. This needs the NVIDIA Container Toolkit on the host.

**Docker root ownership.** The container runs as **root** by default, so
`samples.sdf` ends up root-owned on the host. Add `--user "$(id -u):$(id -g)"`
to the `docker run` invocation to run as your uid/gid instead. Relatedly,
`generate`'s output is written at the run-dir root rather than in a
subdirectory: the task only bind-mounts `$(dirname ${samples})`, and a
not-yet-existing parent would be created by the daemon (as root) the first
time Docker sees it.

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
