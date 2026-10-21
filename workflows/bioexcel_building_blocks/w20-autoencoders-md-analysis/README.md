# W-25 · AutoEncoders for MD Analysis

Train an autoencoder on an apo MD trajectory, compare its latent space with the holo trajectory, check reconstruction by RMSF, and export the model as PLUMED collective variables for enhanced sampling.

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

Trains an autoencoder (biobb_pytorch) on an apo MD trajectory from MDDB (default: PDB 6W9C, MCV1900210), compares its latent space with a holo trajectory of the same protein (default MCV1900212), checks reconstruction quality by RMSF, and exports the model as a PLUMED collective variable. Both trajectories are fitted and featurized as Calpha Cartesian coordinates. The workflow has 16 tasks.

## Pipeline

```
fetch_train_trajectory -> fit_train_trajectory -> featurize_train_trajectory    Apo trajectory
build_model -> train_model                                                      Autoencoder, trained on apo
fetch_test_trajectory -> fit_test_trajectory -> featurize_test_trajectory       Holo trajectory
evaluate_model -> reconstruct_trajectory                                        Latent space, reconstructed holo
make_ndx_apo / make_ndx_holo                                                    Calpha index files
gmx_rmsf_apo / gmx_rmsf_holo / gmx_rmsf_holo_recon                              RMSF profiles
make_plumed                                                                     PLUMED CV and bias input
```

## Inputs / Outputs

Inputs are two MDDB projects of the same protein: the apo (training) and holo (test) trajectories. The autoencoder hidden layers are fixed (encoder 933, 747, 561, 375, 189; decoder mirrored); the input and output layers follow the protein automatically (3 x Calpha atoms of the featurized apo trajectory). Outputs (`results/`):
- `{apo,holo}.pdb/.xtc`, `*_fit.xtc`, `*.pt`, `*_stats.pt`: raw, fitted and featurized trajectories
- `model.pth`, `apo_trained_model.pth`, `model_training_metrics.npz`: untrained and trained model, training curves
- `apo_eval_results.npz`: evaluation and latent-space results
- `holo_recon.xtc/.pdb`: reconstructed holo trajectory
- `{apo,holo}.ndx`, `*_rmsf.xvg`, `holo_recon_rmsf.xvg`: index files and RMSF profiles
- `plumed_model.ptc`, `plumed.dat`, `features.dat`: PLUMED collective-variable model and input files

## Parameters

| id | Default | Meaning |
|---|---|---|
| `train_mddb_project` | MCV1900210 | MDDB project of the apo trajectory the autoencoder is trained on. |
| `test_mddb_project` | MCV1900212 | MDDB project of the holo trajectory projected onto the latent space; same protein as the training project. |
| `n_frames` | 10000 | Frames downloaded per trajectory, from frame 1 (100-10000). |
| `n_cvs` | 3 | Latent space size, i.e. number of collective variables (1-10). |
| `max_epochs` | 100 | Maximum training epochs (1-2000). |
| `batch_size` | 128 | Training batch size (8-4096). |

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [biobb_pytorch](https://github.com/bioexcel/biobb_pytorch)
- [GROMACS](https://www.gromacs.org)
- [PLUMED](https://github.com/plumed/plumed2)
- [MDDB — MoDEL Database](https://mddbr.eu/)
- [BioExcel AutoEncoder tutorial](https://biobb-wf-autoencoder.readthedocs.io)
