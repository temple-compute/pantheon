# W-35 · cMD Replicas (AMBER)

![Domain: Drug Discovery](https://img.shields.io/badge/domain-drug--discovery-blue)

## Overview

End-to-end conventional molecular dynamics (cMD) with AMBER: from a PDB ID
to a protonated, solvated system with an optional GAFF2 ligand, N parallel replicas of a 10-step equilibration and chunked
production on GPUs, per-replica trajectory analysis, and one HTML report with
clustering. The MD protocol is ported from
[MolBioMedUAB/protocols](https://github.com/MolBioMedUAB/protocols)'
`MD/cMD/create_md_custom.sh`; preparation, analysis and the parameters around
it are added here.

Preparation and analysis run on the cluster in one conda-forge environment
(AmberTools 26: pdb4amber, tleap, antechamber, parmchk2, parmed, cpptraj;
PROPKA; Open Babel), built on first use and reused. Only `pmemd.cuda` comes
from the cluster's AMBER module (`amber_env`). Replicas fan out with
Horus's `horus_map`, one SLURM job per replica per phase.

## Pipeline

```
fetch_pdb (local)            PDB ID --> structure.pdb
  |-- extract_ligand (local)      structure + residue name --> ligand pose .pdb
  |     parameterize_ligand (CPU) pose --> ligand.mol2 + ligand.frcmod (GAFF2, AM1-BCC)
  |-- build_complex (CPU)    structure + ligand --> system.prmtop/.inpcrd/.pdb, prep_report.json
  '-- build_system (CPU)     protein-only alternative (outputs unused in the default graph)
prepare_replicas (local)     renders min/md templates from the MD settings --> replicas/<i>/
horus_map equilibrate (N x GPU)  10 steps: min, heat, restrained NPT, min, NPT, free NPT/NVT
horus_map produce     (N x GPU)  chunked production (NVT or NPT)
horus_map analyze     (N x CPU)  cpptraj: RMSD, RMSF, Rg, H-bonds, ligand RMSD/contacts
report                (CPU)      k-means over all replicas --> report.html, summary.csv, clusters/
```

### Swapping blocks

Blocks exchange plain files, so any block can be replaced by connecting
your own file to the next block's input:

| You have | Delete | Connect to |
|---|---|---|
| your own PDB | `fetch_pdb` | `structure_in` of the build block (and `extract_ligand`) |
| a docked/prepared ligand pose (.pdb/.sdf/.mol2) | `extract_ligand` | `ligand_in` of `parameterize_ligand` |
| ligand.mol2 + ligand.frcmod you parameterized | `extract_ligand`, `parameterize_ligand` | `ligand_mol2_in` / `ligand_frcmod_in` of `build_complex` |
| a protein-only system | the ligand blocks and `build_complex` | `build_system`'s `protein_prmtop`/`protein_inpcrd` to `prepare_replicas` |
| a ready prmtop/inpcrd | everything before `prepare_replicas` | `system_prmtop_in` / `system_inpcrd_in` of `prepare_replicas` |

`examples/` has a protein PDB (`1aki.pdb`) and a ready 1AKI system
(`system.prmtop`/`.inpcrd`) to try the last rows. The report needs nothing
from the build blocks: `analyze` reads the system composition from the
topology.

## Prerequisites

- A SLURM cluster with an AMBER module providing `pmemd.cuda` (pick or add
  its line in `amber_env`) and conda on the nodes. Set the three target
  anchors at the top of `workflow.yaml` (partition/account) and the `_tools`
  executor's `conda` and `environment_dir` (an absolute path, so the
  environment is built once and shared by every task and run; the first
  build takes a few minutes). The defaults are picard's: Miniconda is on the
  gorn1 nodes' `/shared`, so run the CPU blocks there too.
- `prepare_replicas` runs on the orchestrator and needs only `python3`.

## Quick start

```bash
uv sync          # horus-runtime + horus-slurm + horus-environments
uv run horus run workflow.yaml
```

or import the folder into tc-os and set the inputs in the UI. Uses the
`shell` executor throughout.

## Inputs

**Structure, ligand and system build**

| Input | Default | Used by | Meaning |
|---|---|---|---|
| `pdb_id` | `3HTB` | fetch_pdb | RCSB ID; needs a PDB-format file |
| `ligand_resname` / `ligand_chain` | `JZ4` / first copy | extract_ligand, parameterize_ligand | ligand to extract; name it keeps in the system |
| `ligand_charge` | 0 | parameterize_ligand | net formal charge (AM1-BCC) |
| `protonate_ligand` | on | parameterize_ligand | Open Babel hydrogens at the pH; off keeps the file's hydrogens |
| `chains` | all | build | e.g. `A,B`; every hetero group is removed (MSE becomes MET) |
| `keep_waters` | off | build | keep crystal waters |
| `protonation` / `ph` | PROPKA / 7.0 | build | PROPKA sets HIS (HIE/HIP), ASP (ASH), GLU (GLH), LYS (LYN); `reduce` = HIS tautomers only |
| `forcefield` / `water` | ff14SB / TIP3P | build | ff19SB should go with OPC |
| `box` / `padding` | truncated octahedron / 12 Å | build | |
| `salt_mM` | 150 | build | NaCl by SLTCAP on top of neutralization |
| `hmr` | off | build | hydrogen mass repartitioning (allows 4 fs) |
| `amber_env` | Picard | equilibrate, produce | module line that provides `pmemd.cuda` |

**MD protocol**

| Input | Default | Meaning |
|---|---|---|
| `n_replicas` | 3 | independent replicas |
| `temperature` | 300 K | |
| `length_ns` / `chunk_ns` | 200 / 10 | production per replica, as consecutive chunks |
| `timestep_fs` | 0 = auto | 4 fs with HMR, else 2 fs; >2 fs without HMR is refused |
| `prod_ensemble` | NVT | NVT or NPT (Monte Carlo barostat) |
| `save_every_ps` | 10 | production frame interval |
| `write_solvent` | on | off writes solute-only trajectories (`ntwprt`, ~10x smaller) |
| `equil_scale` | 1.0 | scales all equilibration lengths (15 ns at 1.0); 0.1 for tests |
| `restraint_scale` | 1.0 | scales the 250/100/100/10 (solute) and 10/10/1/0.1 (backbone) schedule |
| `restraint_mask` | auto | solute heavy atoms, or any Amber mask |
| `heat_start_k`, `cutoff`, `gamma_ln`, `pressure_bar` | 100 K, 9 Å, 3 ps⁻¹, 1 bar | |
| `seed` | -1 | -1 random; a number gives each replica/step its own derived `ig` |

**Analysis:** `analysis_stride` (every Nth frame, default 1), `n_clusters`
(k-means on backbone, default 5, 0 skips).

The equilibration schedule (step lengths, restraint weights, which steps
draw new velocities) is the `PROTOCOL` table in `scripts/prepare_replicas.py`;
the namelists are `templates/min.in` and `templates/md.in` (archived as
`templates.tar.gz`; rebuild with `tar -czf templates.tar.gz -C templates .`).

The default inputs build T4 lysozyme L99A with 2-propylphenol (3HTB + JZ4).
One ligand per `build_complex`; for a protein-only system see
[Swapping blocks](#swapping-blocks).

## Outputs

- `results/report.html`: system and protocol summary, per-replica plots
  (backbone RMSD vs first frame and vs the built structure, CA RMSF, Rg,
  H-bond count, ligand RMSD and contacts, potential energy, temperature,
  density for NPT), cluster populations per replica with Mol* views of the
  representatives, top H-bonds and ligand contacts, the system composition
  and every MD setting.
- `results/summary.csv`: one row per replica (chunks, ns, frames, mean RMSD,
  Rg, H-bonds, ligand RMSD).
- `results/clusters/`: representative PDBs and the per-frame assignment.
- `system/`: `system.prmtop`, `system.inpcrd`, `system.pdb`,
  `prep_report.json` (removed hetero groups, protonation changes,
  disulfides, ligand charge, ions, box, warnings).
- `ligand/`: extracted pose, `ligand.mol2`, `ligand.frcmod`.
- Per replica: `equilibrated_out/<i>/`, `produced_out/<i>/` (chunks) and
  `analyzed_out/<i>/` (cpptraj `.dat` files, dry trajectory).

## Design notes

- **Two map stages for MD:** a `horus_map` clone runs one flat command on
  one item, so equilibration and production are separate stages (and SLURM
  jobs with their own walltime). Each stage copies the slot forward, so
  every item is self-contained; value inputs reach the clones only through
  the slot's rendered mdin files and `protocol.json`.
- **Resume:** `equilibrate.sh` and `production.sh` skip steps and chunks
  whose restart exists and whose mdout has pmemd's closing TIMINGS section, so a
  requeued job in the same directory continues instead of starting over.
- **Analysis next to the data:** `analyze` runs on the cluster so the
  production trajectories never need to move; only the small results and
  a dry strided trajectory go to `report`.

## Live monitoring (while a replica runs)

Declared outputs (`equilibrated`, `produced`) only upload when a task
succeeds, so a long or failing run would otherwise show nothing. To cover
that, `scripts/live_monitor.sh` (copied into every slot) runs beside pmemd
in both `equilibrate` and `produce` and writes a small digest to
`$HORUS_SIDE_ARTIFACTS_DIR`. Horus pulls that directory every ~30 s while the
task runs, and once more when it fails or is cancelled. The digest appears
in each replica's **side products** in the UI:

| File | What | Viewer |
|---|---|---|
| `current_mdout.log` | newest mdout (AMBER errors end up here) | text |
| `current_mdinfo.txt` | newest mdinfo (ns/day, ETA, current energies) | text |
| `energies.csv` / `energies.svg` | every MD energy record so far; EPtot/Temp/Density plot with step boundaries | table / image |
| `trajectory.pdb` | newest `.nc`, solvent and H stripped, at most `LIVE_FRAMES` models | Mol* (plays as a trajectory) |
| `rmsd.csv` | CA RMSD of those frames against the first one | table |

- **Settings:** `LIVE_INTERVAL` (default 60 s) and `LIVE_FRAMES` (default 50).
  Export them in the task environment.
- **Outside Horus:** the monitor is a no-op (`HORUS_SIDE_ARTIFACTS_DIR` unset).
- **If it goes bad:** cancel the run from the UI. That `scancel`s the SLURM
  jobs, and the final digest is still uploaded.
- **Self-check:** `bash scripts/live_monitor.sh --selftest` checks the mdout
  parser and the plot. Trajectory frames need `cpptraj`, which AmberTools
  provides once the AMBER module is loaded (live monitor) and the tools
  environment provides (analysis).

## Verification

- Self-checks (no AMBER needed): `--self-test` on `scripts/fetch_pdb.py`,
  `extract_ligand.py`, `parameterize_ligand.py`, `build_system.py`,
  `scripts/prepare_replicas.py --self-test` (rendered nstlim/dt/cut/restraints
  per step, HMR at 4 fs, NPT production, seeds), `scripts/analyze.py --self-test`,
  `scripts/report.py --self-test`, `bash scripts/live_monitor.sh --selftest`.
- `env/amber-stub.sh` is a drop-in for the AMBER module that writes fake
  pmemd outputs (including the completion line the resume check reads), to
  exercise `equilibrate.sh`/`production.sh` without a GPU.
- Real tests with conda-forge AmberTools: fetch 3HTB -> extract JZ4 ->
  parameterize -> build_complex and build_system; then (`sander` standing
  in for pmemd) 2 replicas with `equil_scale` and `chunk_ns` cut to
  picoseconds through `analyze.py` and `report.py`.

## References

- [MolBioMedUAB/protocols](https://github.com/MolBioMedUAB/protocols) --
  `MD/cMD/create_md_custom.sh`, the source protocol this workflow ports.
