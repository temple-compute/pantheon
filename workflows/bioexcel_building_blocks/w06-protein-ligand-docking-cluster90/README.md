# W-11 · Protein-Ligand Docking (PDB Cluster90 Binding Site)

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

This workflow performs structure-based virtual screening of a single ligand against a protein target using **AutoDock Vina**, locating the docking box from a **PDB Cluster90** sequence-cluster analysis of known co-crystallized ligands. The target is **p38-α MAP kinase** (PDB: 3HEC) and the ligand is the FDA-approved kinase inhibitor **Imatinib** (PDB ligand code STI). The workflow downloads the receptor and a Cluster90 collection of homologous structures, infers the binding site from where ligands cluster across those homologs, builds a docking box around it, prepares both receptor and ligand as PDBQT, runs the docking, and assembles the top pose back into a full protein-ligand complex. Horus provisions the biobb/OpenBabel/AutoDock Vina conda environment automatically and runs all stages locally.

## Pipeline

```
create_results_folder      Create results folder
   │
fetch_pdb                   Download 3HEC structure from PDB
   │
   ├─ extract_molecule       Extract protein structure from downloaded PDB
   │
   └─ pdb_cluster_zip        Download PDB Cluster90 collection for 3HEC
         │
      bindingsite             Extract binding site from Cluster90 collection
         │
      box                     Generate cavity box around binding site
         │
ideal_sdf                   Download Imatinib (STI) small molecule as SDF
   │
babel_convert_sdf2pdb        Convert small molecule from SDF to PDB format
   │
babel_convert_pdb2pdbqt      Prepare ligand for docking (PDB → PDBQT)
   │
str_check_add_hydrogens      Prepare receptor protein for docking (PDB → PDBQT)
   │
autodock_vina_run            Run AutoDock Vina docking
   │
extract_model_pdbqt          Extract top docking pose from Vina output
   │
babel_convert_pdbqt2pdb      Convert docking pose from PDBQT to PDB format
   │
cat_pdb                      Combine protein and docked ligand into final structure
```

## Prerequisites

- **uv** (recommended) or pip — to install horus-runtime
- **micromamba**, **mamba**, or **conda** — the workflow executor builds a shared conda environment from `conda_env.yaml` to provision AutoDock Vina, OpenBabel, and the biobb stack

## Quick Start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# From the workflow directory, install horus-runtime
cd workflows/bioexcel_building_blocks/w06-protein-ligand-docking-cluster90
uv sync
# or: pip install horus-runtime horus-environments

# Run the workflow
uv run horus run workflow.yaml
```

The first run builds the conda environment (this takes a few minutes). Subsequent runs reuse the cached environment at `../.horus_conda_env`.

## Inputs / Outputs

This workflow has no file inputs — it fetches the 3HEC receptor, its PDB Cluster90 collection, and the Imatinib (STI) ligand automatically.

**Outputs** (all under `results/`):
- `download.pdb`, `pdb_protein.pdb` — fetched receptor structure
- `pdb_cluster.zip` — PDB Cluster90 collection used to locate the binding site
- `bindingsite.pdb`, `box.pdb` — inferred binding site and docking box
- `ideal.sdf`, `ligand.pdb`, `prep_ligand.pdbqt` — ligand structure and docking-ready PDBQT
- `prep_receptor.pdbqt` — docking-ready receptor PDBQT
- `output_vina.pdbqt`, `output_vina.log` — all Vina docking poses and scores
- `output_model.pdbqt`, `output_model.pdb` — top-ranked pose
- `output_structure.pdb` — final assembled protein-ligand complex

## Configuration

- `configs/fetch_pdb.yaml`, `configs/pdb_cluster_zip.yaml` — target PDB code (3HEC) and cluster identity threshold (90%)
- `configs/bindingsite.yaml` — binding-site detection parameters
- `configs/box.yaml` — docking box offset/padding around the binding site
- `configs/ideal_sdf.yaml` — ligand code (STI)
- `configs/babel_convert_sdf2pdb.yaml`, `configs/babel_convert_pdb2pdbqt.yaml`, `configs/babel_convert_pdbqt2pdb.yaml` — OpenBabel format conversion options
- `configs/str_check_add_hydrogens.yaml` — receptor protonation settings
- `configs/extract_model_pdbqt.yaml` — which Vina pose to extract

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [biobb_vs](https://github.com/bioexcel/biobb_vs)
- [AutoDock Vina](https://vina.scripps.edu)
- [OpenBabel](https://openbabel.org)
- [BioExcel protein-ligand docking tutorial (Cluster90 variant)](https://biobb-wf-virtual-screening.readthedocs.io)
