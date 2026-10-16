# W-37 · OpenFE Relative Binding Free Energies (TYK2)

![Domain: OMSF](https://img.shields.io/badge/domain-omsf-blue)

## Overview

Relative binding free energies (RBFE) for a congeneric TYK2 inhibitor series with
[OpenFE](https://openfree.energy). This is a native Horus port of two entries in the
[OMSF workflow directory](https://directory.omsf.io/workflows/):
"Relative Free Energies with the OpenFE CLI"
([`rbfe_tutorial/cli_tutorial.md`](https://github.com/OpenFreeEnergy/ExampleNotebooks/tree/main/rbfe_tutorial))
and "Partial charges with OpenFE CLI"
([`cli_tutorials/cli_charge_molecules.md`](https://github.com/OpenFreeEnergy/ExampleNotebooks/blob/main/cli_tutorials/cli_charge_molecules.md)),
which becomes the charging step.

The tutorial is plan, run, gather. The run step is one `openfe quickrun` per leg
(complex and solvent leg of each edge), each hours on a GPU. The tutorial leaves
that fan-out to a hand-written `sbatch` loop. Here it is a `horus_map`: one clone per
transformation JSON, on a local CPU for the smoke profile or one Slurm GPU job per leg
for the full profile, with gather and the report waiting for all of them.

## Horus Configuration

```
fetch_inputs    (local, shell)   curl tyk2_ligands.sdf + tyk2_protein.pdb (pinned commit)
select_ligands  (local, shell)   smoke: 3 ligands / full: all 10
charge_ligands  (local, conda)   openfe charge-molecules  (AM1-BCC, ambertools)
plan_network    (local, conda)   scripts/plan.py: Kartograf + minimal spanning network
                                 --> transformations/<leg>.json + ligand_network.graphml
quickrun        (horus_map)      openfe quickrun per leg   (smoke: local CPU; full: Slurm GPU)
gather          (local, conda)   openfe gather --report ddg / raw / dg --> ddg.tsv, raw.tsv, dg.tsv
report          (local, shell)   scripts/report.py --> report.html (tables + Mol*)
```

| Piece | Kind | Used by |
|---|---|---|
| executors | `shell` (stdlib Python, curl); `conda_python_environment` (one openfe 1.13.0 env at `horus_workflow_results/.horus_conda_env`) | shell: fetch, select, report; conda: charge, plan, quickrun, gather |
| targets | `local` (`*local`); `slurm` with a local inner target (`*gpu`, partition/account per site) | everything local; `quickrun` switches to `*gpu` for full |
| map | `horus_map` over the `transformations/` folder, one clone per leg JSON, `max_concurrency: 2` | `quickrun` |
| parameter | root `choice` artifact `profile` (`params/profile.txt`) | select, plan, gather |

## Compute Pattern

| Stage | Where | CPU / GPU | Smoke | Full |
|---|---|---|---|---|
| fetch, select | local | CPU | seconds | seconds |
| charge_ligands | local | 4 CPU | ~1 min (3 ligands) | a few min (10 ligands) |
| plan_network | local | 1 CPU | seconds | ~1 min |
| quickrun (map) | local / Slurm | smoke: 2 CPU threads per leg, 2 legs at a time; full: 1 GPU per leg | complex legs 11-22 min, solvent legs 1-2 min; map 13-22 min (host load) | hours per leg (3 repeats x 11 windows x 6 ns) |
| gather, report | local | CPU | seconds | seconds |

Measured smoke runs on a shared 16-core host (other jobs running, our cap 5 cores):
**15-23 min wall** (886 s, and 1388 s with a host load average of ~16, where the two
concurrent complex legs took 15 and 22 min) end to end with the conda env already built; building the env
the first time adds a few minutes. Each complex leg uses ~1.5 GB RAM. The full profile
is 10 ligands, 9 edges, 18 legs of several GPU-hours each (not measured here), spread
over as many GPUs as `max_concurrency` allows.

## Tools & Dependencies

- [openfe](https://github.com/OpenFreeEnergy/openfe) 1.13.0 (MIT) from conda-forge,
  with openmm 8.4.0, ambertools, kartograf. See `conda_env.yaml`.
- Official containers for the same version: `ghcr.io/openfreeenergy/openfe:1.13.0`
  (Docker) and `oras://ghcr.io/openfreeenergy/openfe:1.13.0-apptainer` (Apptainer).
- Horus: `horus-runtime`, `horus-environments` (conda executor), `horus-slurm`.
- `micromamba` (or conda/mamba) on the target for the conda executor.

## Quick start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# From the repo root
cd workflows/omsf/w01-openfe-rbfe-tyk2

# Install the horus-runtime and plugins (one time)
uv sync

# Run the smoke profile (default)
uv run horus run workflow.yaml --no-tui
```

The first run builds the openfe conda env from `conda_env.yaml` once, at
`horus_workflow_results/.horus_conda_env` (a few minutes; every openfe task reuses it).
A second `horus run` skips every task whose outputs are already there.

Self-checks for the glue scripts:

```bash
python3 scripts/select_ligands.py --selftest
python3 scripts/report.py --selftest
micromamba run -p horus_workflow_results/.horus_conda_env python scripts/plan.py --selftest
```

## Running the full profile on Slurm GPUs

1. Switch the profile: set `value: full` on the root `profile` artifact in
   `workflow.yaml` (or pick it in the tc-os UI), then
   `rm params/profile.txt`. Horus writes `params/profile.txt` only when it is missing
   and uses it for the skip check. Optionally also `rm -rf horus_workflow_results/results`
   for a clean start; it is not needed for correctness, since the map drops slots it no
   longer uses and each slot is cleared before its leg runs.
2. Fill `partition` and `account` in the `_gpu` anchor.
3. On the `quickrun` task change `target: *local` to `target: *gpu`, and raise
   `max_concurrency` to the number of GPU jobs you want at once (10 ligands give
   9 edges, so 18 legs).
4. Set `time_limit` in `_gpu` to your site's maximum. A leg that is killed (timeout,
   preemption) is re-run on the next `horus run` and `openfe quickrun --resume` picks up
   the units it already finished from `horus_workflow_results/quickrun[N]/work`.

The full profile uses the protocol defaults, which are also the CLI defaults: CUDA
platform, 3 repeats per leg, 11 lambda windows, 1 ns equilibration and 5 ns production.

The conda-forge openmm build ships the CUDA platform plugin even when the env is solved
on a host without a GPU, so the shared env built by `charge_ligands` on the login/local
node also runs on the GPU node. It pulls `cuda-version` 13.x; if your GPU nodes have an
older driver, add `cuda-version=12` to `conda_env.yaml`.

To use the official container instead of the conda env, swap the `executor` of the
openfe tasks (all of them run `command` runtimes except `plan_network`, which stays on
conda). Add `horus-docker` or `horus-singularity` to `pyproject.toml` first
(`uv add horus-docker` / `uv add horus-singularity`):

```yaml
# Docker (needs the NVIDIA Container Toolkit for GPUs)
executor:
  kind: docker
  image: ghcr.io/openfreeenergy/openfe:1.13.0
  gpus: all
  user: "1000:1000" # your uid:gid (`id -u`:`id -g`), else results/ ends up root-owned

# Apptainer, typical on HPC: pull once, then point at the .sif
#   apptainer pull openfe.sif oras://ghcr.io/openfreeenergy/openfe:1.13.0-apptainer
executor:
  kind: singularity
  exe: apptainer
  image: /path/to/openfe.sif
  nv: true
```

Both executors mount the artifact folders only. `quickrun` keeps its work dir at
`../work` relative to the clone's run folder, so under a container that folder also
needs a bind mount and the container's working directory must be the run folder
(e.g. Docker `working_dir: ${task.working_dir}` plus a `volumes` entry for
`horus_workflow_results`); without it the leg still runs but `--resume` has nothing to
resume from.

## Input / Output

**Input**: nothing to provide. `tyk2_ligands.sdf` and `tyk2_protein.pdb` are fetched
from OpenFreeEnergy/ExampleNotebooks at commit `d083c283b96e976d2e90c03d94e57e3ef6bc2c8c`.
To run your own series, replace `fetch_inputs` with root file artifacts.

**Output** (in `results/`):

| File | What | Renders as |
|---|---|---|
| `ddg.tsv` | ddG per edge with uncertainty (`openfe gather --report ddg`) | table |
| `raw.tsv` | dG per leg and repeat (`--report raw`) | table |
| `dg.tsv` | MLE dG per ligand (`--report dg`); in smoke a one-line note (see below) | table |
| `report.html` | both tables, network edges, Mol* view of TYK2 with the ligands | HTML page |
| `ligand_network.graphml` | the planned network with atom mappings | file |
| `alchemicalNetwork.json` | the full alchemical network, as `plan-rbfe-network` writes it (not a declared artifact) | file |
| `charged_ligands.sdf` | ligands with AM1-BCC charges | file |
| `transformations/` | one transformation JSON per leg | folder |
| `legs/<slot>/` | per leg: `result.json`, `quickrun.log` | folder |

## Parameterization

| Parameter | Where | Default | Meaning |
|---|---|---|---|
| `profile` | root `profile` choice artifact (`value:`) | `smoke` | `smoke` or `full`; passed to scripts as `${profile}`. After changing it, delete `params/profile.txt` (see above) |
| smoke ligands | `SMOKE` in `scripts/select_ligands.py` | ejm_31, ejm_42, ejm_46 | 3 ligands give 2 edges, 4 legs |
| smoke sampling | `protocol_settings()` in `scripts/plan.py` | 1 repeat, 4 windows, 0.1 ps iterations, 1 ps eq / 2 ps prod, 100 minimization steps, CPU | |
| charging cores | `charge_ligands` `resources.cpus` | 4 | passed to `-n` |
| quickrun target | `quickrun` `target` | `*local` | `*gpu` for full |

## Implementation Notes

- Planning goes through the openfe Python API (`scripts/plan.py`) instead of
  `openfe plan-rbfe-network`, because the CLI settings YAML only takes `mapper`,
  `network` and `partial_charge` keys and so cannot shorten sampling. The script uses
  the CLI's own loaders and defaults (`openfecli.parameters`), so the mapper (Kartograf),
  scorer, network (minimal spanning tree) and solvent match the CLI.
- Charges are computed once in `charge_ligands` and read from the SDF; `plan.py`
  fails if a ligand has none, so nothing is recharged.
- The smoke sampling is tiny because the hybrid-topology forces are slow on the
  OpenMM CPU platform: one force evaluation of the ~37k-atom complex leg takes ~0.2 s
  on 2 threads. A first try with 5 windows and 10 ps / 20 ps took 11 min for a
  solvent leg (1.7k atoms) and was on track for hours per complex leg, and 1000
  minimization steps alone ran over 25 min. Smoke runs 2 legs at a time
  (`max_concurrency: 2`) with `OPENMM_CPU_THREADS` set from `resources.cpus` (2).
- The solvent padding stays at the protocol default (1.5 nm). With 1.0 or 1.2 nm the
  solvent-leg box ended up smaller than twice the 0.9 nm cutoff and the leg failed.
- A failing leg fails the map (default `on_item_failure: fail`), which cancels the
  other running legs.
- `openfe gather --report dg` refuses networks with fewer than 3 edges or fewer than
  2 repeats per edge. The smoke network has 2 edges and 1 repeat (a 4th ligand would add
  a third ~15 min complex leg), so in smoke `gather` writes a note to `dg.tsv` and the
  report shows ddG and raw per-leg values. Full runs `--report dg` as usual.
- Each leg writes `legs/<slot>/result.json` (gather reads the leg identity from the
  JSON, not the file name) and the slot is emptied before the leg runs, so a slot reused
  for a different leg never keeps the old result.
- The openfe work directory (trajectories, checkpoints, the quickrun resume cache) is
  `horus_workflow_results/quickrun[N]/work`, outside the `legs/` output, so Horus does
  not fingerprint or transfer GBs of trajectories and gather only walks small files.
  `--resume` is a no-op on a fresh leg; the cache key hashes the output path and the
  transformation, so a cache from another leg is never reused.
- Progress bars from `openfe` are `\r`-only, so `charge_ligands` and `quickrun` log to a
  file and print the tail.

## Open Questions

- Smoke ddG values are not meaningful (picoseconds of sampling, one repeat). One smoke
  run gave ejm_31 -> ejm_42 = 0.1 and ejm_31 -> ejm_46 = 4.5 kcal/mol, with uncertainty
  0.0 because a single repeat has no spread. Expect
  different numbers on every run.
- The full profile and the container executors were not run here (no GPU or Slurm on
  the test host). Not verified: that `openfe` is on `PATH` under `apptainer exec` for the
  `-apptainer` image (exec skips the runscript), and the container bind mount for the
  quickrun work dir described above.
- Whether one full leg (198 ns of hybrid-topology sampling) fits in 24 h depends on the
  GPU; on older cards it may need a resume or two.

## References

- OpenFE docs: <https://docs.openfree.energy>
- Upstream tutorials (MIT): <https://github.com/OpenFreeEnergy/ExampleNotebooks>
- OMSF workflow directory: <https://directory.omsf.io/workflows/>

## License and credit

The workflow glue is MIT like this repository. The TYK2 inputs and tutorials are from
OpenFreeEnergy/ExampleNotebooks (MIT); openfe is MIT. Credit to the Open Free Energy
team for the tutorials and the software.
