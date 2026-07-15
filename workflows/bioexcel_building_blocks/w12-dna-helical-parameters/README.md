# W-17 · DNA Helical Parameters

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

This workflow extracts structural and dynamical helical parameters from a DNA MD trajectory using the `biobb_dna` package (wrapping Curves+ and Canal). The example system is the Drew-Dickerson Dodecamer (sequence CGCGAATTCGCG, PDB code 1BNA), analyzed from a 500 ns MD trajectory taken from the BigNASim database. Curves+ extracts per-base-pair and per-base-pair-step helical parameters from the raw trajectory, Canal converts these into time series and histograms, and a large fan-out of downstream stages computes averages, time series, stiffness, bimodality, and correlations for every helical parameter (rise, roll, twist, shift, slide, tilt, shear, stretch, stagger, buckle, propeller, opening, inclination, tip, X/Y-displacement, groove widths/depths, backbone torsions, and sugar puckering/backbone conformational populations). Horus provisions the Curves+/biobb_dna conda environment automatically and runs all stages locally.

## Pipeline

```
curves              Extract helical parameters from trajectory (Curves+)
   │
canal               Generate time series and histograms (Canal)
   │
   ├── avg_*   (20 stages)   Average helical parameters: base-pair step (rise, roll, twist,
   │                         shift, slide, tilt), base pair (shear, stretch, stagger, buckle,
   │                         propeller, opening), axis (inclination, tip, x/y-disp), grooves
   │                         (major/minor width & depth)
   │
   ├── puckering, canonicalag, bipopulations
   │                         Sugar pucker, canonical alpha/gamma, and BI/BII backbone
   │                         conformational populations
   │
   ├── ts_*    (~34 stages)  Time series of every helical parameter and backbone torsion
   │                         (alpha/beta/gamma/delta/epsilon/zeta/chi, phase) per strand
   │
   ├── average_stiffness, basepair_stiffness
   │                         Stiffness / elastic constants for Twist and the CG step
   │
   ├── dna_bimodality        Bimodality analysis of Twist at the CG step
   │
   └── intraseqcorr, interseqcorr, intrahpcorr, interhpcorr, intrabpcorr, interbpcorr
                             Sequence and helical-parameter correlations (intra/inter base
                             pair, neighboring steps)
```

## Prerequisites

- **uv** (recommended) or pip — to install horus-runtime
- **micromamba**, **mamba**, or **conda** — the workflow executor builds a shared conda environment from `conda_env.yaml` to provision Curves+, Canal, and the biobb_dna stack

## Quick Start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# From the workflow directory, install horus-runtime
cd workflows/bioexcel_building_blocks/w12-dna-helical-parameters
uv sync
# or: pip install horus-runtime horus-environments

# Run the workflow
uv run horus run workflow.yaml
```

The first run builds the conda environment (this takes a few minutes). Subsequent runs reuse the cached environment at `../.horus_conda_env`.

## Inputs / Outputs

This workflow uses **real input trajectory data** checked into the directory (not fetched at runtime):
- `TRAJ/structure.stripped.nc` — 500 ns Drew-Dickerson Dodecamer MD trajectory (BigNASim, NAFlex_DDD_II entry)
- `TRAJ/structure.stripped.top` — associated AMBER topology
- `.curvesplus/standard_{b,i,s}.lib` — Curves+ standard base/backbone reference libraries used internally by the `biobb_curves` tool

**Outputs** (all under `workflow_results/`):
- `results/curves.out.lis`, `results/curves.out.cda` — raw Curves+ helical parameter output
- `results/canal.out.zip` — Canal time series/histogram bundle
- `results/avg_<param>.csv` — average value per helical parameter
- `results/ts_<param>.csv` — time series per helical parameter/torsion
- `results/stiffness.csv`, `results/bimodality.csv` — elastic and bimodality analysis
- `results/*corr.csv` — sequence and helical-parameter correlation matrices

## Configuration

`configs/curves.yaml` sets the strand base-pair ranges (`s1range`/`s2range`) passed to Curves+. `configs/canal.yaml` enables series/histogram output. Each `configs/avg_*.yaml` and `configs/ts_*.yaml` file selects which helical parameter and strand to extract. `configs/average_stiffness.yaml`, `configs/dna_bimodality.yaml`, and the `configs/*corr.yaml` files set the DNA sequence (CGCGAATTCGCG) and analysis parameters (e.g. `max_iter` for bimodality fitting).

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [biobb_dna](https://github.com/bioexcel/biobb_dna)
- [biobb_wf_dna_helparms tutorial notebook](https://github.com/bioexcel/biobb_wf_dna_helparms)
- [Curves+](https://curvesplus.bsc.es/)
- [BigNASim database](https://mmb.irbbarcelona.org/BIGNASim/)
- [NAFlex server](https://mmb.irbbarcelona.org/NAFlex)
