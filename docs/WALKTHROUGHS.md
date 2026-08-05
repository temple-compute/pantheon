# Workflow Walkthroughs

Every workflow in this repo follows the same four steps:

```bash
# 1. Install uv (one time)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Enter the workflow directory (paths below are from the repo root)
cd <workflow directory>

# 3. Install horus-runtime and plugins into the workflow's venv (one time per dir)
uv sync

# 4. Run it
uv run horus run workflow.yaml
```

The only per-workflow differences are the directory you `cd` into and, for the
two workflows built with Python (`run.py`) instead of YAML, the run command.
Outputs land in the workflow's `horus_workflow_results/` or `workflow_results/`
directory (created next to the run dir), and are re-created on every run.

## Prerequisites by workflow

Most workflows provision their simulation software via conda environments
(built automatically on first run), so a conda-family tool
(`micromamba`, `mamba`, or `conda`) must be on your `PATH`. A handful of
BioExcel workflows instead run their ARM64-incompatible tools inside a Docker
container, which Docker pulls automatically on first run.

| Requires Docker | Workflows |
|---|---|
| Yes | `bioexcel_building_blocks/w22-cavity-guided-virtual-screening` (fpocket stages) |
| Conda only | every other workflow that needs simulation tools; see each README |

The [BioExcel index](../workflows/bioexcel_building_blocks/README.md) details
which packages are affected on macOS ARM64 and how the mixed conda/Docker
strategy works.

## Workflow index

### Drug Discovery

| ID | Directory | Run command |
|---|---|---|
| W-01 | `workflows/drug-discovery/w01-boltz2-virtual-screening` | `uv run horus run workflow.yaml` |
| W-02 | `workflows/drug-discovery/w02-autodock-vina-docking` | `uv run horus run workflow.yaml` |

### BioExcel Building Blocks

| ID | Directory | Run command |
|---|---|---|
| W-03 | `workflows/bioexcel_building_blocks/w01-gromacs-md-setup` | `uv run horus run workflow.yaml` |
| W-04 | `workflows/bioexcel_building_blocks/w02-ligand-parameterization` | `uv run horus run workflow.yaml` |
| W-05 | `workflows/bioexcel_building_blocks/w03-amber-md-setup` | `uv run horus run workflow.yaml` |
| W-09 | `workflows/bioexcel_building_blocks/w04-gromacs-protein-ligand-complex-md-setup` | `uv run horus run workflow.yaml` |
| W-10 | `workflows/bioexcel_building_blocks/w05-mutation-free-energy-calculations` | `uv run horus run workflow.yaml` |
| W-11 | `workflows/bioexcel_building_blocks/w06-protein-ligand-docking-cluster90` | `uv run horus run workflow.yaml` |
| W-12 | `workflows/bioexcel_building_blocks/w07-protein-ligand-docking-pdbe-rest-api` | `uv run horus run workflow.yaml` |
| W-13 | `workflows/bioexcel_building_blocks/w08-protein-ligand-docking-fpocket` | `uv run horus run workflow.yaml` |
| W-14 | `workflows/bioexcel_building_blocks/w09-amber-protein-md-setup` | `uv run horus run workflow.yaml` |
| W-15 | `workflows/bioexcel_building_blocks/w10-amber-protein-ligand-complex-md-setup` | `uv run horus run workflow.yaml` |
| W-16 | `workflows/bioexcel_building_blocks/w11-amber-constant-ph-md-setup` | `uv run horus run workflow.yaml` |
| W-17 | `workflows/bioexcel_building_blocks/w12-dna-helical-parameters` | `uv run horus run workflow.yaml` |
| W-18 | `workflows/bioexcel_building_blocks/w13-abc-md-setup` | `uv run horus run workflow.yaml` |
| W-19 | `workflows/bioexcel_building_blocks/w14-protein-conformational-ensembles` | `uv run horus run workflow.yaml` |
| W-20 | `workflows/bioexcel_building_blocks/w15-protein-conformational-transitions` | `uv run horus run workflow.yaml` |
| W-21 | `workflows/bioexcel_building_blocks/w16-macromolecular-coarse-grained-flexibility` | `uv run horus run workflow.yaml` |
| W-22 | `workflows/bioexcel_building_blocks/w17-classical-molecular-interaction-potentials` | `uv run horus run workflow.yaml` |
| W-23 | `workflows/bioexcel_building_blocks/w18-molecular-structure-checking` | `uv run horus run workflow.yaml` |
| W-24 | `workflows/bioexcel_building_blocks/w19-haddock3-protein-protein-docking` | `uv run horus run workflow.yaml` |
| W-25 | `workflows/bioexcel_building_blocks/w20-autoencoders-md-analysis` | `uv run horus run workflow.yaml` |
| W-26 | `workflows/bioexcel_building_blocks/w21-protein-membrane-md-analysis` | `uv run horus run workflow.yaml` |
| W-30 | `workflows/bioexcel_building_blocks/w22-cavity-guided-virtual-screening` | `uv run horus run workflow.yaml` |
| W-31 | `workflows/bioexcel_building_blocks/w23-cavity-analysis` | `uv run horus run workflow.yaml` |

### Engine Showcases

| ID | Directory | Run command |
|---|---|---|
| W-06 | `workflows/engine-showcases/w01-fanout-map-gather` | `uv run horus run workflow.yaml` |
| W-07 | `workflows/engine-showcases/w02-programmatic-dynamic-dag` | `uv run python run.py` |
| W-08 | `workflows/engine-showcases/w03-loop-map` | `uv run horus run workflow.yaml` |
| W-27 | `workflows/engine-showcases/w04-subworkflow-reuse` | `uv run horus run workflow.yaml` |

### AI

| ID | Directory | Run command |
|---|---|---|
| W-28 | `workflows/ai/w01-train-llm` | `uv run horus run workflow.yaml` |
| W-29 | `workflows/ai/w02-tiny-llm` | `uv run horus run workflow.yaml` |

## Where output lands

- Workflows whose `workflow.yaml` sets `working_directory: horus_workflow_results`
  (the drug-discovery, engine-showcase, and w22/w23 BioExcel workflows) write
  outputs under `horus_workflow_results/`.
- The other BioExcel and AI workflows set `working_directory: ./workflow_results`
  and write outputs under `workflow_results/results/`.
- `w02-programmatic-dynamic-dag` writes directly to `results/` next to `run.py`.

Every run directory is git-ignored, so you can run workflows in place without
polluting the repo.
