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
| W-09 | [GROMACS Protein-Ligand Complex MD Setup](workflows/bioexcel_building_blocks/w04-gromacs-protein-ligand-complex-md-setup/README.md) | Full MD setup for a T4 lysozyme–ligand complex using GROMACS, AMBER99SB-ILDN, and GAFF/ACPype ligand parameters |
| W-10 | [Mutation Free Energy Calculations](workflows/bioexcel_building_blocks/w05-mutation-free-energy-calculations/README.md) | Non-equilibrium alchemical mutation free-energy (ΔΔG) via GROMACS + pmx, estimated with CGI/BAR/Jarzynski |
| W-11 | [Protein-Ligand Docking (Cluster90)](workflows/bioexcel_building_blocks/w06-protein-ligand-docking-cluster90/README.md) | AutoDock Vina virtual screening with the docking box inferred from a PDB Cluster90 homolog analysis |
| W-12 | [Protein-Ligand Docking (PDBe REST API)](workflows/bioexcel_building_blocks/w07-protein-ligand-docking-pdbe-rest-api/README.md) | AutoDock Vina virtual screening with the docking box located via the PDBe REST API's annotated binding sites |
| W-13 | [Protein-Ligand Docking (fpocket)](workflows/bioexcel_building_blocks/w08-protein-ligand-docking-fpocket/README.md) | AutoDock Vina virtual screening with the docking box computed directly from fpocket cavity detection |
| W-14 | [AMBER Protein MD Setup](workflows/bioexcel_building_blocks/w09-amber-protein-md-setup/README.md) | Full AMBER (AmberTools/sander/cpptraj) MD setup and analysis for lysozyme 1AKI |
| W-15 | [AMBER Protein-Ligand Complex MD Setup](workflows/bioexcel_building_blocks/w10-amber-protein-ligand-complex-md-setup/README.md) | AMBER MD setup for a T4 lysozyme–ligand complex with ACPype/GAFF ligand parameterization |
| W-16 | [AMBER Constant pH MD Setup](workflows/bioexcel_building_blocks/w11-amber-constant-ph-md-setup/README.md) | Constant-pH MD with AmberTools, predicting per-residue pKa values from titratable-residue protonation states |
| W-17 | [DNA Helical Parameters](workflows/bioexcel_building_blocks/w12-dna-helical-parameters/README.md) | Extracts per-base-pair helical parameters and dynamics from a DNA MD trajectory using Curves+/Canal |
| W-18 | [ABC MD Setup](workflows/bioexcel_building_blocks/w13-abc-md-setup/README.md) | Ascona B-DNA Consortium standard protocol for DNA MD system preparation with AmberTools |
| W-19 | [Protein Conformational Ensembles](workflows/bioexcel_building_blocks/w14-protein-conformational-ensembles/README.md) | Generates and compares protein conformational ensembles via CONCOORD, ANM, FlexServ, NOLB, and iMODS |
| W-20 | [Protein Conformational Transitions](workflows/bioexcel_building_blocks/w15-protein-conformational-transitions/README.md) | Computes a conformational transition pathway between two protein states using GOdMD |
| W-21 | [Macromolecular Coarse-Grained Flexibility](workflows/bioexcel_building_blocks/w16-macromolecular-coarse-grained-flexibility/README.md) | FlexServ flexibility analysis (BD/DMD/NMA ensembles + PCA) from a single static structure |
| W-22 | [Classical Molecular Interaction Potentials](workflows/bioexcel_building_blocks/w17-classical-molecular-interaction-potentials/README.md) | CMIP interaction-potential grids and protein-ligand/protein-protein interaction energies |
| W-23 | [Molecular Structure Checking](workflows/bioexcel_building_blocks/w18-molecular-structure-checking/README.md) | Structure-quality checking and repair pipeline (Modeller + AMBER minimization) ahead of MD |
| W-24 | [HADDOCK3 Protein-Protein Docking](workflows/bioexcel_building_blocks/w19-haddock3-protein-protein-docking/README.md) | Antibody-antigen information-driven docking with HADDOCK3, scored against a reference complex |
| W-25 | [AutoEncoders for MD Analysis](workflows/bioexcel_building_blocks/w20-autoencoders-md-analysis/README.md) | Trains an AutoEncoder on MD trajectories for feature extraction and PLUMED collective-variable export |
| W-26 | [Protein-Membrane MD Analysis](workflows/bioexcel_building_blocks/w21-protein-membrane-md-analysis/README.md) | Membrane MD analysis: leaflet identification, bilayer thickness, order parameters, area per lipid, pore radius |

### Engine Showcases

Small, self-contained workflows that demonstrate horus-runtime engine
features rather than a science domain.

| ID | Workflow | Description |
|---|---|---|
| W-06 | [Fan-out / Map / Gather](workflows/engine-showcases/w01-fanout-map-gather/README.md) | Split a collection into batches, map a stage over them concurrently, gather N results into one folder |
| W-07 | [Programmatic Dynamic DAG](workflows/engine-showcases/w02-programmatic-dynamic-dag/README.md) | A task generates downstream tasks at runtime from the data it reads, via `add_task`/`expand` |
| W-08 | [Bounded Loop (Range Map)](workflows/engine-showcases/w03-loop-map/README.md) | Run a fixed number of deterministic iterations with `map: {range: N}` and gather the results |

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for how to add new workflows or improve existing ones.
