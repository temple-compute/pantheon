# W-15 · AMBER Protein-Ligand Complex MD Setup

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

This workflow sets up a molecular dynamics simulation of a protein-ligand complex using AmberTools, illustrated with T4 lysozyme (PDB: 3HTB, mutant L99A/M102Q) bound to the small ligand 2-propylphenol (JZ4). Starting from the raw PDB file, it strips crystallographic water and co-crystallized ligands (PO4, BME), prepares the structure for AMBER, generates GAFF ligand parameters with ACPype, builds a combined protein-ligand topology with `leap`, minimizes, solvates, neutralizes with ions, and runs a full heat/NVT/NPT/production MD protocol with `sander`, finishing with cpptraj-based trajectory analysis (RMSD, radius of gyration, imaging). Horus provisions the AmberTools/biobb conda environment automatically for each stage and runs locally.

## Pipeline

```
fetch_pdb              Download 3HTB from the PDB (biobb_io)
   │
remove_pdb_water        Strip crystallographic waters
   │
remove_ligand_po4        Remove PO4 co-crystallized ligand
   │
remove_ligand_bme         Remove BME co-crystallized ligand
   │
pdb4amber                  Prepare structure for AMBER
   ├──────────────────────────────────┐
extract_heteroatoms                    │
   │                                   │
reduce_add_hydrogens (Reduce)          │
   │                                   │
babel_minimize (OpenBabel/GAFF)        │
   │                                   │
acpype_params_ac (ACPype)              │
   │  lib, frcmod                      │
   └──────────► leap_gen_top ◄─────────┘   Build protein-ligand complex topology (leap)
                    │
               sander_h_min ──► process_h_min      Minimize ligand hydrogens in vacuo
                    │
               sander_n_min ──► process_n_min      Minimize full system in vacuo
                    │
               amber_to_pdb (ambpdb)                Convert minimized structure to PDB
                    │
               leap_solvate                         Solvate in truncated octahedron box
                    │
               leap_add_ions                        Neutralize and add ions
                    │
               sander_min ──► process_min           Energy minimize solvated system
                    │
               sander_heat ──► process_heat          Heat 0 → 300 K
                    │
               sander_nvt ──► process_nvt             NVT equilibration
                    │
               sander_npt ──► process_npt              NPT equilibration
                    │
               sander_free                              Free production MD
                    │
        ┌───────────┼───────────┬───────────────┐
   cpptraj_rms_first  cpptraj_rms_exp  cpptraj_rgyr  cpptraj_image
   (RMSd vs frame 0)  (RMSd vs exp.)   (Rgyr)        (image + strip solvent)
```

## Prerequisites

- **uv** (recommended) or pip — to install horus-runtime
- **micromamba**, **mamba**, or **conda** — the workflow executor builds a shared conda environment from `conda_env.yaml` to provision AmberTools, ACPype, and the biobb stack

## Quick Start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# From the workflow directory, install horus-runtime
cd workflows/bioexcel_building_blocks/w10-amber-protein-ligand-complex-md-setup
uv sync
# or: pip install horus-runtime horus-environments

# Run the workflow
uv run horus run workflow.yaml
```

The first run builds the conda environment (this takes a few minutes). Subsequent runs reuse the cached environment at `../.horus_conda_env`.

## Inputs / Outputs

This workflow has no file inputs — it fetches PDB 3HTB automatically from the RCSB (ligand code JZ4 set in `configs/extract_heteroatoms.yaml`).

**Outputs** (all under `workflow_results/`):
- `results/3htb.pdb`, `results/3htb.noBME.pdb` — downloaded and cleaned structures
- `results/JZ4.pdb`, `results/JZ4.reduce.H.pdb`, `results/JZ4.H.min.mol2` — ligand extraction, protonation, and minimization intermediates
- `results/JZ4params.{inpcrd,frcmod,lib,prmtop}` — ACPype-generated GAFF ligand parameters
- `results/structure.leap.{pdb,top,crd}` — protein-ligand complex topology
- `results/structure.ions.{pdb,parmtop,crd}` — solvated, ion-neutralized system
- `results/sander.free.netcdf` — production MD trajectory
- `results/3htb_rms_first.dat`, `results/3htb_rms_exp.dat`, `results/3htb_rgyr.dat` — RMSD and radius-of-gyration time series
- `results/3htb_imaged_traj.trr` — PBC-imaged, solvent-stripped trajectory

## Configuration

`configs/fetch_pdb.yaml` and `configs/extract_heteroatoms.yaml` control the PDB/ligand codes fetched. `configs/acpype_params_ac.yaml` and `configs/babel_minimize.yaml` control ligand parameterization. `configs/leap_*.yaml` control force field selection, water model, and box geometry. `configs/sander_*.yaml` control simulation length, restraints, and thermostat/barostat settings for each minimization/equilibration/production stage.

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [biobb_amber](https://github.com/bioexcel/biobb_amber)
- [biobb_wf_amber tutorial notebooks](https://github.com/bioexcel/biobb_wf_amber)
- [AmberTools](https://ambermd.org/AmberTools.php)
- [ACPype](https://github.com/alanwilter/acpype)
