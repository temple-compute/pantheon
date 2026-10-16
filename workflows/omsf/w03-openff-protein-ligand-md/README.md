# W-39 · OpenFF Protein-Ligand MD

![Domain: OMSF](https://img.shields.io/badge/domain-omsf-blue)

## Overview

A Horus port of the Open Force Field [Toolkit Showcase](https://github.com/openforcefield/openff-toolkit/tree/0.19.0/examples/toolkit_showcase)
(`toolkit_showcase.ipynb`, openff-toolkit 0.19.0), listed in the
[OMSF workflow directory](https://directory.omsf.io/workflows/). It takes the
HIF-2α PAS-B domain (PDB 5TBM) with the inhibitor PT2385, solvates it,
parameterizes protein with ff14SB and ligand, water and ions with OpenFF Sage
2.3.0 through Interchange, then runs independent OpenMM replicas and reports
protein and ligand RMSD.

The notebook is split into five tasks. Setup is cheap CPU work. MD is the
only heavy step, so it is a `horus_map` over replica slots that can run on a
GPU target while everything else stays local.

## Compute Pattern

| Stage | Task | Where | CPU / GPU | Smoke (measured, this host) | Full (estimate) |
|---|---|---|---|---|---|
| 1 | `fetch_inputs` | local | shell, network | ~1 s | ~1 s |
| 2 | `build_system` | local | 1 CPU, ~2 GB | 4.5-7.5 min | same |
| 3 | `parameterize` | local | 2 CPU, ~3 GB | 0.5-1 min | same |
| 4 | `simulate` (map, 1 clone per replica) | smoke: local; full: Slurm GPU | 2 CPU threads each, or 1 GPU | 2 x 5 ps, 5-6 min in parallel | 3 x 1 ns, ~10-20 min each on a modern GPU |
| 5 | `analyze` | local | 1 CPU | ~5 s | ~30 s |

Smoke total: 14.7 min from scratch on a shared 16-core host (load average ~30), env already built. The system has about 24,000 atoms. On CPU OpenMM runs at about 3.5 ns/day
with 2 threads, so the full profile is not meant for CPU. A fresh run also
builds the conda env once (about 2.2 GB, a few minutes).

## Tools & Dependencies

Installed from conda-forge by `conda_env.yaml` (micromamba), pinned:
`openff-toolkit=0.19.0`, `openff-interchange=0.5.5`, `openmm=8.6.1`,
`openff-forcefields=2026.09.0` (provides `openff-2.3.0.offxml`),
`openff-amber-ff-ports=2025.09.0` (provides `ff14sb_off_impropers_0.0.4.offxml`),
`pdbfixer=1.12`, `mdtraj=1.11.2`, Python 3.12. Sage 2.3.0 assigns ligand
charges with OpenFF NAGL (pulled in by openff-toolkit), so AmberTools and
OpenEye are not needed.

There is no official OpenFF container, so unlike the other OMSF ports there
is no one-field swap to an upstream image: the executor is the pinned conda
env. If you build your own image from `conda_env.yaml`, note that the
`docker` and `singularity` executors only accept `kind: command` runtimes, so
the four `python_script` tasks would need to become
`python scripts/<name>.py ...` commands as well.

## Horus Configuration

```
fetch_inputs ─► build_system ─► parameterize ─► simulate[0..n] ─► analyze
   curl          PDBFixer +       Interchange     horus_map:        mdtraj RMSD,
                 OpenFF Topology  system.xml,     OpenMM minimize   Mol* report
                                  replicas/<i>/   + Langevin MD
```

- All tasks except `fetch_inputs` share one conda env at
  `horus_workflow_results/.horus_conda_env` (`environment_dir: ../../.horus_conda_env`,
  relative to each task's `<results>/<task-id>/<run-id>` working dir).
- `parameterize` writes `replicas/<i>/{system.xml,complex.pdb,seed}`; the
  `simulate` map clones itself once per slot and writes `trajectories/<i>/`.
- `simulate` picks the CUDA platform when OpenMM can load it, otherwise CPU
  with `--threads` (2). BLAS/torch threads are capped with `OMP_NUM_THREADS=2`
  unless already set.

### Running full on Slurm / GPU

1. Set the `profile` artifact to `full` (UI dropdown, or `value: full` on the
   root `profile` artifact in `workflow.yaml`). Tasks get the value through
   `${profile}`, which follows the authored value; `params/profile.txt` is
   written once and not read back, so editing that file does not switch it.
2. In the `_gpu` anchor fill in `partition` and `account` (and `qos` if your
   site needs it).
3. On the `simulate` task change `target: *local` to `target: *gpu`. That is
   the only change; the conda env is built on the cluster on first use.

`resources.gpus: 1` is already set on `simulate`; `gres: gpu:1` in the anchor
requests it from Slurm. Finished tasks are skipped, so after a smoke run
delete `horus_workflow_results/` except `.horus_conda_env/` before running
full (or the other way round). `parameterize` clears old replica slots itself.

GPU build: conda-forge ships OpenMM's CUDA plugin whether or not the solving
host has a GPU, so one env built on a CPU node still runs CUDA on the GPU
node (PyTorch is CPU-only, but only NAGL charging in `parameterize` uses it).
The pinned solve picks CUDA 13 builds, which need an NVIDIA driver >= 580. For
older drivers add `cuda-version=12.9` to `conda_env.yaml` (this resolves with
the same pins) and delete `.horus_conda_env/` so it is rebuilt.

## Quick start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install the horus-runtime and plugins (one time)
uv sync

# Run the smoke profile (needs micromamba on PATH)
uv run horus run workflow.yaml
```

Executor: `conda_python_environment` with `micromamba`. Running it again skips
every finished task.

## Input / Output

**Inputs** (downloaded at run time from openff-toolkit tag `0.19.0`):
`5tbm_prepared.pdb` and `PT2385.sdf`.

**Outputs** in `horus_workflow_results/results/`:

| File | Renders as | Content |
|---|---|---|
| `rmsd.csv` | table | `replica, frame, time_ps, protein_ca_rmsd_A, ligand_rmsd_A` |
| `report.html` | HTML page with Mol* | per-replica summary and a 3D view of the final frame |
| `final_frame.pdb` | structure | protein + ligand, last frame of replica 0 |

Per replica, `horus_workflow_results/trajectories/<i>/` holds `trajectory.dcd`,
`log.csv` (energy, temperature, speed), `complex.pdb` and `seed`.

## Parameterization

| Parameter | Where | smoke | full |
|---|---|---|---|
| `profile` | `profile` choice artifact | default | 1 ns runs |
| replicas | `REPLICAS` in `scripts/parameterize.py` | 2 | 3 |
| MD steps / frame interval | `PROFILES` in `scripts/simulate.py` | 2,500 / 250 (5 ps) | 500,000 / 5,000 (1 ns) |
| minimizer iterations | `PROFILES` in `scripts/simulate.py` | 200 | until converged |
| CPU threads per replica | `--threads` in `simulate` args | 2 | 2 (ignored on CUDA) |

Seeds are `2026 + replica index`, stored in each slot's `seed` file.

## Implementation Notes

- Ligand RMSD is measured after aligning on protein Cα atoms, without refitting
  the ligand, so it shows drift in the pocket. DCD frames are written
  unwrapped (`enforcePeriodicBox=False`) so molecules never jump a box length.
- The notebook's clash helper is reimplemented in a few lines of numpy. It
  only removes waters and ions within 1.5 Å of the ligand, never the protein.
  For 5TBM no solvent clashes, since PDBFixer does not fill the buried pocket.
- Dynamics are NVT, like the notebook, which uses `runForClockTime(1 min)`;
  we use a fixed step count so runs are reproducible.
- `build_system` is dominated by `Topology.from_pdb` on the solvated system,
  which is single-threaded.

## Open Questions

- Full-profile GPU timings are estimates; this port was only run on CPU.
- No official container exists (see Tools & Dependencies).

## References

- Upstream notebook: [openff-toolkit 0.19.0 toolkit_showcase](https://github.com/openforcefield/openff-toolkit/tree/0.19.0/examples/toolkit_showcase) (MIT, © Open Force Field Initiative)
- [OMSF workflow directory](https://directory.omsf.io/workflows/)
- [OpenFF Toolkit docs](https://docs.openforcefield.org/projects/toolkit/) · [Interchange](https://docs.openforcefield.org/projects/interchange/) · [OpenMM](https://openmm.org)
