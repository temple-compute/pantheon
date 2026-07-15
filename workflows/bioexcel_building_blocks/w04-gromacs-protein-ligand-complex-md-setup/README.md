# W-09 · GROMACS Protein-Ligand Complex MD Setup

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

This workflow runs a complete molecular dynamics setup for a protein-ligand complex using GROMACS: the **T4 lysozyme L99A/M102Q** protein (PDB: 3HTB) in complex with the small molecule **2-propylphenol** (ligand code JZ4). Starting from the raw PDB file, it splits the structure into protein and ligand, builds an AMBER99SB-ILDN topology for the protein and a GAFF/ACPype topology for the ligand, merges them into a single restrained complex, solvates and ionizes the system, energy-minimizes it, runs NVT/NPT equilibration, and finishes with a free production MD simulation. Horus provisions the full GROMACS/biobb conda environment (biobb_io, biobb_model, biobb_chemistry, biobb_gromacs, biobb_analysis, biobb_structure_utils) automatically for each stage and routes every task to the local machine — swapping any stage to a remote cluster is a one-line `target:` change.

## Pipeline

```
fetch_pdb                    Download 3HTB (T4 lysozyme + JZ4) from PDB
   │
   ├─ extract_heteroatoms     Extract JZ4 ligand (biobb_structure_utils)
   │     │
   │  reduce_add_hydrogens    Add hydrogens to ligand (Reduce)
   │     │
   │  babel_minimize          Energetically minimize ligand hydrogens (OpenBabel GAFF)
   │     │
   │  acpype_params_gmx       Generate ligand GROMACS topology (ACPype / amberGAFF)
   │     │
   │  make_ndx_ligand ──► genrestr   Ligand position restraints (1000 kJ/mol·nm²)
   │
   └─ extract_molecule        Extract protein chain
         │
      fix_side_chain          Model missing side-chain atoms
         │
      pdb2gmx                 Build protein topology (amber99sb-ildn, SPC/E)
         │
trjconv_protein + trjconv_ligand   Convert GRO → PDB (with hydrogens)
         │
      cat_pdb_complex          Concatenate protein + ligand → complex structure
         │
      append_ligand             Merge ligand topology into protein topology
         │
      editconf                  Define truncated octahedron box (0.8 nm)
         │
      solvate                   Fill box with SPC water molecules
         │
grompp_ions ──► genion            Add neutralizing NaCl ions
         │
grompp_minimize ──► mdrun_minimize ──► gmx_energy_min   Energy minimization (steepest descent)
         │
      make_ndx_complex           Index file for protein-ligand complex group
         │
grompp_nvt ──► mdrun_nvt ──► gmx_energy_nvt   NVT equilibration (restrained)
         │
grompp_npt ──► mdrun_npt ──► gmx_energy_npt   NPT equilibration (restrained)
         │
grompp_free ──► mdrun_free        Free production MD (50 ps, unrestrained)
         │
gmx_rms_first / gmx_rms_exp / gmx_rgyr   RMSd (vs minimized & experimental) and radius of gyration
         │
gmx_image                          Center complex, strip periodic-boundary artifacts
         │
gmx_trjconv_str_dry                Extract final dry protein-ligand structure
```

## Prerequisites

- **uv** (recommended) or pip — to install horus-runtime
- **micromamba**, **mamba**, or **conda** — the workflow executor builds a shared conda environment from `conda_env.yaml` to provision GROMACS and the biobb stack

## Quick Start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# From the workflow directory, install horus-runtime
cd workflows/bioexcel_building_blocks/w04-gromacs-protein-ligand-complex-md-setup
uv sync
# or: pip install horus-runtime horus-environments

# Run the workflow
uv run horus run workflow.yaml
```

The first run builds the conda environment (this takes a few minutes). Subsequent runs reuse the cached environment at `../.horus_conda_env`.

## Inputs / Outputs

This workflow has no file inputs — it fetches 3HTB from the RCSB PDB automatically and extracts both the protein chain and the JZ4 ligand from it.

**Outputs** (all under `results/`):
- `downloaded.pdb`, `ligand.pdb`, `protein.pdb`, `fixed.pdb` — fetched and split structures
- `pdb2gmx.gro`, `pdb2gmx_top.zip` — protein topology
- `ligand.params.gro`, `ligand.params.itp`, `ligand.params.top` — ligand (GAFF) topology
- `ligand_posres.itp` — ligand position restraints
- `complex_H.pdb`, `complex_top.zip` — merged protein-ligand complex and topology
- `ionized.gro`, `ionized_top.zip` — solvated, neutralized system
- `min_energy.xvg`, `nvt_temp.xvg`, `npt_PD.xvg` — energy/temperature/pressure-density traces
- `md.gro`, `md.trr` — free production MD trajectory
- `rms_first.xvg`, `rms_exp.xvg`, `rgyr.xvg` — analysis (RMSd, radius of gyration)
- `dry.gro` — final dry protein-ligand structure (solvent stripped)

## Configuration

- `configs/fetch_pdb.yaml`, `configs/extract_heteroatoms.yaml` — target PDB code (3HTB) and ligand code (JZ4)
- `configs/pdb2gmx.yaml` — protein force field and water model
- `configs/acpype_params_gmx.yaml`, `configs/babel_minimize.yaml`, `configs/reduce_add_hydrogens.yaml` — ligand parameterization settings (GAFF charges, pH, minimization)
- `configs/editconf.yaml`, `configs/genion.yaml`, `configs/genrestr.yaml` — box geometry, ion concentration, restraint force constants
- `configs/grompp_minimize.yaml`, `configs/grompp_nvt.yaml`, `configs/grompp_npt.yaml`, `configs/grompp_free.yaml` — GROMACS `mdp` parameters (time step, temperature, pressure, simulation length) for each MD stage

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [GROMACS](https://www.gromacs.org)
- [ACPype](https://github.com/alanwilter/acpype)
- [Official GROMACS protein-ligand complex tutorial](http://www.mdtutorials.com/gmx/complex/index.html)
- [BioExcel protein-ligand complex MD setup tutorial](https://biobb-wf-protein-complex-md-setup.readthedocs.io)
