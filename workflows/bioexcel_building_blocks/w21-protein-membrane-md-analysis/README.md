# W-26 · Protein-Membrane MD Analysis

Analyse a protein-membrane MD trajectory from MDDB: leaflets, lipid z-positions, order parameters, area per lipid, density profile, channel pore radius and lipid flip-flop.

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

Analyses a protein-membrane MD trajectory downloaded from MDDB (default A023K: a GABA-gated chloride channel in a DPPC bilayer). The trajectory is fitted so the membrane lies in the xy-plane, leaflets are identified with FATSLiM and Lipyphilic, and the workflow computes lipid z-positions, order parameters, area per lipid, density profile, channel pore radius and lipid flip-flop. The workflow has 12 tasks.

## Pipeline

```
download_trajectory                     Structure, trajectory and tpr from MDDB
fit_membrane -> fit_protein             Fit to membrane normal (rot+trans), then to protein (xy translation)
identify_leaflets_fatslim -> assign_leaflets    Leaflet identification and per-frame assignment
compute_zpositions, compute_zpositions_around   Lipid z-positions, whole membrane and around the protein
compute_order_parameters                Deuterium order parameters of acyl tails
compute_area_per_lipid                  Area per lipid, 2D Voronoi
compute_density_profile                 Density profile along z
compute_pore_dimensions                 Channel pore-radius profile (HOLE)
compute_flip_flop                       Lipid flip-flop events
```

## Inputs / Outputs

The lipid selections in `configs/` assume a DPPC bilayer, so another entry must also be DPPC. Output file names keep the `A023K` prefix. Outputs (`results/`):
- `A023K_10.pdb`, `A023K_10.xtc`, `A023K.tpr`: downloaded structure, trajectory, topology
- `A023K_fit.xtc`, `A023K_fit2.xtc`: membrane-fitted and protein-fitted trajectories
- `leaflets.ndx`, `leaflets_data.csv`: leaflet groups and per-frame assignment
- `zpositions.csv`, `zpositions_around.csv`, `order.csv`, `apl.csv`, `density.dat`
- `hole.vmd`, `hole_profile.csv`: pore-radius profile
- `flip_flop.csv`: flip-flop events

## Parameters

| id | Default | Meaning |
|---|---|---|
| `mddb_project` | `A023K` | MDDB accession of a protein in a DPPC membrane. |
| `frame_stride` | 1000 | Keep every Nth frame when downloading (1-10000). |
| `pore_frame_step` | 20 | Analyse the pore radius every Nth downloaded frame (1-1000). |

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [biobb_mem](https://github.com/bioexcel/biobb_mem)
- [FATSLiM](https://pythonhosted.org/fatslim/)
- [Lipyphilic](https://lipyphilic.readthedocs.io)
- [MDDB](https://mddbr.eu/)
- [BioExcel protein-membrane MD analysis tutorial](https://biobb-wf-mem.readthedocs.io)
