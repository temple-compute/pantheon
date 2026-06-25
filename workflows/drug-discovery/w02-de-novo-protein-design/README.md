# W-02 · De Novo Protein Binder Design (RFdiffusion → ProteinMPNN → Boltz-2 Validation)

![Status: draft](https://img.shields.io/badge/status-draft-lightgrey)
![Domain: Drug Discovery](https://img.shields.io/badge/domain-drug--discovery-blue)
![GTM: Tier 1](https://img.shields.io/badge/GTM-Tier%201-green)

## Overview

Given a protein target, this workflow designs novel protein binders from scratch using a three-step generative pipeline: backbone scaffold generation (RFdiffusion), sequence design (ProteinMPNN), and structural validation (Boltz-2 or AlphaFold2 Initial Guess). The output is a ranked shortlist of designed binders with predicted structure quality metrics, ready for wet-lab synthesis.

This workflow reflects the current state of the art for de novo binder design as of 2025–2026. Success rates are low (typically 1–5% of designs pass in silico filters), which means scale is essential — thousands of designs must be generated to get a usable hit list. This makes it a natural HPC workflow: the generation and validation stages are highly parallel but compute-intensive, and they require different hardware profiles.

**Reference implementation:** [ProteinDJ](https://github.com/ProteinDJ/ProteinDJ) — Nextflow + Slurm pipeline published Dec 2025.

**Target users:** Protein engineers, structural biologists, biotech R&D teams.

---

## Compute Pattern

| Stage | Name | Cluster Type | Resources | Est. Walltime |
|-------|------|-------------|-----------|---------------|
| 1 | `SCAFFOLD_GENERATION` | GPU — high-end (H100) | 32–64×H100 | 4–12h (5k designs) |
| 2 | `SEQUENCE_DESIGN` | GPU — mid-tier or H100 | 8–16×A100 | 1–3h |
| 3 | `STRUCTURE_VALIDATION` | GPU — high-end (A100) | 16–32×A100 | 3–8h |
| 4 | `HIT_RANKING` | CPU cluster | 16 cores | 15–30 min |

**Key pattern:** Stage 1 is the heaviest compute — hundreds of GPU-hours for serious campaigns. Stages 2 and 3 can run on the same cluster as stage 1 or be handed off to a more cost-efficient tier. Stage 4 is pure CPU.

---

## Tools & Dependencies

| Tool | Role | Source |
|------|------|--------|
| [RFdiffusion](https://github.com/RosettaCommons/RFdiffusion) | Backbone scaffold generation via diffusion | MIT — Baker Lab, UW |
| [ProteinMPNN](https://github.com/dauparas/ProteinMPNN) | Sequence design for generated backbones | MIT — Baker Lab, UW |
| [Boltz-2](https://github.com/jwohlwend/boltz) | Structure prediction + validation | MIT — MIT/Recursion |
| [AlphaFold2-Initial-Guess](https://github.com/sokrypton/ColabFold) | AF2-based structure validation (alternative) | Apache 2.0 |
| [pyRosetta](https://www.pyrosetta.org/) | Optional: additional scoring (score function filters) | Academic license |
| [BioPython](https://biopython.org/) | Structure parsing, FASTA handling | BSD |
| [pandas / scipy](https://pandas.pydata.org/) | Diversity clustering, hit ranking | BSD |

---

## Input / Output

**Inputs:**
- `target.pdb` — 3D structure of the target protein (required for RFdiffusion)
- `hotspot_residues.txt` — target binding site residue IDs (optional but recommended)
- `config.yaml` — workflow parameters

**Outputs:**
- `results/top_hits/` — PDB files of top-ranked designed binders
- `results/ranking.csv` — all designs with pLDDT, interface pAE, interface score, sequence
- `results/report.html` — visual summary with structure overlays

---

## Horus Configuration

```
Cluster A (stages 1–3):  GPU cluster — H100 or A100-80GB
                          min_gpus: 8, max_gpus: 64
                          requires: CUDA >= 12.0

Cluster B (stage 4):     CPU cluster — any
                          cores: 16
```

**Data flow:**
- Stage 1 → Stage 2: PDB files of backbone scaffolds (potentially thousands; ~GB total)
- Stage 2 → Stage 3: FASTA sequences paired with backbone PDBs
- Stage 3 → Stage 4: validation scores CSV + top-N PDB files

**Scheduler notes:**
- All GPU stages are embarrassingly parallel — implement as job arrays, one job per design batch.
- ProteinDJ's reference implementation uses Nextflow with Slurm for synchronization across GPU↔CPU stage transitions. Horus should replicate this barrier behavior.
- Stage 1 fan-out: `n_designs / designs_per_gpu_job` array tasks. Typical: 100 designs/job.
- Stages 1, 2, 3 can run on the same cluster with no teardown between them if cost allows.

---

## Parameterization

| Parameter | Description | Default |
|-----------|-------------|---------|
| `n_designs` | Total backbone scaffolds to generate | `5000` |
| `designs_per_job` | RFdiffusion designs per GPU job | `100` |
| `mpnn_sequences_per_backbone` | ProteinMPNN sequences to generate per backbone | `8` |
| `validation_model` | `boltz2` or `af2-initial-guess` | `boltz2` |
| `plddt_threshold` | Minimum per-residue pLDDT to pass validation | `0.85` |
| `interface_pae_threshold` | Maximum interface pAE (Ų) to pass validation | `10.0` |
| `output_top_n` | Number of hits to include in final report | `50` |

---

## Implementation Notes

- RFdiffusion requires a target PDB. If only a sequence is available, run AlphaFold2 or Boltz-2 structure prediction first (see W-01 as a reference for AF2 invocation patterns).
- ProteinMPNN is very fast relative to the other stages. It can run on the same GPU nodes after stage 1 completes or on cheaper mid-tier nodes.
- Boltz-2 is preferred over AF2-Initial-Guess for validation when binding affinity scores are needed in addition to structural quality. AF2-Initial-Guess is faster if only pLDDT/pAE is required.
- In silico success rates are typically 1–5%. Budget for at least 2000–5000 initial designs to get a useful hit list of 20–50 candidates.
- Diversity filtering before ranking (e.g., sequence identity clustering at 80%) avoids returning clusters of nearly-identical designs.
- ProteinDJ (Dec 2025) is the most production-ready open-source reference for this pipeline on HPC.

---

## Open Questions

- [ ] What PDB preprocessing is needed (chain selection, hydrogens, missing residues)? Should Horus handle this in stage 1 or require a clean input?
- [ ] How should hotspot residues be specified — Rosetta-style chain+resnum or a separate file?
- [ ] Should the workflow support BindCraft as an alternative to RFdiffusion for stage 1?
- [ ] Is there a standard Horus pattern for fan-out job arrays with dynamic sizing (depends on `n_designs` parameter)?

---

## References

- [RFdiffusion paper (Watson et al., Science 2023)](https://www.science.org/doi/10.1126/science.adl2528)
- [ProteinMPNN paper (Dauparas et al., Science 2022)](https://www.science.org/doi/10.1126/science.add2187)
- [ProteinDJ preprint (Dec 2025)](https://www.biorxiv.org/content/10.1101/2025.09.24.678028v2.full)
- [Boltz-2 GitHub](https://github.com/jwohlwend/boltz)
- [RFdiffusion GitHub](https://github.com/RosettaCommons/RFdiffusion)
- [ProteinMPNN GitHub](https://github.com/dauparas/ProteinMPNN)
