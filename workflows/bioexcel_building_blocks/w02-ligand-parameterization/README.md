# W-04 · Ligand Parameterization

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

This workflow generates GROMACS-compatible force-field parameters for a small-molecule ligand using the GAFF (General AMBER Force Field) via ACPype. Starting from a PDB ligand structure fetched from the RCSB, it adds hydrogens with OpenBabel, minimizes their positions energetically, then produces the `.gro`, `.itp`, and `.top` files needed to include the ligand in a GROMACS simulation. Horus provisions the biobb/OpenBabel/ACPype conda environment automatically and runs all stages locally.

## Pipeline

```
fetch_ligand       Fetch ligand structure from the PDB (biobb)
   │
add_hydrogens      Add hydrogen atoms at pH 7.4 (OpenBabel)
   │
minimize_hydrogens Energetically minimize hydrogen positions (OpenBabel + GAFF)
   │
parameterize       Generate GROMACS force-field parameters (ACPype / GAFF)
                   → ligand.params.gro  ligand.params.itp  ligand.params.top
```

## Prerequisites

- **uv** (recommended) or pip — to install horus-runtime
- **micromamba**, **mamba**, or **conda** — the workflow executor builds a shared conda environment from `conda_env.yaml` to provision OpenBabel, ACPype, and the biobb stack

## Quick Start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# From the workflow directory, install horus-runtime
cd workflows/bioexcel_building_blocks/w02-ligand-parameterization
uv sync
# or: pip install horus-runtime horus-environments

# Run the workflow
uv run horus run workflow.yaml
```

The first run builds the conda environment (this takes a few minutes). Subsequent runs reuse the cached environment at `../.horus_conda_env`.

## Inputs / Outputs

The workflow fetches the ligand automatically from the PDB using the ligand code in `configs/fetch_ligand.yaml`.

**Outputs** (all under `workflow_results/`):
- `results/ligand.pdb` — raw ligand structure from RCSB
- `results/ligand.H.mol2` — ligand with added hydrogens (MOL2 format)
- `results/ligand.H.min.pdb` — hydrogen-minimized ligand (PDB)
- `results/ligand.params.gro` — GROMACS structure file
- `results/ligand.params.itp` — GROMACS include topology (force-field parameters)
- `results/ligand.params.top` — GROMACS top file

## Configuration

Edit `configs/fetch_ligand.yaml` to change the target ligand (PDB ligand code). The `configs/add_h.yaml` and `configs/minimize_h.yaml` files control hydrogen addition and minimization options (pH, force field, convergence criteria).

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [ACPype](https://github.com/alanwilter/acpype)
- [OpenBabel](https://openbabel.org)
- [GAFF (General AMBER Force Field)](https://ambermd.org/antechamber/gaff.html)
- [BioExcel ligand parameterization tutorial](https://biobb-wf-ligand-parameterization.readthedocs.io)
