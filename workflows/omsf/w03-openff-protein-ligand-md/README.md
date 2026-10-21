# W-39 · OpenFF Protein-Ligand MD

Solvate a protein-ligand complex, parameterize it with OpenFF Sage + ff14SB, run independent OpenMM replicas in parallel and report protein and ligand RMSD.

![Domain: OMSF](https://img.shields.io/badge/domain-omsf-blue)

## Overview

Solvates the HIF-2α PAS-B domain (PDB 5TBM) with the inhibitor PT2385, parameterizes the protein with ff14SB and the ligand, water and ions with OpenFF Sage 2.3.0 (through Interchange), runs independent OpenMM replicas and reports protein and ligand RMSD. It is a port of the Open Force Field Toolkit Showcase (openff-toolkit 0.19.0). The workflow has 4 tasks.

## Pipeline

```
build_system  PDBFixer + OpenFF Topology        --> system/topology.json
parameterize  Interchange                       --> replicas/<i>/{system.xml,complex.pdb,seed}
simulate      horus_map, 1 clone per replica    --> trajectories/<i>/ (OpenMM minimize + Langevin MD)
analyze       mdtraj RMSD                       --> results/{rmsd.csv,report.html,final_frame.pdb}
```

## Inputs / Outputs

- `receptor`: prepared PDB (protonated, capped, no missing atoms, no ligand). Default `examples/5tbm_prepared.pdb`.
- `ligand`: SDF with explicit hydrogens, posed in the pocket; the residue is named `UNK`. Default `examples/PT2385.sdf`.
- `results/rmsd.csv`: `replica, frame, time_ps, protein_ca_rmsd_A, ligand_rmsd_A`. Ligand RMSD is measured after aligning on protein Cα atoms.
- `results/report.html`: per-replica summary and a Mol* view of the final frame, titled with `system_label`. `results/final_frame.pdb`: last frame of replica 0.
- `trajectories/<i>/`: `trajectory.dcd`, `log.csv`, `complex.pdb`, `seed`.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `receptor` / `ligand` | 5TBM / PT2385 examples | Inputs above |
| `system_label` | `PT2385 / HIF-2α (5TBM)` | System name in the report title |
| `n_replicas` | 3 | Independent replicas (1-100) |
| `n_steps` | 500000 | MD steps per replica (1 ns at 2 fs; 1000-50,000,000) |
| `padding_nm` | 1.0 | Solvent padding around the protein (0.5-5) |
| `ionic_strength_molar` | 0.15 | NaCl ionic strength (0-2) |
| `temperature_k` | 300 | Thermostat temperature (250-400) |
| `timestep_fs` | 2 | Integrator timestep, H bonds constrained (0.5-4) |
| `report_interval_steps` | 5000 | Steps between DCD frames and `log.csv` rows; must not exceed `n_steps` (100-1,000,000) |

Seeds are `2026 + replica index`.

## References

- [OpenFF Toolkit](https://github.com/openforcefield/openff-toolkit)
- [OpenFF Interchange](https://github.com/openforcefield/openff-interchange)
- [OpenMM](https://github.com/openmm/openmm)
- [PDBFixer](https://github.com/openmm/pdbfixer)
- [MDTraj](https://github.com/mdtraj/mdtraj)
- Upstream notebook: [openff-toolkit 0.19.0 toolkit_showcase](https://github.com/openforcefield/openff-toolkit/tree/0.19.0/examples/toolkit_showcase) (MIT, © Open Force Field Initiative)
- [OMSF workflow directory](https://directory.omsf.io/workflows/)
- [OpenFF Toolkit docs](https://docs.openforcefield.org/projects/toolkit/) · [Interchange](https://docs.openforcefield.org/projects/interchange/) · [OpenMM](https://openmm.org)
