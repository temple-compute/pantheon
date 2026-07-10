# Horus Workflow Repository

A curated library of production-ready workflows for the [horus-runtime](https://github.com/temple-compute/horus-runtime). Each workflow is a multi-stage pipeline designed to run across heterogeneous compute, routing each stage to the right cluster type automatically.

Each workflow directory contains:
- `README.md`: purpose, pipeline, install steps, and configuration guide
- `workflow.yaml` or `run.py`: a plain Horus workflow definition or Python workflow builder
- `scripts/`: small stage scripts and helper code when needed

## Getting Started

```bash
# 1. Install uv (recommended)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Clone this repo
git clone https://github.com/temple-compute/pantheon
cd pantheon

# 3. Install horus-runtime from inside any workflow directory
cd workflows/drug-discovery/w01-boltz2-virtual-screening
uv sync
# or, if you prefer pip:
# pip install horus-runtime horus-environments

# 4. Run the workflow
uv run horus run workflow.yaml
```

> **BioExcel workflows** also require a conda-family tool (`micromamba`, `mamba`, or `conda`) on your `PATH`. Their executors build conda environments to provision GROMACS, AMBER, and related simulation tools. More on executors at [docs.templecompute.com](https://docs.templecompute.com/guides/concepts).

## Workflows

### Drug Discovery

| ID | Workflow | Description |
|---|---|---|
| W-01 | [Boltz-2 Virtual Screening](workflows/drug-discovery/w01-boltz2-virtual-screening/README.md) | Predict binding structure and affinity for a protein–ligand library using Boltz-2 |
| W-02 | [AutoDock Vina Docking](workflows/drug-discovery/w02-autodock-vina-docking/README.md) | End-to-end molecular docking with AutoDock Vina: prep → dock → rank |

### BioExcel Building Blocks

| ID | Workflow | Description |
|---|---|---|
| W-03 | [GROMACS MD Setup](workflows/bioexcel_building_blocks/w01-gromacs-md-setup/README.md) | Full MD setup for lysozyme 1AKI using GROMACS: topology → solvation → equilibration → production MD |
| W-04 | [Ligand Parameterization](workflows/bioexcel_building_blocks/w02-ligand-parameterization/README.md) | Generate GROMACS force-field parameters for a small-molecule ligand via OpenBabel and ACPype/GAFF |
| W-05 | [AMBER MD Setup](workflows/bioexcel_building_blocks/w03-amber-md-setup/README.md) | Full MD setup for lysozyme 1AKI using AMBER: LEaP topology → solvation → equilibration → production MD + analysis |

### Engine Showcases

Small, self-contained workflows that demonstrate horus-runtime engine
features rather than a science domain. Requires horus-runtime ≥ the
Dynamic-workflows features (milestone: fan-out/map/loops).

| ID | Workflow | Description |
|---|---|---|
| W-06 | [Fan-out / Map / Gather](workflows/engine-showcases/w01-fanout-map-gather/README.md) | Split a collection into batches, map a stage over them concurrently, gather N results into one folder |
| W-07 | [Programmatic Dynamic DAG](workflows/engine-showcases/w02-programmatic-dynamic-dag/README.md) | A task generates downstream tasks at runtime from the data it reads, via `add_task`/`expand` |
| W-08 | [Bounded Loop (Range Map)](workflows/engine-showcases/w03-loop-map/README.md) | Run a fixed number of deterministic iterations with `map: {range: N}` and gather the results |

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for how to add new workflows or improve existing ones.
