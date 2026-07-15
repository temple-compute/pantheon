# W-26 · Protein-Membrane MD Analysis

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

This workflow analyzes a membrane molecular dynamics simulation, using the BioExcel Building Blocks (biobb_io, biobb_mem, biobb_analysis). The example system is a heteropentameric GABA-gated chloride channel embedded in a DPPC lipid bilayer (MDDB accession: A023K, from the MemProtMD project). After fetching and fitting the trajectory so the membrane lies in the xy-plane, the workflow identifies membrane leaflets (FATSLiM, Lipyphilic) and computes a full set of membrane-analysis metrics: per-leaflet lipid z-positions and bilayer thickness, deuterium order parameters of the acyl tails, area per lipid (2D Voronoi tessellation), density profile along the membrane normal, channel pore-radius profile through the protein, and lipid flip-flop events between leaflets. Horus provisions the full FATSLiM/Lipyphilic/MDAnalysis/biobb conda environment automatically for each stage.

## Pipeline

```
download_trajectory        Download structure + trajectory for A023K from MDDB (mddb)
   │
fit_membrane                 Fit trajectory to membrane normal, rot+trans (gmx_image)
   │
fit_protein                   Fit trajectory to protein, XY translation only (gmx_image)
   │
identify_leaflets_fatslim      Identify membrane leaflets (fatslim_membranes)
   │
assign_leaflets                 Per-frame leaflet assignment (lpp_assign_leaflets)
   │
   ├── compute_zpositions           Lipid z-positions, whole membrane (lpp_zpositions)
   ├── compute_zpositions_around     Lipid z-positions around the protein (lpp_zpositions)
   ├── compute_order_parameters       Deuterium order parameters of acyl tails (gorder_aa)
   ├── compute_area_per_lipid          Area per lipid, 2D Voronoi tessellation (fatslim_apl)
   ├── compute_density_profile          Membrane density profile along z (cpptraj_density)
   ├── compute_pore_dimensions           Channel pore-radius profile (mda_hole)
   └── compute_flip_flop                 Lipid flip-flop events across leaflets (lpp_flip_flop)
```

## Prerequisites

- **uv** (recommended) or pip — to install horus-runtime
- **micromamba**, **mamba**, or **conda** — the workflow executor builds a shared conda environment from `conda_env.yaml` to provision FATSLiM, Lipyphilic, MDAnalysis, and the biobb stack

## Quick Start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# From the workflow directory, install horus-runtime
cd workflows/bioexcel_building_blocks/w21-protein-membrane-md-analysis
uv sync
# or: pip install horus-runtime horus-environments

# Run the workflow
uv run horus run workflow.yaml
```

The first run builds the conda environment (this takes a few minutes). Subsequent runs reuse the cached environment at `../.horus_conda_env`.

## Inputs / Outputs

This workflow has no file inputs — it fetches the structure (`.pdb`), trajectory (`.xtc`), and topology (`.tpr`) for MDDB entry A023K automatically.

**Outputs** (all under `results/`):
- `A023K_10.pdb`, `A023K_10.xtc`, `A023K.tpr` — downloaded structure, trajectory, and topology
- `A023K_fit.xtc`, `A023K_fit2.xtc` — membrane-normal-fitted and protein-XY-fitted trajectories
- `leaflets.ndx` — FATSLiM leaflet index groups
- `leaflets_data.csv` — per-frame Lipyphilic leaflet assignment (also reused as input for flip-flop detection)
- `zpositions.csv`, `zpositions_around.csv` — lipid z-position / bilayer-thickness data (whole membrane and protein-local)
- `order.csv` — deuterium order parameters
- `apl.csv` — area-per-lipid data
- `density.dat` — density profile along the membrane normal
- `hole.vmd`, `hole_profile.csv` — channel pore-radius profile
- `flip_flop.csv` — detected lipid flip-flop events

## Configuration

`configs/download_trajectory.yaml` sets the MDDB node/project ID, trajectory format, and frame stride. `configs/assign_leaflets.yaml`, `compute_zpositions.yaml`, `compute_zpositions_around.yaml`, `identify_leaflets_fatslim.yaml` control the lipid headgroup selection (`resname DPPC and element P`) used to identify leaflets. `configs/fit_membrane.yaml` and `fit_protein.yaml` control the GROMACS fitting mode (rot+trans vs. transxy) and reference selection.

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [biobb_mem](https://github.com/bioexcel/biobb_mem)
- [FATSLiM](https://pythonhosted.org/fatslim/)
- [Lipyphilic](https://lipyphilic.readthedocs.io)
- [MDDB](https://mddbr.eu/)
- [BioExcel protein-membrane MD analysis tutorial](https://biobb-wf-mem.readthedocs.io)
