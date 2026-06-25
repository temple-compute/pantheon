# W-08 · Climate/Weather AI Emulator (Physics Simulation → ML Surrogate → Fast Inference)

![Status: draft](https://img.shields.io/badge/status-draft-lightgrey)
![Domain: Scientific Computing](https://img.shields.io/badge/domain-scientific--computing-teal)
![GTM: Tier 2](https://img.shields.io/badge/GTM-Tier%202-blue)

## Overview

Trains a machine learning surrogate model on top of a physics-based climate or weather simulation, then deploys the surrogate for fast ensemble inference at a fraction of the cost of the original simulator. A single surrogate model can run thousands of climate scenarios in the time the physics model would take to run one.

This workflow demonstrates Horus's most technically complex multi-cluster pattern: stage 1 is a tightly coupled MPI job on a traditional HPC cluster (InfiniBand required); stage 3 is a GPU-intensive deep learning training job. These have completely different infrastructure requirements and are normally run on separate, independently managed systems. Horus makes the handoff automatic.

**Operational precedent:** ECMWF's AIFS (AI Integrated Forecasting System) has been running operationally on EuroHPC supercomputers daily since 2025. This is no longer experimental.

**Target users:** Climate scientists, national weather services, climate risk analytics companies, environmental consultancies.

---

## Compute Pattern

| Stage | Name | Cluster Type | Resources | Est. Walltime |
|-------|------|-------------|-----------|---------------|
| 1 | `PHYSICS_SIMULATION` | HPC CPU/GPU cluster (MPI, InfiniBand) | 128–1024 cores | 24–96h |
| 2 | `DATA_PREPROCESSING` | CPU cluster | 32–64 cores | 2–6h |
| 3 | `SURROGATE_TRAINING` | GPU cluster (H100/A100) | 16–64×A100 | 6–24h |
| 4 | `VALIDATION` | GPU cluster — mid-tier | 4–8×A100 | 2–4h |
| 5 | `ENSEMBLE_INFERENCE` | GPU cluster — auto-scale | 8–64×A100 | 1–4h per ensemble |

---

## Tools & Dependencies

| Tool | Role | Source |
|------|------|--------|
| [WRF](https://github.com/wrf-model/WRF) | Weather Research and Forecasting model (physics) | public domain |
| [OpenIFS](https://confluence.ecmwf.int/display/OIFS) | ECMWF Integrated Forecasting System | ECMWF license |
| [ICON](https://www.dwd.de/EN/research/weatherforecasting/num_modelling/01_nummodellierung/icon_en.html) | German Weather Service NWP model | BSD (open source core) |
| [ClimSim](https://github.com/leap-stc/ClimSim) | ML emulation framework + datasets | MIT |
| [ACE2](https://github.com/ai2cm/ace) | Atmospheric emulator (Allen AI) | Apache 2.0 |
| [Anemoi](https://github.com/ecmwf/anemoi-training) | ECMWF's ML weather training framework | Apache 2.0 |
| [xarray](https://xarray.dev/) | N-D labeled array processing for climate data | Apache 2.0 |
| [zarr](https://zarr.readthedocs.io/) | Chunked, compressed array storage | MIT |
| [PyTorch / Lightning](https://lightning.ai/) | ML training framework | BSD/Apache |
| [wandb / MLflow](https://wandb.ai/) | Experiment tracking | Commercial / Apache 2.0 |

---

## Input / Output

**Inputs (stage 1):**
- `sim_config/` — physics model configuration files (WRF namelist, ICON grid, etc.)
- `initial_conditions/` — ERA5 or model analysis initial conditions (NetCDF/GRIB)
- `config.yaml` — workflow parameters

**Outputs:**
- `artifacts/surrogate_model/` — trained ML surrogate weights
- `results/validation_metrics.json` — RMSE, skill scores vs. held-out simulation runs
- `results/ensemble/` — surrogate inference outputs as NetCDF/zarr archives
- `results/validation_report.html` — skill score maps, bias analysis

---

## Horus Configuration

```
Cluster A (stage 1):   HPC CPU cluster — MPI, InfiniBand
                        cores: 128–1024 (MPI ranks)
                        requires: InfiniBand or equivalent high-bandwidth interconnect
                        requires: high-performance parallel filesystem (Lustre, GPFS)
                        Note: this is a tightly-coupled MPI job — all ranks must
                              start simultaneously and communicate during execution

Cluster B (stages 3,4,5): GPU cluster — H100 or A100
                             gpus: 16–64×A100 for training
                             gpus: 8–64×A100 for ensemble (auto-scale)

Cluster C (stage 2):   CPU cluster — high-memory
                        cores: 32–64, RAM: 256GB+
                        Note: climate data preprocessing requires significant RAM
                              for NetCDF/GRIB manipulation
```

**Data flow:**
- Stage 1 → Stage 2: simulation output files (NetCDF/GRIB, potentially TB-scale)
- Stage 2 → Stage 3: ML-ready tensors as zarr arrays (~100GB–1TB)
- Stage 3 → Stage 4/5: trained model weights (~GB range)

**Critical note:** The simulation output (stage 1) can be terabytes. Horus must coordinate access to a shared high-performance filesystem accessible by both the HPC cluster (stage 1) and the preprocessing cluster (stage 2). This is the most complex data handoff in this catalog.

**Scheduler notes:**
- Stage 1 is tightly coupled MPI — all nodes must be co-allocated and start together.
- Stage 5 (ensemble inference) is embarrassingly parallel; fan out across available GPUs.

---

## Parameterization

| Parameter | Description | Default |
|-----------|-------------|---------|
| `physics_model` | `wrf`, `openifs`, or `icon` | `wrf` |
| `simulation_domain` | Geographic domain (WRF config or lat/lon box) | — (required) |
| `simulation_length_days` | Length of each simulation run | `30` |
| `n_training_simulations` | Number of sim runs to generate training data | `100` |
| `surrogate_architecture` | `ace2`, `spherical-fno`, or `custom` | `ace2` |
| `target_variables` | Climate variables to emulate | `["T", "U", "V", "Q", "Z"]` |
| `ensemble_size` | Number of surrogate inference rollouts | `50` |
| `lead_time_days` | Forecast lead time for ensemble | `14` |

---

## Implementation Notes

- WRF MPI jobs require specific core-count constraints (domain decomposition must divide evenly). Document the valid core counts for common domain configurations.
- Climate simulation output files are often in GRIB or NetCDF3 format. Convert to zarr in stage 2 for efficient tensor access during training.
- ACE2 is the most production-ready open-source surrogate architecture for global atmospheric emulation (Allen AI, 2024–2025).
- Anemoi (ECMWF, Apache 2.0) provides a complete training + evaluation pipeline compatible with ECMWF model output.
- Ensemble inference with the surrogate (stage 5) replaces the need to run the physics model multiple times for uncertainty quantification — this is typically a 100–1000× cost reduction.
- Skill score validation should compare against held-out simulation runs, not just reanalysis (ERA5), to properly measure surrogate quality.

---

## Open Questions

- [ ] How does Horus handle terabyte-scale data handoffs between clusters with different storage systems (Lustre on HPC vs. object storage on GPU cluster)?
- [ ] Should stage 1 support CMIP6 data download as an alternative to running physics simulations from scratch?
- [ ] Is there a standard Horus pattern for MPI job submission with topology-aware scheduling?
- [ ] Should the workflow include an optional downscaling step (HiRO-ACE / statistical downscaling) after ensemble inference?

---

## References

- [ECMWF: Powering the AI Weather Revolution (2026)](https://www.ecmwf.int/en/about/media-centre/focus/2026/powering-ai-weather-revolution-era5-ai-ready-pipelines)
- [ACE2 paper (Allen AI, 2024)](https://arxiv.org/pdf/2411.11268)
- [HiRO-ACE: 3km global storm-resolving emulator](https://arxiv.org/pdf/2512.18224)
- [ClimSim-Online framework](https://arxiv.org/html/2306.08754v6)
- [Anemoi GitHub (ECMWF)](https://github.com/ecmwf/anemoi-training)
- [Machine Learning Workflows in Climate Modeling (arxiv, 2025)](https://arxiv.org/pdf/2510.03305)
- [Twelve Tips for AI-Driven HPC Workflows (arxiv, 2026)](https://arxiv.org/html/2606.07491)
