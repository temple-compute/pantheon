# W-20 · Protein Conformational Transitions

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

This workflow computes a conformational transition pathway between two known structural states of a protein using GOdMD, illustrated with adenylate kinase transitioning from its closed state (PDB: 1AKE) to its open state (PDB: 4AKE). It fetches both structures, extracts chain A from each, removes the AP5 inhibitor ligand from the origin structure, computes a residue mapping between origin and target via EMBOSS sequence alignment, runs the GOdMD discrete-molecular-dynamics/Maxwell-Demon transition simulation, and converts the resulting trajectory to XTC format for visualization. Horus provisions the GOdMD/EMBOSS/biobb conda environment automatically and runs all stages locally.

## Pipeline

```
fetch_pdb_origin          Download 1AKE (closed state) from the PDB
   │
extract_chain_origin       Extract chain A
   │
remove_molecules_origin     Remove AP5 inhibitor ligand
   │                                    fetch_pdb_target          Download 4AKE (open state) from the PDB
   │                                       │
   │                                    extract_chain_target       Extract chain A
   │                                       │
   └───────────────────► godmd_prep ◄──────┘   Compute residue mapping (EMBOSS water alignment)
                              │
                         godmd_run              Run GOdMD conformational transition (1AKE → 4AKE)
                              │
                         cpptraj_convert         Convert trajectory mdcrd → XTC
```

## Prerequisites

- **uv** (recommended) or pip — to install horus-runtime
- **micromamba**, **mamba**, or **conda** — the workflow executor builds a shared conda environment from `conda_env.yaml` to provision GOdMD, EMBOSS, and the biobb stack

## Quick Start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# From the workflow directory, install horus-runtime
cd workflows/bioexcel_building_blocks/w15-protein-conformational-transitions
uv sync
# or: pip install horus-runtime horus-environments

# Run the workflow
uv run horus run workflow.yaml
```

The first run builds the conda environment (this takes a few minutes). Subsequent runs reuse the cached environment at `../.horus_conda_env`.

## Inputs / Outputs

This workflow has no file inputs — it fetches PDB 1AKE (origin) and 4AKE (target) automatically from the RCSB (`configs/fetch_pdb_origin.yaml`, `configs/fetch_pdb_target.yaml`).

**Outputs** (all under `workflow_results/`):
- `results/1ake.pdb`, `results/4ake.pdb` — downloaded origin/target structures
- `results/1ake.chains.pdb`, `results/4ake.chains.pdb` — chain-A-only structures
- `results/1ake.chains.nolig.pdb` — origin structure with AP5 ligand removed
- `results/1ake.aln`, `results/4ake.aln` — residue-mapping sequence alignments
- `results/1ake-4ake.godmd.mdcrd` — raw GOdMD transition trajectory
- `results/1ake-4ake.godmd.pdb` — GOdMD topology/reference structure
- `results/1ake-4ake.godmd.xtc` — transition trajectory converted to XTC for visualization

## Configuration

`configs/fetch_pdb_origin.yaml` / `configs/fetch_pdb_target.yaml` set the origin/target PDB codes. `configs/extract_chain_origin.yaml` / `configs/extract_chain_target.yaml` set which chain to keep. `configs/remove_molecules_origin.yaml` sets which ligand/heteroatom to strip from the origin structure. `configs/godmd_prep.yaml` controls the EMBOSS alignment used for residue mapping. `configs/godmd_run.yaml` controls the GOdMD simulation parameters (number of trajectories, temperature, sampling steps). `configs/cpptraj_convert.yaml` controls the output trajectory format.

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [biobb_godmd](https://github.com/bioexcel/biobb_godmd)
- [biobb_wf_godmd tutorial notebook](https://github.com/bioexcel/biobb_wf_godmd)
- [GOdMD web server](https://mmb.irbbarcelona.org/GOdMD/index.php)
- [Exploration of conformational transition pathways from coarse-grained simulations (Sfriso et al., Bioinformatics)](https://doi.org/10.1093/bioinformatics/btt324)
- [EMBOSS](https://www.ebi.ac.uk/Tools/emboss/)
