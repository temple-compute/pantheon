# W-09 · AI-Accelerated Materials Discovery (DFT → MLIP Training → High-Throughput Screening)

![Status: draft](https://img.shields.io/badge/status-draft-lightgrey)
![Domain: Scientific Computing](https://img.shields.io/badge/domain-scientific--computing-teal)
![GTM: Tier 2](https://img.shields.io/badge/GTM-Tier%202-blue)

## Overview

Generates candidate crystal structures, validates them with density functional theory (DFT) calculations to produce energy and force labels, trains a machine learning interatomic potential (MLIP) on those labels, and uses the MLIP for high-throughput property screening at 10,000× DFT speed. The output is a ranked list of materials candidates with predicted properties of interest (stability, band gap, conductivity, etc.).

This workflow directly addresses one of the most painful bottlenecks in computational materials science: DFT is accurate but slow (~hours per structure); empirical force fields are fast but inaccurate; MLIPs bridge the gap. The DFT generation stage (classic HPC, MPI, CPU) and the MLIP training stage (GPU cluster) are natural Horus handoff points.

**Target users:** Computational materials scientists, battery R&D teams, semiconductor companies, catalysis researchers.

---

## Compute Pattern

| Stage | Name | Cluster Type | Resources | Est. Walltime |
|-------|------|-------------|-----------|---------------|
| 1 | `STRUCTURE_GENERATION` | CPU cluster | 32 cores | 1–4h |
| 2 | `DFT_CALCULATION` | HPC CPU cluster (MPI, InfiniBand) | 256–512 cores | 12–48h |
| 3 | `MLIP_TRAINING` | GPU cluster (H100/A100) | 4–16×A100 | 2–12h |
| 4 | `HIGH_THROUGHPUT_SCREENING` | GPU or CPU cluster | 4–64×A100 or 256 CPU | 1–8h |
| 5 | `RANKING_AND_EXPORT` | CPU cluster | 16 cores | 15–30 min |

---

## Tools & Dependencies

| Tool | Role | Source |
|------|------|--------|
| [USPEX](https://uspex-team.org/) | Evolutionary crystal structure prediction | Free for academic |
| [AIRSS](https://airss-docs.github.io/) | Ab initio random structure searching | GPL |
| [MatterGen](https://github.com/microsoft/mattergen) | Generative model for crystal structures | MIT — Microsoft |
| [VASP](https://www.vasp.at/) | DFT calculations (most used in materials) | Commercial license |
| [Quantum ESPRESSO](https://www.quantum-espresso.org/) | Open-source DFT (alternative) | GPL |
| [MACE](https://github.com/ACEsuit/mace) | State-of-the-art MLIP (equivariant GNN) | MIT |
| [CHGNet](https://github.com/CederGroupHub/chgnet) | MLIP with charge equilibration | MIT — Berkeley |
| [SevenNet](https://github.com/MDIL-SNU/SevenNet) | Scalable MLIP for large systems | GPL |
| [ASE](https://wiki.fysik.dtu.dk/ase/) | Atomic simulation environment | LGPL |
| [pymatgen](https://pymatgen.org/) | Materials analysis framework | MIT |
| [Materials Project API](https://next-gen.materialsproject.org/api) | Known structure database | Free (API key) |

---

## Input / Output

**Inputs:**
- `target_composition.txt` — chemical composition or phase space to explore (e.g., `Li-Fe-O`, `GaN`)
- `target_properties.yaml` — desired material properties and thresholds
- `config.yaml` — workflow parameters

**Outputs:**
- `artifacts/mlip_model/` — trained MLIP weights (MACE/CHGNet format)
- `results/screening_results.csv` — all screened structures with predicted properties
- `results/top_candidates.cif` — CIF structure files for top-ranked candidates
- `results/report.html` — property distribution plots, structure visualizations

---

## Horus Configuration

```
Cluster A (stage 2):   HPC CPU cluster — MPI, InfiniBand
                        cores: 256–512
                        requires: InfiniBand, parallel filesystem (Lustre)
                        Note: VASP requires a commercial license; cluster must have
                              VASP installed and licensed. QE is open-source alternative.
                        Note: one MPI job per structure; fan out as job array

Cluster B (stages 3,4): GPU cluster — A100 or H100
                          gpus: 4–16×A100 for training
                          gpus: 4–64×A100 for screening (auto-scale)

Cluster C (stages 1,5): CPU cluster — any
                          cores: 16–32
```

**Data flow:**
- Stage 1 → Stage 2: POSCAR/CIF structure files (~KB each; thousands of structures)
- Stage 2 → Stage 3: energy/force/stress labels as extXYZ or ASE database (~GB)
- Stage 3 → Stage 4: MLIP model file (~MB to GB depending on architecture)
- Stage 4 → Stage 5: property predictions as CSV

---

## Parameterization

| Parameter | Description | Default |
|-----------|-------------|---------|
| `composition` | Chemical composition space to explore | — (required) |
| `n_structures_to_generate` | Candidate structures to generate in stage 1 | `1000` |
| `structure_generator` | `airss`, `uspex`, or `mattergen` | `airss` |
| `dft_code` | `vasp` or `qe` (Quantum ESPRESSO) | `vasp` |
| `dft_functional` | DFT exchange-correlation functional | `PBE` |
| `dft_kpoints` | K-point mesh density | `0.03` (Å⁻¹) |
| `mlip_architecture` | `mace`, `chgnet`, or `sevennet` | `mace` |
| `mlip_training_cutoff_angstrom` | Interaction cutoff radius | `6.0` |
| `screening_library` | Structure database to screen | `materials_project` |
| `target_property` | Property to optimize | — (required) |

---

## Implementation Notes

- VASP requires a paid license. For open-source deployments, use Quantum ESPRESSO. VASP is faster and more commonly used in industrial settings; QE is preferred for academic/open deployments.
- DFT calculation is one MPI job per structure. Fan out as a Slurm/Horus job array. Each calculation takes 30 min–4h depending on system size and k-points.
- MACE is currently the most accurate and widely adopted MLIP architecture (2024–2026). MACE-MP-0 pretrained weights are available as a starting point for fine-tuning.
- Active learning (iterative DFT → MLIP → identify uncertain structures → run more DFT) can dramatically reduce the number of DFT calculations needed. Consider adding this as an optional workflow loop.
- High-throughput screening (stage 4) with an MLIP is 10,000–100,000× faster than DFT. A single A100 can screen millions of structures per day.
- pymatgen provides structure matching, prototype identification, and Materials Project database access — essential for filtering already-known structures from screening results.

---

## Open Questions

- [ ] Should the workflow support active learning (iterative DFT → MLIP loop)? This would require Horus to handle cycles in the workflow DAG.
- [ ] How should VASP license management be handled in Horus? Does it support license-gated software?
- [ ] Is MatterGen (Microsoft, MIT license) mature enough to use as the default structure generator? It produces structures directly from property conditions but is newer.
- [ ] Should the workflow output structures in CIF, POSCAR, or both?

---

## References

- [MACE GitHub (Cambridge)](https://github.com/ACEsuit/mace)
- [MACE-MP: Universal MLIP (2023)](https://arxiv.org/abs/2401.00096)
- [MatterGen GitHub (Microsoft)](https://github.com/microsoft/mattergen)
- [CHGNet GitHub (Berkeley)](https://github.com/CederGroupHub/chgnet)
- [pymatgen documentation](https://pymatgen.org/)
- [Materials Project](https://next-gen.materialsproject.org/)
- [ASE documentation](https://wiki.fysik.dtu.dk/ase/)
