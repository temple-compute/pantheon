# W-37 · OpenFE Relative Binding Free Energies (TYK2)

Relative binding free energies for a congeneric ligand series with OpenFE: upload the ligands and a prepared protein, get ddG per edge and dG per ligand.

![Domain: OMSF](https://img.shields.io/badge/domain-omsf-blue)

## Overview

Relative binding free energies (RBFE) for a congeneric TYK2 inhibitor series with [OpenFE](https://openfree.energy) 1.13.0, ported from the OpenFE `rbfe_tutorial` and `cli_charge_molecules` tutorials in the OMSF workflow directory. The `quickrun` task is a `horus_map` with one clone per transformation JSON (complex or solvent leg of each edge). With the 10 default ligands that is 9 edges and 18 legs. The workflow has 5 tasks.

## Pipeline

```
charge_ligands  openfe charge-molecules (AM1-BCC)          --> results/charged_ligands.sdf
plan_network    Kartograf + minimal spanning network       --> results/transformations/<leg>.json, results/ligand_network.graphml
quickrun        openfe quickrun per leg                    --> results/legs/<slot>/result.json
gather          openfe gather                              --> results/ddg.tsv, results/raw.tsv, results/dg.tsv
report          tables + Mol* view                         --> results/report.html
```

## Inputs / Outputs

- `ligands`: SDF with 3D poses in the binding site; every record is charged and planned (default `examples/tyk2_ligands.sdf`).
- `protein`: prepared PDB (default `examples/tyk2_protein.pdb`).
- `results/ddg.tsv`: ddG per edge with uncertainty. `results/raw.tsv`: dG per leg and repeat. `results/dg.tsv`: MLE dG per ligand.
- `results/report.html`: both tables, network edges and a Mol* view of the protein with the ligands, titled with `target_name`.
- `results/ligand_network.graphml`, `results/charged_ligands.sdf`, `results/transformations/`, `results/legs/<slot>/` (`result.json`, `quickrun.log`).
- `results/dg.tsv` needs at least 3 edges and 2 repeats per edge; otherwise it holds a one-line note and the report shows ddG and raw values.

## Parameters

Defaults are the openfe 1.13.0 `RelativeHybridTopologyProtocol` defaults.

| id | Default | Meaning |
|---|---|---|
| `ligands` / `protein` | TYK2 examples | Inputs above |
| `target_name` | `TYK2` | Protein label in the report title and Mol* view |
| `n_repeats` | 3 | Repeats per leg (1-10); `dg` needs >= 2 |
| `lambda_windows` | 11 | Lambda windows per leg (2-32); `n_replicas` is set equal |
| `equilibration_ns` | 1.0 | Equilibration per replica (0.1-20) |
| `production_ns` | 5.0 | Production per replica (0.5-50) |
| `time_per_iteration_ps` | 2.5 | MD time between replica-exchange attempts (0.5-10); must divide the lengths and intervals |
| `minimization_steps` | 5000 | Minimization steps before equilibration (0-100000) |
| `real_time_analysis_ps` | 250 | Online free energy analysis interval (0-5000); 0 turns it off |
| `checkpoint_interval_ns` | 1.0 | Checkpoint interval, the `--resume` restart point (0.25-10) |
| `compute_platform` | `cuda` | OpenMM platform: `cuda`, `opencl` or `cpu` |

## References

- [OpenFE](https://github.com/OpenFreeEnergy/openfe)
- [OpenMM](https://github.com/openmm/openmm)
- [OpenFE docs](https://docs.openfree.energy)
- [OpenFE ExampleNotebooks (upstream tutorials, MIT)](https://github.com/OpenFreeEnergy/ExampleNotebooks)
- [OMSF workflow directory](https://directory.omsf.io/workflows/)
- Workflow glue is MIT; the TYK2 inputs and tutorials are from OpenFreeEnergy/ExampleNotebooks (MIT) and openfe is MIT. Credit to the Open Free Energy team.
