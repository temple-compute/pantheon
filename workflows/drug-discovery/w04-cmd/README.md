# W-33 · cMD Replicas (AMBER)

![Domain: Drug Discovery](https://img.shields.io/badge/domain-drug--discovery-blue)

## Overview

Runs conventional molecular dynamics (cMD) with AMBER (pmemd/pmemd.cuda),
ported from [MolBioMedUAB/protocols](https://github.com/MolBioMedUAB/protocols)'
`MD/cMD/create_md_custom.sh`: minimize, heat, equilibrate (10 preproduction
steps), then run production MD in 10 ns chunks. This version fans that chain
out across N independent replicas in parallel via Horus's `horus_map`, splits
equilibration and production into two independent SLURM jobs per replica
(their own walltime, independently resumable), and replaces the original
script's bash `-m csuc|local|picard|slurm` machine branching with plain
configuration: SLURM target blocks and an AMBER environment script, all meant
to be saved as reusable library items per cluster.

The point on Horus: the original script generates one `script.sh` per run
and expects you to `sbatch` it yourself, once per replica, by hand. Here,
`prepare_replicas` renders the AMBER inputs once, `equilibrate` and `produce`
each fan out one SLURM job per replica concurrently, and `collect` waits for
all of them and summarizes the results -- all from one `horus run`.

## Pipeline

```
prepare_replicas (local, CPU)         input values + .prmtop/.inpcrd + templates.tar.gz
      |                                --> replicas/<i>/  (one self-contained slot per replica)
      |
horus_map equilibrate (N x SLURM, GPU) one clone per replica, run in parallel:
      |                                preproduction steps 1-10 (minimize/heat/equilibrate)
      |                                --> equilibrated_out/<i>/  (slot copied forward + results)
      |
horus_map produce (N x SLURM, GPU)     one clone per replica, run in parallel:
      |                                chunked production MD (scripts/production.sh)
      |                                --> produced_out/<i>/
      |
collect (local, CPU)                   --> results/summary.csv
```

## Quick start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install the horus-runtime and plugins (one time)
uv sync
# or: pip install horus-runtime horus-slurm horus-environments

# Run the workflow
uv run horus run workflow.yaml
```

Uses the `shell` executor throughout (`prepare_replicas`/`collect` run
locally; `equilibrate`/`produce`'s SLURM targets submit via sbatch, see
`horus-slurm`). No conda/Docker/Singularity involved -- AMBER is expected to
already be on the target via the `amber_env` module line.

## Inputs / Outputs

**Inputs** (value artifacts, editable in the tc-os UI):
- `last_residue` -- last residue number of protein + substrate, for the
  `:1-last_residue` restraint masks. Default `0` = auto: read from the
  prmtop as the last residue that isn't water or a monovalent ion (the task
  log prints the value and residue name; **129** for the example system).
  Set a number to override.
- `temperature` -- target temperature in K (default 300).
- `length_ns` -- production length in ns, rounded up to the next multiple
  of 10 (default 200).
- `n_replicas` -- number of independent replicas to fan out (default 3).
- `amber_env` -- dropdown of the AMBER module line per cluster (Picard,
  CSUC, Local).

Plus `examples/system.prmtop` / `examples/system.inpcrd` -- a real, solvated
and ionized AMBER system: hen egg-white lysozyme (PDB 1AKI), apo, 129
protein residues + Cl- + TIP3P water, 18,019 atoms total. Reused from this
repo's own [`w09-amber-protein-md-setup`](../../bioexcel_building_blocks/w09-amber-protein-md-setup)
output (`structure.ions.parmtop`/`.crd`), so it's already a byproduct of a
real AMBER topology-build pipeline, not synthetic. `1_min` (the first
preprod step) was run against it directly with `sander` as a sanity check --
converged (-20.6k -> -52.8k kcal/mol) with the `:1-129` restraint applied as
expected. Swap in your own system's `.prmtop`/`.inpcrd` for a different target; check the auto
`last_residue` in the task log.

**Output** -- `results/summary.csv`: one row per replica (chunks completed,
last restart file, trajectory file count/size), plus each replica's
equilibration output under `horus_workflow_results/equilibrated_out/<i>/`
and production output (`.rst`/`.nc`/`.mdout`/`.mdinf` chunks) under
`horus_workflow_results/produced_out/<i>/`.

## Configuration (the reusable/library-item parts)

- **`amber_env`** -- the module line written to each slot's `amber.sh`,
  sourced before every `pmemd`/`pmemd.cuda` call. Replaces the original
  script's `-m` machine flag (`csuc`/`local`/`picard`/`slurm`, each a
  different `module load` line). Add an option for a new site.
- **The `_gpu_equilibrate` / `_gpu_produce` target anchors** at the top of
  `workflow.yaml` -- two `kind: slurm` blocks (partition, account,
  `gres: gpu:1`, `mem: 16G`, walltime). One SLURM allocation per replica per
  phase. Give `mem` a unit: a bare number is MB to Slurm.
  Split so each phase gets its own walltime budget instead of sharing one
  job's, unlike the original script's single `#SBATCH --gres=gpu:1` job.
  Fill in `partition`/`account` for your site, or save these blocks as
  library items.

## Task granularity (equilibrate + produce, not per-AMBER-step)

Equilibration (preproduction steps 1-10) and production run as two separate
Horus tasks / SLURM jobs per replica (`equilibrate[i]`, then `produce[i]`),
each running its whole phase in one shot (`scripts/equilibrate.sh`,
`scripts/production.sh`). This gives real phase separation -- independent
walltimes, and a re-run can skip a replica's finished equilibration without
re-touching its production -- without going further to one task per AMBER
step, which isn't possible with the current primitive: `horus_map` clones
itself once per item as a plain `horus_task` with one runtime/executor/
target, so a map's per-item body is always flat, never a multi-step chain
(`src/horus_builtin/workflow/map.py` in horus-runtime). `equilibrate`'s
command works around this only by copying its own item forward
(`cp -r ${slot}/. ${equilibrated}/`) before running, so `produce` -- mapping
over *its* output -- receives an equally self-contained item and needs no
input from `prepare_replicas` at all.

(An earlier draft of this workflow targeted horus-runtime 0.3.x, whose
`map:`/`gather:` YAML sugar *did* let a map's per-item template be a
`subworkflow`, chaining tasks -- which would have made per-AMBER-step
granularity possible. That was dropped in 0.4 -- see `horus_map: an ordinary
task that runs its own body once per item` in the current `map.py`
docstring -- specifically because that composition let the gather task race
ahead of the subworkflow's real inner tasks and collect an empty result,
reproducible with a minimal 2-step example. This version targets current
horus-runtime (`>=0.4.0`) and its `kind: horus_map` syntax; there is no
`map:`/`gather:` block or subworkflow nesting to revert to.)

## Live monitoring (while a replica runs)

Declared outputs (`equilibrated`, `produced`) only upload when a task
succeeds, so a long or failing run would otherwise show nothing. To cover
that, `scripts/live_monitor.sh` (copied into every slot) runs beside pmemd
in both `equilibrate` and `produce` and writes a small digest to
`$HORUS_SIDE_ARTIFACTS_DIR`. Horus pulls that directory every ~30 s while the
task runs, and once more when it fails or is cancelled. The digest appears
in each replica's **side products** in the UI:

| File | What | Viewer |
|---|---|---|
| `current_mdout.log` | newest mdout (AMBER errors end up here) | text |
| `current_mdinfo.txt` | newest mdinfo (ns/day, ETA, current energies) | text |
| `energies.csv` / `energies.svg` | every MD energy record so far; EPtot/Temp/Density plot with step boundaries | table / image |
| `trajectory.pdb` | newest `.nc`, solvent and H stripped, at most `LIVE_FRAMES` models | Mol* (plays as a trajectory) |
| `rmsd.csv` | CA RMSD of those frames against the first one | table |

- **Settings:** `LIVE_INTERVAL` (default 60 s) and `LIVE_FRAMES` (default 50).
  Export them in the task environment.
- **Outside Horus:** the monitor is a no-op (`HORUS_SIDE_ARTIFACTS_DIR` unset).
- **If it goes bad:** cancel the run from the UI. That `scancel`s the SLURM
  jobs, and the final digest is still uploaded.
- **Self-check:** `bash scripts/live_monitor.sh --selftest` checks the mdout
  parser and the plot. Trajectory frames need `cpptraj`, which AmberTools
  provides once the AMBER module is loaded.

## Verification without AMBER

`env/amber-stub.sh` is a drop-in test double for the AMBER module: it defines
`pmemd`/`pmemd.cuda` as shell functions that touch their declared output
files instead of loading a real AMBER module, so the whole DAG (both
fan-outs, the copy-forward between them, the final summary) can be exercised
with no AMBER/SLURM installation at all -- the stub never parses
`examples/system.prmtop`/`.inpcrd`'s contents, only Horus's file-transfer
step needs them to exist.

To run the smoke test: set the `amber_env` value to
`. /absolute/path/to/env/amber-stub.sh` and flip both
`_gpu_equilibrate`/`_gpu_produce` anchors to `{kind: local}`, then
`uv run horus run workflow.yaml`. `results/summary.csv` should report one
row per replica with
`chunks_completed` matching `ceil(length_ns / 10)`.

Two scripts also carry a `--self-test` self-check (`prepare_replicas.py`,
`collect.py`) that exercises their core logic directly, no workflow run
needed.

## References

- [MolBioMedUAB/protocols](https://github.com/MolBioMedUAB/protocols) --
  `MD/cMD/create_md_custom.sh`, the source protocol this workflow ports.
