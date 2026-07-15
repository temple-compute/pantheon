# W-13 · Protein-Ligand Docking (Fpocket Binding Site)

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

This workflow performs structure-based virtual screening of a single ligand against a protein target using **AutoDock Vina**, locating the docking box by computing candidate cavities directly on the receptor with **fpocket** instead of relying on homolog clustering or external annotations. The target is **p38-α MAP kinase** (PDB: 3HEC) and the ligand is the FDA-approved kinase inhibitor **Imatinib** (PDB ligand code STI). The workflow downloads the receptor, runs fpocket to detect all cavities, filters them by volume and selects the target pocket, builds a docking box around it, prepares both receptor and ligand as PDBQT, runs the docking, and superposes the top pose onto the receptor. Horus provisions the biobb/OpenBabel/fpocket/AutoDock Vina conda environment automatically and runs all stages locally.

## Pipeline

```
fetch_pdb                    Download 3HEC structure from PDB
   │
extract_protein               Extract protein structure (remove ligands, ions, water)
   │
   ├─ fpocket_run              Compute protein cavities with fpocket
   │     │
   │  fpocket_filter           Filter cavities by volume (800-2000 Å³)
   │     │
   │  fpocket_select           Extract selected pocket cavity (pocket 6)
   │     │
   │  box                      Generate docking box around cavity (offset 12 Å)
   │
   └─ str_check_add_hydrogens  Prepare receptor protein for docking (PDB → PDBQT)
   │
ideal_sdf                     Download Imatinib (STI) small molecule as SDF
   │
babel_convert_sdf_to_pdb       Convert small molecule from SDF to PDB format
   │
babel_convert_pdb_to_pdbqt     Prepare ligand for docking (PDB → PDBQT, partial charges)
   │
autodock_vina_run              Run AutoDock Vina docking
   │
extract_model_pdbqt            Extract docking pose (model 1) from Vina output
   │
babel_convert_pdbqt_to_pdb     Convert docking pose from PDBQT to PDB format
   │
cat_pdb                        Superpose ligand docking pose onto target protein structure
```

## Prerequisites

- **uv** (recommended) or pip — to install horus-runtime
- **micromamba**, **mamba**, or **conda** — the workflow executor builds a shared conda environment from `conda_env.yaml` to provision AutoDock Vina, fpocket, OpenBabel, and the biobb stack

## Quick Start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# From the workflow directory, install horus-runtime
cd workflows/bioexcel_building_blocks/w08-protein-ligand-docking-fpocket
uv sync
# or: pip install horus-runtime horus-environments

# Run the workflow
uv run horus run workflow.yaml
```

The first run builds the conda environment (this takes a few minutes). Subsequent runs reuse the cached environment at `../.horus_conda_env`.

## Inputs / Outputs

This workflow has no file inputs — it fetches the 3HEC receptor and the Imatinib (STI) ligand automatically, and computes candidate binding cavities on the receptor itself with fpocket.

**Outputs** (all under `results/`):
- `download.pdb`, `pdb_protein.pdb` — fetched receptor structure
- `fpocket_all_pockets.zip`, `fpocket_summary.json` — all detected cavities
- `fpocket_filter_pockets.zip` — cavities filtered by volume
- `fpocket_cavity.pdb`, `fpocket_pocket.pqr` — selected pocket (pocket 6)
- `box.pdb` — docking box around the selected cavity
- `ideal.sdf`, `ligand.pdb`, `prep_ligand.pdbqt` — ligand structure and docking-ready PDBQT
- `prep_receptor.pdbqt` — docking-ready receptor PDBQT
- `output_vina.pdbqt` — all Vina docking poses and scores
- `output_model.pdbqt`, `output_model.pdb` — top-ranked pose
- `output_structure.pdb` — final assembled protein-ligand complex

## Configuration

- `configs/fetch_pdb.yaml` — target PDB code (3HEC)
- `configs/fpocket_run.yaml` — fpocket cavity-detection parameters
- `configs/fpocket_filter.yaml` — volume range used to filter candidate cavities
- `configs/fpocket_select.yaml` — which detected pocket to use for docking
- `configs/box.yaml` — docking box offset around the selected cavity
- `configs/ideal_sdf.yaml` — ligand code (STI)
- `configs/babel_convert_sdf_to_pdb.yaml`, `configs/babel_convert_pdb_to_pdbqt.yaml`, `configs/babel_convert_pdbqt_to_pdb.yaml` — OpenBabel format conversion options
- `configs/str_check_add_hydrogens.yaml` — receptor protonation settings
- `configs/extract_model_pdbqt.yaml` — which Vina pose to extract

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [biobb_vs](https://github.com/bioexcel/biobb_vs)
- [AutoDock Vina](https://vina.scripps.edu)
- [fpocket](https://github.com/Discngine/fpocket)
- [BioExcel protein-ligand docking tutorial (fpocket variant)](https://biobb-wf-virtual-screening.readthedocs.io)
