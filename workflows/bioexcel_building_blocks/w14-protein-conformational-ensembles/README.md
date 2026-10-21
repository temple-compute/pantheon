# W-19 · Protein Conformational Ensembles

Generate protein conformational ensembles with five coarse-grained methods (CONCOORD, ProDy ANM, FlexServ BD/DMD/NMA, NOLB, iMODS), cluster the meta-trajectory and analyse its principal motions.

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

Generates protein conformational ensembles with five coarse-grained methods (CONCOORD, ProDy ANM, FlexServ BD/DMD/NMA, NOLB, iMODS), illustrated with adenylate kinase (PDB 1AKE, chain A). All ensembles are concatenated into a meta-trajectory, clustered with GROMACS, and analysed by PCA for B-factors, hinge points, stiffness and collectivity. The workflow has 43 tasks.

## Pipeline

```
fetch_pdb -> extract_model -> extract_chain -> cpptraj_mask_backbone / cpptraj_mask_ca
concoord_dist -> concoord_disco -> cpptraj_rms_concoord -> cpptraj_convert_concoord    CONCOORD
prody_anm -> cpptraj_rms_prody -> cpptraj_convert_prody                                ProDy ANM
bd_run / dmd_run / nma_run -> cpptraj_rms_* (-> cpptraj_convert_nma)                   FlexServ BD / DMD / NMA
nolb_nma -> cpptraj_rms_nolb -> cpptraj_convert_nolb                                   NOLB
imod_imode -> imod_imc -> cpptraj_rms_imods -> cpptraj_convert_imods                   iMODS
zip_trajectories -> trjcat                         Concatenate ensembles into meta-trajectory
make_ndx -> gmx_cluster -> cpptraj_rms_meta        Cluster meta-trajectory (GROMACS)
pcz_zip_classic / pcz_zip_gaussian                 PCA compression
pcz_info, pcz_evecs                                PCA statistics and eigenvectors
pcz_animate -> cpptraj_convert_proj                Animate along PC1
pcz_bfactor                                        B-factors from PCA modes
pcz_hinges_bfactor / _dyndom / _fcte               Hinge points (3 methods)
pcz_stiffness, pcz_collectivity                    Apparent stiffness, collectivity index
```

## Inputs / Outputs

Outputs (`results/`):
- `input.pdb` and the extracted model, monomer and masks
- Per-method ensemble trajectories (`.trr`) and RMSD `.dat` files
- `concat_traj.*`, `concat_cluster.pdb`, `meta_traj_*`: meta-trajectory and GROMACS cluster output
- `concat_ensemble.pcz`, `concat_ensemble_gaussian.pcz`: compressed PCA trajectories
- `bfactor_all.*`, `hinges_{bfactor,dyndom,fcte}_report.json`, `pcz_stiffness.json`, `pcz_collectivity.json`: flexibility analysis

## Parameters

| id | Default | Meaning |
|---|---|---|
| `pdb_id` | `1ake` | PDB code to download; leave empty to use `structure`. |
| `structure` | `examples/1ake.pdb` | PDB file used when `pdb_id` is empty. |
| `chain` | `A` | Chain to analyse. |
| `n_structures` | 300 | Conformations per ensemble method (10-5000). |
| `cluster_cutoff_nm` | 0.12 | RMSD cutoff of the GROMACS linkage clustering (0.02-1.0). |

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [biobb_flexdyn](https://github.com/bioexcel/biobb_flexdyn)
- [biobb_flexserv](https://github.com/bioexcel/biobb_flexserv)
- [biobb_wf_flexdyn tutorial notebook](https://github.com/bioexcel/biobb_wf_flexdyn)
- [CONCOORD](https://www3.mpibpc.mpg.de/groups/de_groot/concoord/concoord.html)
- [ProDy](https://github.com/prody/ProDy)
- [FlexServ](https://mmb.irbbarcelona.org/FlexServ/)
- [NOLB](https://team.inria.fr/nano-d/software/nolb-normal-modes)
- [iMODS](https://imods.chaconlab.org/)
