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

| Stage | Task | Where | CPU / GPU | Defaults (3 x 1 ns) |
|---|---|---|---|---|
| 1 | `fetch_inputs` | local | shell, network | ~1 s |
| 2 | `build_system` | local | 1 CPU, ~2 GB | 4.5-7.5 min (measured) |
| 3 | `parameterize` | local | 2 CPU, ~3 GB | 0.5-1 min (measured) |
| 4 | `simulate` (map, 1 clone per replica) | Slurm GPU (`_gpu` target) | 1 GPU + 2 CPU each | 3 x 1 ns in parallel, a few minutes each on a modern GPU (estimate) |
| 5 | `analyze` | local | 1 CPU | ~30 s |

With the defaults the run is meant for one GPU per replica; setup takes
about 10 min on CPU. The system has about 24,000 atoms. On CPU OpenMM runs
at about 3.5 ns/day with 2 threads, so 1 ns per replica on the local target
takes roughly 7 h, and minimizing until converged takes about 6.5 min per
replica on 2 CPU threads (measured). A fresh run also builds the conda env once (about 2.2 GB,
a few minutes).

## Tools & Dependencies

Installed from conda-forge by `conda_env.yaml` (micromamba), pinned:
`openff-toolkit=0.19.0`, `openff-interchange=0.5.5`, `openmm=8.6.1`,
`openff-forcefields=2026.09.0` (provides `openff-2.3.0.offxml`),
`openff-amber-ff-ports=2025.09.0` (provides `ff14sb_off_impropers_0.0.4.offxml`),
`pdbfixer=1.12`, `mdtraj=1.11.2`, Python 3.12. The force fields are fixed: OpenFF Sage 2.3.0
(`openff-2.3.0.offxml`) for the ligand, water (TIP3P) and ions, and ff14SB
(`ff14sb_off_impropers_0.0.4.offxml`) for the protein. Sage 2.3.0 assigns ligand
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
- `analyze` also takes `replicas/` and reads only `trajectories/<i>/` for the
  current slots, so a leftover `trajectories/2/` from an earlier run with
  more replicas is ignored after lowering `n_replicas`.
- `simulate` tries CUDA, then OpenCL, then CPU with `--threads` (2), taking the
  first platform that creates a context; each fallback is logged. On the `_gpu`
  target `REQUIRE_GPU=1` is exported (`extra_sbatch_args`), so if no GPU
  platform works the clone fails at once instead of running `n_steps` on CPU into
  the time limit. BLAS/torch threads are capped with `OMP_NUM_THREADS=2`
  unless already set.

### Running on Slurm / GPU

