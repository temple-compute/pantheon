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

The entry must be a single-lipid bilayer whose lipid residue name is `lipid_resname`; the lipid headgroups are selected as its phosphorus atoms. Outputs (`results/`):
- `structure.pdb`, `trajectory.xtc`, `topology.tpr`: downloaded structure, trajectory, topology
- `membrane_fit.xtc`, `protein_fit.xtc`: membrane-fitted and protein-fitted trajectories
- `leaflets.ndx`, `leaflets_data.csv`: leaflet groups and per-frame assignment
- `zpositions.csv`, `zpositions_around.csv`, `order.csv`, `apl.csv`, `density.dat`
- `hole.vmd`, `hole_profile.csv`: pore-radius profile
- `flip_flop.csv`: flip-flop events

## Parameters

| id | Default | Meaning |
|---|---|---|
| `mddb_project` | `A023K` | MDDB accession of a protein in a lipid bilayer. |
| `lipid_resname` | `DPPC` | Lipid residue name (1-4 characters). Its phosphorus atoms (element P) are the headgroup selection for leaflets, z-positions, area per lipid and flip-flop; the membrane fit uses the GROMACS index group of the same name. The density profile uses the first 3 characters, because cpptraj reads 3-character PDB residue names. |
| `frame_stride` | 1000 | Keep every Nth frame when downloading (1-10000). |
| `pore_frame_step` | 20 | Analyse the pore radius every Nth downloaded frame (1-1000). |

## References

- [FATSLiM](https://pythonhosted.org/fatslim/)
- [Lipyphilic](https://lipyphilic.readthedocs.io)
- [biobb_mem](https://github.com/bioexcel/biobb_mem)
- [GROMACS](https://www.gromacs.org)
- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [MDDB](https://mddbr.eu/)
- [BioExcel protein-membrane MD analysis tutorial](https://biobb-mem.readthedocs.io)
