# W-12 · Protein-Ligand Docking (PDBe REST-API Binding Site)

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

This workflow performs structure-based virtual screening of a single ligand against a protein target using **AutoDock Vina**, locating the docking box by querying the **PDBe REST API** for known ligand-binding sites instead of computing one locally. The target is **p38-α MAP kinase** (PDB: 3LFA) and the ligand is the kinase inhibitor **Dasatinib** (PDB ligand code 1N1). The workflow downloads the receptor, queries PDBe for its annotated binding sites, builds a docking box around the selected cavity, prepares both receptor and ligand as PDBQT, runs the docking, and assembles the top pose back into a full protein-ligand complex. Horus provisions the biobb/OpenBabel/AutoDock Vina conda environment automatically and runs all stages locally.

## Pipeline

```
download_pdb                Download 3LFA structure from PDB (protein + ligand complex)
   │
   ├─ extract_protein         Extract protein chain (remove ligands, water, ions)
   │
   ├─ get_binding_sites       Query PDBe REST-API for binding sites (residues.json)
   │
   └─ generate_cavity_box     Generate docking box around selected binding site cavity
         │
download_ligand_sdf          Download Dasatinib (1N1) ideal SDF from PDBe
   │
convert_sdf_to_pdb            Convert ligand SDF to PDB format (OpenBabel)
   │
prepare_ligand_pdbqt          Convert ligand PDB to PDBQT for AutoDock Vina (OpenBabel)
   │
prepare_receptor_pdbqt        Add hydrogens and convert receptor to PDBQT
   │
run_docking                   Run AutoDock Vina protein-ligand docking
   │
extract_docking_pose          Extract best docking pose (model 1) from Vina output
   │
convert_pose_to_pdb           Convert docking pose PDBQT to PDB format (OpenBabel)
   │
assemble_complex              Merge receptor and docking pose into final complex PDB
```

## Prerequisites

- **uv** (recommended) or pip — to install horus-runtime
- **micromamba**, **mamba**, or **conda** — the workflow executor builds a shared conda environment from `conda_env.yaml` to provision AutoDock Vina, OpenBabel, and the biobb stack

## Quick Start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# From the workflow directory, install horus-runtime
cd workflows/bioexcel_building_blocks/w07-protein-ligand-docking-pdbe-rest-api
uv sync
# or: pip install horus-runtime horus-environments

# Run the workflow
uv run horus run workflow.yaml
```

The first run builds the conda environment (this takes a few minutes). Subsequent runs reuse the cached environment at `../.horus_conda_env`.

## Inputs / Outputs

This workflow has no file inputs — it fetches the 3LFA receptor and the Dasatinib (1N1) ligand automatically, and queries the PDBe REST API directly for binding-site annotations.

> **Note:** `configs/generate_cavity_box.yaml` ships with an empty `resid_list`. The binding-site residue indices are only known after `get_binding_sites` runs and `results/residues.json` can be inspected — populate `resid_list` with the residues for your chosen cavity before (re-)running `generate_cavity_box`. This is a manual, two-pass step inherited from the original tutorial notebook.

**Outputs** (all under `results/`):
- `download.pdb`, `pdb_protein.pdb` — fetched receptor structure
- `residues.json` — PDBe-annotated binding sites for 3LFA
- `box.pdb` — docking box around the selected cavity
- `ideal.sdf`, `ligand.pdb`, `prep_ligand.pdbqt` — ligand structure and docking-ready PDBQT
- `prep_receptor.pdbqt` — docking-ready receptor PDBQT
- `output_vina.pdbqt`, `output_vina.log` — all Vina docking poses and scores
- `output_model.pdbqt`, `output_model.pdb` — top-ranked pose
- `output_structure.pdb` — final assembled protein-ligand complex

## Configuration

- `configs/download_pdb.yaml`, `configs/get_binding_sites.yaml` — target PDB code (3LFA)
- `configs/generate_cavity_box.yaml` — binding-site residue selection (`resid_list`) and box offset
- `configs/download_ligand_sdf.yaml` — ligand code (1N1)
- `configs/convert_sdf_to_pdb.yaml`, `configs/prepare_ligand_pdbqt.yaml`, `configs/convert_pose_to_pdb.yaml` — OpenBabel format conversion options
- `configs/prepare_receptor_pdbqt.yaml` — receptor protonation settings
- `configs/extract_docking_pose.yaml` — which Vina pose to extract

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [biobb_vs](https://github.com/bioexcel/biobb_vs)
- [AutoDock Vina](https://vina.scripps.edu)
- [PDBe REST API](https://www.ebi.ac.uk/pdbe/pdbe-rest-api)
- [BioExcel protein-ligand docking tutorial (PDBe REST-API variant)](https://biobb-wf-virtual-screening.readthedocs.io)