1. Set the variables you need (see [Parameters](#parameters)).
2. In the `_gpu` anchor fill in `partition` and `account` (and `qos` if your
   site needs it).
3. On the `simulate` task change `target: *local` to `target: *gpu`. That is
   the only change; the conda env is built on the cluster on first use.

The anchor sets no `cpus_per_task` or `gres`: horus-slurm derives
`--cpus-per-task=2` and `--gres=gpu:1` from `simulate.resources`, so edit
`resources` to change them. `parameterize` clears old replica slots itself.

GPU build: conda-forge ships OpenMM's CUDA plugin whether or not the solving
host has a GPU, so one env built on a CPU node still runs CUDA on the GPU
node (PyTorch is CPU-only, but only NAGL charging in `parameterize` uses it).
The pinned solve picks CUDA 13 builds (`cuda-version 13.4`, `cuda-nvrtc
13.4`). OpenMM compiles its kernels at run time with nvrtc, and an older
driver can reject that code even inside the 13.x compat range, so pin
`cuda-version` in `conda_env.yaml` to at most the CUDA version `nvidia-smi`
reports on the GPU node (e.g. `cuda-version=12.9`, which resolves with the
same pins) and delete `.horus_conda_env/` so it is rebuilt. Not tested on a
GPU.

## Quick start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

cd workflows/omsf/w03-openff-protein-ligand-md

# Install the horus-runtime and plugins (one time)
uv sync

# Run with the defaults (needs micromamba on PATH). Set the simulate target
# to *gpu first (see above); on the local CPU target 3 x 1 ns takes hours.
uv run horus run workflow.yaml
```

Executor: `conda_python_environment` with `micromamba`. Running it again skips
every finished task.

## Input / Output

**Inputs**: the receptor PDB at `protein_url` and the ligand SDF at
`ligand_url`, downloaded at run time with `curl` (defaults: `5tbm_prepared.pdb`
and `PT2385.sdf` from openff-toolkit tag `0.19.0`). `file:///abs/path` URLs
work, so local files can be used. The receptor must already be prepared
(protonated, capped, no missing atoms) and the ligand must have explicit
hydrogens and a pose in the pocket; the ligand residue is named `UNK`.

**Outputs** in `horus_workflow_results/results/`:

| File | Renders as | Content |
|---|---|---|
| `rmsd.csv` | table | `replica, frame, time_ps, protein_ca_rmsd_A, ligand_rmsd_A` |
| `report.html` | HTML page with Mol* | per-replica summary and a 3D view of the final frame |
| `final_frame.pdb` | structure | protein + ligand, last frame of replica 0 |

Per replica, `horus_workflow_results/trajectories/<i>/` holds `trajectory.dcd`,
`log.csv` (energy, temperature, speed), `complex.pdb` and `seed`.

## Parameters

Root variables in `workflow.yaml`. Defaults are the production setup.

| id | default | meaning |
|---|---|---|
| `protein_url` | openff-toolkit 0.19.0 `toolkit_showcase/5tbm_prepared.pdb` | receptor PDB to download (`file:///abs/path` works) |
| `ligand_url` | openff-toolkit 0.19.0 `toolkit_showcase/PT2385.sdf` | ligand SDF to download (`file:///abs/path` works) |
| `n_replicas` | 3 | independent replicas, 1-100 |
| `n_steps` | 500000 | MD steps per replica (1 ns at 2 fs) |
| `padding_nm` | 1.0 | solvent padding around the protein, 0.5-5 nm |
| `ionic_strength_molar` | 0.15 | NaCl ionic strength, 0-2 M |
| `temperature_k` | 300 | thermostat temperature, 1-1000 K |
| `timestep_fs` | 2 | integrator timestep, 0.1-4 fs (H bonds constrained, no HMR) |
| `report_interval_steps` | 5000 | steps between DCD frames and `log.csv` rows (10 ps at 2 fs), 1 to `n_steps` |

Out-of-range values stop the task with a message naming the variable.
Fixed: Sage 2.3.0 + ff14SB, 1/ps friction, minimization until converged,
2 CPU threads per replica (`--threads` in the `simulate` args, ignored on
GPU). Seeds are `2026 + replica index`, stored in each slot's `seed` file.

To change a value, edit its `value:` in `workflow.yaml` (or in the tc-os
UI), **then** run `rm -rf params/`. Both steps are needed: tasks get the
value through `${id}`, but the skip check hashes `params/<id>.txt`, which
horus writes only when it is missing; without the `rm` every task reports
"Already complete" and the old results stay. Only the tasks downstream of
the changed variable re-run.

## Implementation Notes

- Ligand RMSD is measured after aligning on protein Cα atoms, without refitting
  the ligand, so it shows drift in the pocket. DCD frames are written
  unwrapped (`enforcePeriodicBox=False`) so molecules never jump a box length.
- The notebook's clash helper is reimplemented in a few lines of Python. It
  only removes waters within 1.5 Å of the ligand, never the protein or ions
  (dropping an ion would leave a net charge under PME), and prints how many it
  removed. For 5TBM no water clashes, since PDBFixer does not fill the buried
  pocket.
- Dynamics are NVT, like the notebook, which uses `runForClockTime(1 min)` with
  a reporter stride of 1000 on CUDA; we use a fixed length (and fixed seeds)
  so a run takes the same simulated time anywhere. Runs are not bitwise
  reproducible: CPU summation order varies with threads, so RMSDs differ in
  the last digits between runs.
- The integrator is `LangevinMiddleIntegrator` (the notebook uses
  `LangevinIntegrator`); same 300 K, 1/ps, 2 fs by default.
- The simulation is built from `interchange.to_openmm_system()` plus positions
  from `interchange.to_pdb()` (0.001 Å precision) instead of
  `interchange.to_openmm_simulation()`, so the system can be shipped to the
  map clones as `system.xml` and `complex.pdb`.
- Default length: 1 ns with a frame every 10 ps (upstream-like length, not
  the notebook's clock-time run).
- `build_system` is dominated by `Topology.from_pdb` on the solvated system,
  which is single-threaded.

## Open Questions

- GPU timings are estimates; this port was only run on CPU.
- No official container exists (see Tools & Dependencies).

## References

- Upstream notebook: [openff-toolkit 0.19.0 toolkit_showcase](https://github.com/openforcefield/openff-toolkit/tree/0.19.0/examples/toolkit_showcase) (MIT, © Open Force Field Initiative)
- [OMSF workflow directory](https://directory.omsf.io/workflows/)
- [OpenFF Toolkit docs](https://docs.openforcefield.org/projects/toolkit/) · [Interchange](https://docs.openforcefield.org/projects/interchange/) · [OpenMM](https://openmm.org)
