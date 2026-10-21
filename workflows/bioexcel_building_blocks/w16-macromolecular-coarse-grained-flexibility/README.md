# W-21 · Macromolecular Coarse-Grained Flexibility

FlexServ coarse-grained flexibility from a single structure: Brownian dynamics, discrete MD and normal-mode ensembles, PCA compression, B-factors, hinges, stiffness and cross-ensemble similarity.

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

FlexServ coarse-grained flexibility analysis from a single structure (default: ribosomal protein S15, PDB 1A32). The structure is reduced to Calpha atoms and three ensembles are generated (Brownian dynamics, discrete MD, normal modes), each compressed with the PCA suite and analysed for eigenvectors, B-factors, hinges, stiffness, collectivity and cross-ensemble similarity, including a reference all-atom MD trajectory from MoDEL. The workflow has 48 tasks.

## Pipeline

```
fetch_pdb -> extract_atoms_ca               Calpha-only model
bd_run / dmd_run / nma_run -> cpptraj_rms_*  BD, DMD and NMA ensembles with RMSD
pcz_zip_* -> pcz_unzip_* -> cpptraj_rms_*_uncompressed   PCA compression and round-trip check
pcz_info, pcz_evecs                           PCA report and eigenvectors
pcz_animate -> cpptraj_convert_proj1          PC1 animation
pcz_bfactor_all, pcz_bfactor_mode1..5         B-factors per PCA mode
pcz_hinges_bfactor / _dyndom / _fcte          Hinge points (3 methods)
pcz_stiffness, pcz_collectivity               Stiffness, collectivity index
pcz_similarity_*                              16 pairwise similarities across BD/DMD/NMA/MD
```

## Inputs / Outputs

Outputs (`results/`, file names keep the `1a32` prefix):
- `1a32.pdb`, `1a32_ca.pdb`: downloaded and Calpha structures
- `{bd,dmd,nma}_ensemble.mdcrd` and `.pcz`, plus `.xtc` and RMSD `.dat`; `*_uncompressed.*` from the round-trip check
- `pcz_report.json`, `pcz_evecs.json`, `pcz_proj1.crd`/`.xtc`
- `bfactor_all.*`, `bfactor_mode1-5.*`
- `hinges_{bfactor,dyndom,fcte}_report.json`, `pcz_stiffness.json`, `pcz_collectivity.json`
- `pcz_similarity_*.json`

## Parameters

| id | Default | Meaning |
|---|---|---|
| `pdb_id` | `1a32` | PDB code to download; leave empty to use `structure`. |
| `structure` | `examples/1a32.pdb` | PDB file used when `pdb_id` is empty. |
| `bd_time` | 10000 | Brownian dynamics length in ps (1000-1000000). |
| `nma_frames` | 50 | Frames generated along the normal modes (10-2000). |
| `pca_variance` | 90 | Explained variance kept in PCZ compression (50-99). |
| `md_pcz` | `Files/1a32.MoDEL.pcz` | Reference all-atom MD in PCZ format, 10 ns of 1A32 from MoDEL. Used only for the similarity analyses; must have the same Calpha atoms as the input structure. |

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [biobb_flexserv](https://github.com/bioexcel/biobb_flexserv)
- [FlexServ web server](https://mmb.irbbarcelona.org/FlexServ/)
- [PCA suite](https://mmb.irbbarcelona.org/software/pcasuite/)
- [BioExcel FlexServ tutorial](https://biobb-wf-flexserv.readthedocs.io)
