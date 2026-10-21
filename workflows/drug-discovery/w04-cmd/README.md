# W-35 · cMD Replicas (AMBER)

From a PDB ID or an uploaded structure to a solvated protein–ligand system, N parallel AMBER MD replicas, per-replica analysis and a clustered HTML report.

![Domain: Drug Discovery](https://img.shields.io/badge/domain-drug--discovery-blue)

## Overview

Conventional MD with AMBER, from a PDB ID or uploaded structure to a solvated protein-ligand system (optional GAFF2 ligand), N parallel replicas of a 10-step equilibration plus chunked production, per-replica analysis and one clustered HTML report. The protocol is ported from [MolBioMedUAB/protocols](https://github.com/MolBioMedUAB/protocols). The workflow has 10 tasks.

## Pipeline

```
fetch_pdb            PDB ID or upload             --> structure/structure.pdb
extract_ligand       structure + residue name     --> ligand/ligand_pose.pdb
parameterize_ligand  pose                         --> ligand/ligand.mol2 + ligand/ligand.frcmod (GAFF2, AM1-BCC)
build_complex        structure + ligand           --> system/system.{prmtop,inpcrd,pdb}, system/prep_report.json
build_system         protein-only variant         (output not used downstream)
prepare_replicas     renders min/md templates     --> replicas/<i>/
equilibrate (xN) 10 steps: min, heat, restrained NPT, min, NPT, free NPT/NVT
produce     (xN) chunked production (NVT or NPT)
analyze     (xN) cpptraj: RMSD, RMSF, Rg, H-bonds, ligand RMSD/contacts
report               k-means over all replicas    --> results/report.html, results/summary.csv, results/clusters/
```

## Inputs / Outputs

- Inputs: `pdb_id` (default `3HTB`) or `structure_upload` (default `examples/1aki.pdb`, used when `pdb_id` is empty). The default builds T4 lysozyme L99A with 2-propylphenol (3HTB + JZ4). One ligand per `build_complex`.
- `results/report.html`: system and protocol summary, per-replica plots, cluster populations with Mol* views, top H-bonds and ligand contacts. `results/summary.csv`: one row per replica. `results/clusters/`: representative PDBs and per-frame assignment.
- `system/` (prmtop, inpcrd, pdb, `prep_report.json`), `ligand/` (pose, mol2, frcmod) and per replica `equilibrated_out/<i>/`, `produced_out/<i>/`, `analyzed_out/<i>/`.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `ligand_resname` / `ligand_chain` | `JZ4` / first copy | Ligand to extract |
| `ligand_charge` | 0 | Net formal charge (AM1-BCC) |
| `protonate_ligand` | on | Open Babel hydrogens at the pH |
| `chains` | all | Chains to keep, e.g. `A,B`; hetero groups are removed |
| `keep_waters` | off | Keep crystal waters |
| `protonation` / `ph` | PROPKA / 7.0 | Protonation method (`reduce` = HIS tautomers only) and pH |
| `forcefield` / `water` | ff14SB / TIP3P | Force field and water model |
| `box` / `padding` | truncated octahedron / 12 Å | Box shape and padding |
| `salt_mM` | 150 | NaCl on top of neutralization |
| `hmr` | off | Hydrogen mass repartitioning (allows 4 fs) |
| `md_engine` / `amber_env` | OpenMM / none | `openmm` or `pmemd`; shell line run before `pmemd.cuda` |
| `n_replicas` | 3 | Independent replicas (1-20) |
| `temperature` | 300 K | Temperature (250-400) |
| `length_ns` / `chunk_ns` | 200 / 10 | Production per replica, in consecutive chunks |
| `timestep_fs` | 0 (auto) | 4 fs with HMR, else 2 fs |
| `prod_ensemble` | NVT | NVT or NPT |
| `save_every_ps` | 10 | Production frame interval |
| `write_solvent` | on | Off writes solute-only trajectories |
| `equil_scale` / `restraint_scale` | 1.0 / 1.0 | Scale equilibration lengths (15 ns at 1.0) and restraint weights |
| `restraint_mask` | auto | Solute heavy atoms, or any Amber mask |
| `heat_start_k`, `cutoff`, `gamma_ln`, `pressure_bar` | 100 K, 9 Å, 3 ps⁻¹, 1 bar | Thermostat, cutoff and barostat settings |
| `seed` | -1 | -1 random; a number derives a seed per replica and step |
| `analysis_stride` | 1 | Analyze every Nth frame |
| `n_clusters` | 5 | k-means clusters on backbone; 0 skips |

## References

- [AmberTools](https://ambermd.org) · [cpptraj](https://github.com/Amber-MD/cpptraj) · [ParmEd](https://github.com/ParmEd/ParmEd)
- [OpenMM](https://github.com/openmm/openmm)
- [PROPKA](https://github.com/jensengroup/propka)
- [Reduce](https://github.com/rlabduke/reduce)
- [Open Babel](https://github.com/openbabel/openbabel)
- [MolBioMedUAB/protocols](https://github.com/MolBioMedUAB/protocols) -- `MD/cMD/create_md_custom.sh`, the source protocol this workflow ports.
