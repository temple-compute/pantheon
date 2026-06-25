# W-03 · Absolute Binding Free Energy Pipeline (Boltz-2 → ABFE → Molecular Dynamics)

![Status: draft](https://img.shields.io/badge/status-draft-lightgrey)
![Domain: Drug Discovery](https://img.shields.io/badge/domain-drug--discovery-blue)
![GTM: Tier 3](https://img.shields.io/badge/GTM-Tier%203-orange)

## Overview

Combines AI-predicted binding poses (Boltz-2) with physics-based absolute binding free energy (ABFE) calculations to produce highly accurate ΔG estimates for a set of lead compounds. ABFE is the gold standard for lead optimization but traditionally requires expert setup and significant compute. This workflow automates the full pipeline from AI pose prediction through MD simulation to final ΔG ranking.

This is a Tier 3 workflow: it targets a specialized audience (computational chemists with ABFE experience) and requires tight coordination between a GPU deep learning cluster and a CPU HPC cluster with InfiniBand. The Horus value is highest here — the two compute types have completely conflicting scheduler requirements, and manual handoff between them is the #1 pain point in computational chemistry.

**Target users:** Computational chemists at pharma companies, CROs, and advanced academic drug discovery groups.

---

## Compute Pattern

| Stage | Name | Cluster Type | Resources | Est. Walltime |
|-------|------|-------------|-----------|---------------|
| 1 | `AI_POSE_PREDICTION` | GPU — high-end (H100/A100-80GB) | 4–8×H100 | 30 min–2h |
| 2 | `SYSTEM_PREPARATION` | CPU cluster | 16–32 cores | 30 min–1h |
| 3 | `MD_SIMULATION` | HPC CPU cluster (MPI, InfiniBand) | 128–512 cores | 12–48h per compound |
| 4 | `FREE_ENERGY_ANALYSIS` | CPU cluster | 8 cores | 15–30 min |

**Critical transition:** Stage 3 requires tightly coupled MPI execution on InfiniBand-connected nodes — completely different infrastructure from stage 1's GPU cluster. This is the handoff Horus was built for.

---

## Tools & Dependencies

| Tool | Role | Source |
|------|------|--------|
| [Boltz-2](https://github.com/jwohlwend/boltz) | Initial binding pose prediction | MIT |
| [GROMACS](https://www.gromacs.org/) | MD engine for ABFE simulations | LGPL |
| [NAMD](https://www.ks.uiuc.edu/Research/namd/) | Alternative MD engine | Free for non-commercial |
| [AMBER](https://ambermd.org/) | Force field parameterization + MD | Commercial/academic |
| [OpenFF Toolkit](https://github.com/openforcefield/openff-toolkit) | Open-source small molecule parameterization | MIT |
| [alchemlyb](https://github.com/alchemistry/alchemlyb) | MBAR/BAR free energy analysis | BSD |
| [pymbar](https://github.com/choderalab/pymbar) | MBAR estimator | MIT |
| [MDAnalysis](https://www.mdanalysis.org/) | Trajectory analysis | GPL/LGPL |
| [RDKit](https://www.rdkit.org/) | Ligand preparation | BSD |

---

## Input / Output

**Inputs:**
- `target.pdb` — protein structure (crystal or predicted)
- `ligands.sdf` — lead compounds for ABFE (typically 5–50 compounds)
- `config.yaml` — workflow parameters (lambda windows, simulation length, force field choice)

**Outputs:**
- `results/abfe_results.csv` — predicted ΔG ± uncertainty for each compound
- `results/convergence_plots/` — convergence and overlap matrix plots per compound
- `results/ranked_leads.html` — interactive report with ΔG vs. experimental (if provided)

---

## Horus Configuration

```
Cluster A (stage 1):  GPU cluster — H100 or A100-80GB
                       gpus: 4–8

Cluster B (stage 3):  HPC CPU cluster — InfiniBand, MPI-capable
                       cores: 128–512
                       requires: InfiniBand or high-bandwidth interconnect
                       mpi: openmpi or mpich
                       Note: each compound is an independent MPI job;
                             fan out as array of MPI jobs, one per compound

Cluster C (stages 2,4): CPU cluster — any
                          cores: 16–32
```

**Data flow:**
- Stage 1 → Stage 2: predicted binding poses as PDB files (small)
- Stage 2 → Stage 3: GROMACS/AMBER input files per compound (~100MB per compound)
- Stage 3 → Stage 4: trajectory and energy files (~10–100GB per compound; keep on shared storage)

**Scheduler notes:**
- Stage 3 is an MPI job. Each compound runs as a separate MPI job across N nodes.
- Lambda window parallelization: each ABFE calculation uses multiple lambda windows that can run concurrently. Configure Horus to launch all windows per compound simultaneously.
- Total stage 3 compute scales linearly with number of compounds × simulation length × lambda windows.

---

## Parameterization

| Parameter | Description | Default |
|-----------|-------------|---------|
| `compounds` | List of compounds to run ABFE on | — (required) |
| `force_field` | `openff-2.1`, `gaff2`, or `amber14sb` | `openff-2.1` |
| `md_engine` | `gromacs` or `namd` | `gromacs` |
| `lambda_windows` | Number of alchemical lambda windows | `20` |
| `simulation_length_ns` | MD simulation length per lambda window | `5` |
| `equilibration_length_ns` | Equilibration time before production | `1` |
| `n_replicas` | Number of independent replicas per compound | `3` |
| `estimator` | Free energy estimator: `mbar` or `bar` | `mbar` |

---

## Implementation Notes

- ABFE calculations are sensitive to convergence. Always run multiple independent replicas (≥3) and check convergence plots before trusting ΔG values.
- The uncertainty on ABFE results is typically ±0.5–1.5 kcal/mol. Be explicit about this in reports.
- System preparation (stage 2) is the most expert-intensive step. Automation requires careful handling of protonation states, missing residues, and ligand parameterization. OpenFF Toolkit provides the most automatable path; GAFF2 is more established.
- GROMACS with GPU offloading can accelerate stage 3 if GPU nodes are available on the HPC cluster. This is a configuration option, not a requirement.
- For larger campaigns (>20 compounds), consider running RBFE (relative binding free energy) instead — cheaper and sufficient for SAR. RBFE workflow is a separate entry (not yet in this repo).

---

## Open Questions

- [ ] How does Horus handle InfiniBand-specific job scheduling requirements (node topology, NUMA binding)?
- [ ] Should system preparation (stage 2) include an automated protonation state prediction step (e.g., using Epik or OpenEye QUACPAC)?
- [ ] What is the recommended shared storage solution for large trajectory files between stages 3 and 4 when clusters A and B are different physical systems?
- [ ] Is there interest in supporting RBFE as an alternative to ABFE in this workflow?

---

## References

- [Boltz-2 binding affinity evaluation (arxiv 2026)](https://arxiv.org/html/2603.05532v1)
- [alchemlyb documentation](https://alchemlyb.readthedocs.io/)
- [GROMACS documentation](https://manual.gromacs.org/)
- [OpenFF Toolkit](https://github.com/openforcefield/openff-toolkit)
- [Boltz Upgrade: ABFE pipeline (Recursion, Oct 2025)](https://www.bio-itworld.com/news/2025/10/10/boltz-upgrade--recursion-researchers-release-pipeline-combining-ai-binding-model-with-absolute-binding-free-energies)
