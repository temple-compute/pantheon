# W-01 · Structure Prediction + Virtual Screening (Boltz-2 → DiffDock)

![Status: draft](https://img.shields.io/badge/status-draft-lightgrey)
![Domain: Drug Discovery](https://img.shields.io/badge/domain-drug--discovery-blue)
![GTM: Tier 1](https://img.shields.io/badge/GTM-Tier%201-green)

## Overview

Given a target protein and a library of candidate small-molecule ligands, this workflow predicts binding structures and affinity scores using Boltz-2, then refines the top hits with a docking engine (DiffDock or AutoDock-GPU). The output is a ranked shortlist of candidates with predicted binding poses and ΔG estimates, ready for wet-lab follow-up.

This is one of the most requested workflows in computational drug discovery today. Boltz-2 (MIT + Recursion, 2025) delivers binding affinity prediction at 1000× the speed of classical free energy perturbation, making large-scale virtual screening tractable. The bottleneck is compute: Boltz-2 requires ≥40GB VRAM per instance, but those expensive nodes are only needed for one stage.

**Target users:** Computational chemists, pharma/biotech research teams, academic drug discovery groups.

---

## Compute Pattern

| Stage | Name | Cluster Type | Resources | Est. Walltime |
|-------|------|-------------|-----------|---------------|
| 1 | `PREPROCESSING` | CPU cluster | 16–32 cores | 15–30 min |
| 2 | `STRUCTURE_PREDICTION` | GPU — high-end (H100/A100-80GB) | 8×A100-80GB | 2–6h (1k ligands) |
| 3 | `DOCKING` | GPU — mid-tier or CPU | 8×A10G or 64 CPU cores | 1–3h |
| 4 | `RANKING_AND_REPORT` | CPU cluster | 8–16 cores | 15 min |

**Key transition:** Stage 2 → Stage 3 releases the A100-80GB nodes and picks up cheaper compute. Without Horus, users hold the expensive nodes for the full run.

---

## Tools & Dependencies

| Tool | Role | Source |
|------|------|--------|
| [Boltz-2](https://github.com/jwohlwend/boltz) | Joint structure + binding affinity prediction | MIT License — MIT/Recursion |
| [DiffDock](https://github.com/gcorso/DiffDock) | Diffusion-based docking for pose refinement | MIT License |
| [AutoDock-GPU](https://github.com/ccsb-scripps/AutoDock-GPU) | Traditional GPU-accelerated docking (fallback) | LGPL |
| [RDKit](https://www.rdkit.org/) | Ligand featurization, SMILES parsing | BSD License |
| [OpenBabel](https://openbabel.org/) | File format conversion (SDF, MOL2, PDBQT) | GPL |
| [pandas / numpy](https://pandas.pydata.org/) | Score aggregation and ranking | BSD |

**Container images to build:**
- `boltz2:latest` — Python env with Boltz-2 + CUDA 12 + torch 2.x
- `diffdock:latest` — DiffDock environment
- `autodock-gpu:latest` — AutoDock-GPU binary + OpenBabel

---

## Input / Output

**Inputs:**
- `target.fasta` — protein target sequence (or `target.pdb` for known structure)
- `ligands.smi` or `ligands.sdf` — ligand library (100 to 100k+ molecules)
- `config.yaml` — workflow parameters (see Parameterization)

**Outputs:**
- `results/top_hits.csv` — ranked ligands with predicted ΔG, pLDDT, and interface score
- `results/poses/` — SDF files of top-N predicted binding poses
- `results/report.html` — visual summary with 3D structure viewers (Mol* or py3Dmol)

---

## Horus Configuration

```
Cluster A (stage 2):  GPU cluster — A100-80GB or H100-80GB
                      min_gpus: 4, max_gpus: 32
                      requires: CUDA >= 12.0, VRAM >= 40GB per GPU

Cluster B (stage 3):  GPU cluster — mid-tier (A10G, L40S) or CPU
                      fallback: CPU cluster with 64+ cores

Cluster C (stages 1,4): CPU cluster — any
                         cores: 16–32
```

**Data flow:**
- Stage 1 → Stage 2: featurized numpy arrays or HDF5 file (~MB range)
- Stage 2 → Stage 3: top-N predicted poses as SDF/PDB (~10–100MB depending on cutoff)
- Stage 3 → Stage 4: scored poses as CSV + SDF

**Scheduler notes:**
- Stage 2 runs as a job array: one GPU per batch of N ligands. Horus should fan out across available GPUs in Cluster A.
- Stage 3 can also be a job array (one job per docking target).
- No MPI required. All stages are embarrassingly parallel.

---

## Parameterization

| Parameter | Description | Default |
|-----------|-------------|---------|
| `library_size` | Number of ligands in the input library | — (required) |
| `top_k_for_docking` | How many Boltz-2 hits to pass to docking stage | `100` |
| `boltz2_batch_size` | Ligands per GPU instance | `50` |
| `docking_engine` | `diffdock` or `autodock-gpu` | `diffdock` |
| `output_top_n_poses` | Poses per ligand to include in final output | `3` |
| `affinity_cutoff_kcal` | Minimum predicted ΔG to include in report | `-7.0` |

---

## Implementation Notes

- Boltz-2 requires 40GB VRAM for standard protein-ligand complexes. Use A100-80GB or H100 for large targets (>500 residues). Do not attempt to run on A10G (24GB) for large proteins without sequence truncation.
- DiffDock inference is stochastic — run with multiple seeds and take the best-scoring pose.
- For libraries >10k ligands, consider pre-filtering with a fast 2D similarity screen (RDKit fingerprints vs. known actives) before running Boltz-2 to reduce stage-2 cost.
- Boltz-2 outputs binding affinity as a scalar score, not a calibrated ΔG. The ranking is reliable; the absolute value is not. Make this clear in the report.
- AutoDock-GPU is a faster fallback for stage 3 if DiffDock is too slow for the library size; it requires PDBQT format conversion via OpenBabel in stage 1.

---

## Open Questions

- [ ] What is the Horus artifact schema for passing SDF files between stages? Does it support streaming or require full stage completion first?
- [ ] Should stage 2 fan-out be controlled by `library_size / boltz2_batch_size` automatically, or does the user specify the number of array jobs?
- [ ] Is there a preferred 3D viewer for the HTML report (Mol*, NGL, py3Dmol)?
- [ ] Do we want to support AlphaFold2 structure prediction as an optional pre-stage for targets where no PDB is available?

---

## References

- [Boltz-2 paper (MIT/Recursion)](https://www.biorxiv.org/content/10.1101/2024.05.24.595648)
- [DiffDock paper](https://arxiv.org/abs/2210.01776)
- [GPU Cloud for AI Drug Discovery (Spheron, 2026)](https://www.spheron.network/blog/gpu-cloud-ai-drug-discovery/)
- [Boltz-2 GitHub](https://github.com/jwohlwend/boltz)
- [DiffDock GitHub](https://github.com/gcorso/DiffDock)
