# W-45 · UMA Nitro Molecular Dynamics

Relax any structure and run NVT molecular dynamics with Meta's UMA machine-learned potential in its fast UMA Nitro mode on one GPU.

![Domain: Chemistry](https://img.shields.io/badge/domain-chemistry-blue)

## Overview

Relaxes an uploaded structure and runs Langevin NVT dynamics with [UMA](https://github.com/facebookresearch/fairchem) (`uma-s-1p2p1`, fairchem-core 2.24.0, Meta FAIR Chemistry), a universal potential for molecules, materials, catalysts, MOFs and molecular crystals. UMA's default inference mode is UMA Nitro: single-GPU kernels with CUDA graphs and TF32, on NVIDIA Ampere or newer. The run summary records the mode that actually ran and the speed in ns/day. The workflow has 3 tasks.

The UMA checkpoints are gated on Hugging Face. Request access at [facebook/UMA](https://huggingface.co/facebook/UMA), store a token from the approved account as a credential, and pick it for `hf_token` when you launch.

## Pipeline

```
relax   FIRE relaxation with UMA          ──► results/relaxed.extxyz
md      Langevin NVT with UMA Nitro       ──► results/trajectory.extxyz, thermo.csv, md_summary.json
report  temperature/energy plots, speed   ──► results/report.html
```

## Inputs / Outputs

- `structure`: any ASE-readable file (extxyz, xyz, cif, POSCAR, pdb, sdf). Keep the cell and `pbc` for periodic systems. The example is a periodic box of 64 water molecules.
- `results/trajectory.extxyz`: one frame every `save_every` steps.
- `results/thermo.csv`: `step, time_ps, epot_eV, ekin_eV, etot_eV, temperature_K`.
- `results/md_summary.json`: model, task, `inference_mode`, GPU, atoms, steps, `ns_per_day`.
- `results/report.html`: the summary plus temperature and energy over time.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `structure` | `examples/water_box.extxyz` | Input structure |
| `task_name` | `omol` | UMA head: `omol`, `omat`, `oc20`, `oc22`, `oc25`, `odac` or `omc` |
| `charge` | 0 | Total charge (`omol` only) |
| `spin` | 1 | Spin multiplicity (`omol` only) |
| `relax_steps` | 200 | Maximum FIRE steps; 0 skips the relaxation. The cell relaxes too for periodic `omat` systems |
| `fmax` | 0.05 | Relaxation force threshold (eV/Å) |
| `temperature_K` | 300 | Thermostat temperature (K) |
| `timestep_fs` | 0.5 | MD timestep (fs) |
| `md_steps` | 10000 | MD steps (5 ps at 0.5 fs) |
| `save_every` | 10 | Steps between trajectory frames and thermo rows |
| `hf_token` (secret) | none | Hugging Face token with access to `facebook/UMA` |

## References

- [fairchem GitHub](https://github.com/facebookresearch/fairchem) and its [UMA Nitro PR](https://github.com/facebookresearch/fairchem/pull/2245)
- [UMA models on Hugging Face](https://huggingface.co/facebook/UMA)
- [UMA paper (arXiv:2506.23971)](https://arxiv.org/abs/2506.23971)
- [ASE (Atomic Simulation Environment)](https://ase-lib.org/)
