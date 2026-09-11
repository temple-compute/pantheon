# W-33 · Lacuna Cryptic Pocket Discovery

![Domain: Drug Discovery](https://img.shields.io/badge/domain-drug--discovery-blue)

## Overview

Finds cryptic binding pockets: sites that look closed or shallow in an unbound
structure and only open when something binds. It wraps
[Lacuna](https://github.com/mooreneural/lacuna) (`lacuna-pockets` on PyPI), which
generates a conformational ensemble from the input structure, detects pockets in
every conformer, clusters them across the ensemble so a site that appears in only
a few frames still gets reported, and ranks the survivors with a fitted model that
also scores how much each site opens relative to the input (its crypticity).

This is the cryptic-site-aware counterpart to [W-31 Cavity
Analysis](../../bioexcel_building_blocks/w23-cavity-analysis/README.md), which
ranks fpocket cavities across a pre-built ensemble. fpocket only proposes a pocket
where the surface is *already* concave, which is exactly the assumption a cryptic
site violates. Lacuna 1.1.0 adds a second, learned surface detector alongside the
original geometric one; pooling both (`--detector surface-fusion`) takes held-out
CryptoBench coverage from 68.5% to 86.4% and top-five recovery from 57.1% to 73.9%
over the geometric detector alone.

The bundled example is PDB [4LDJ](https://www.rcsb.org/structure/4LDJ): a
GDP-bound, apo KRAS(G12C) structure with no switch-II inhibitor present. That
pocket is absent from apo KRAS structures and only forms on covalent inhibitor
binding, and KRAS appears nowhere in the benchmark Lacuna's ranker and surface
model were fitted on. Run against this structure Lacuna still surfaces it twice in
the top ten: once as the compact switch-II groove (His95/Tyr96 plus the P-loop
position that carries the G12C cysteine, 4.2 Å from where sotorasib sits) and once
as the wider pocket with the fuller residue overlap (11 of 21 contact residues,
pocket atoms 1.5 Å from the nearest ligand atom, opening nine-fold across the
ensemble). Every site ranked above them is the GDP pocket, a real pocket with a
real ligand already bound.

The workflow doesn't stop at discovery: it boxes Lacuna's top-ranked pocket,
preps a small ligand library, and docks every ligand concurrently with real
AutoDock Vina using a `horus_map` fan-out (one clone per ligand), so the
output is ranked binding poses, not just a pocket report.

## Quick start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

cd workflows/drug-discovery/w04-lacuna-cryptic-pocket-discovery
uv sync
# or: pip install horus-runtime horus-environments

# First run builds the uv-managed lacuna environment and the docking conda
# environments (micromamba/mamba/conda must be on PATH for the latter).
uv run horus run workflow.yaml
```

`discover`/`dock_prep` are pip-only (`uv`); `prep`/`dock` need a conda-family
tool on `PATH` for OpenBabel/Meeko/RDKit/Vina, the same prerequisite as
[W-02](../w02-autodock-vina-docking/README.md).

## Compute Pattern

| Stage | Task | Executor | Concurrency | Est. walltime (example) |
|---|---|---|---|---|
| Ensemble generation + pocket discovery | `discover` | uv venv | serial | ~1-2 min (20 conformers, NMA backend, CPU-only) |
| Docking-input export | `dock_prep` | uv venv | serial | <1 s |
| Receptor/ligand prep, boxed on the top pocket | `prep` | conda | serial | ~15 s (+ first-run env build) |
| **AutoDock Vina docking** | `dock[00..NN]` | conda | **N clones in parallel** | ~1 min total for 3 demo ligands, CPU-only |
| Ranked energy tables | `summary` | shell (stdlib) | serial | <1 s |

`dock` is a `kind: horus_map` task: it runs `scripts/dock_one.py` once per
ligand, concurrently, so docking scales with wall-clock concurrency rather
than the ligand count — a 100-ligand library is 100 independent Vina runs, a
natural cluster array job (see Horus Configuration below for how to point it
at one). Every other stage is serial and CPU-only.

## Tools & Dependencies

- **horus-runtime**, **horus-environments** (`uv_python_environment` and
  `conda_python_environment` executors)
- **lacuna-pockets** ≥ 1.1.0 (PyPI), installed into a `uv`-managed venv via
  `requirements:` — no `openmm`, `plm`, or `boltz` extras needed for the defaults
  used here
- `lacuna discover` / `lacuna dock-prep` CLI entrypoints (installed by the package)
- **conda-forge**: `openbabel` (receptor → rigid PDBQT), `meeko` + `rdkit`
  (ligand → PDBQT), `vina` (AutoDock Vina + Python bindings) — same stack as
  [W-02](../w02-autodock-vina-docking/README.md#implementation-notes), chosen
  there because conda-forge `vina` ships prebuilt osx-arm64/osx-64/linux-64/
  linux-aarch64 wheels and the PyPI package does not

## Horus Configuration

```
examples/structures/receptor.pdb ──► discover ──► results/pockets/
                        │               │             pocket_report.json
                        │               │             pocket_*.pdb
                        │               ▼
                        │          dock_prep ──► results/docking_inputs/
                        │                            pocket_0_vina.conf  (top-ranked pocket's box)
                        │                            pocket_*_constraint.yaml (Boltz)
                        │                            pocket_*_site.pdb
                        │               │
      examples/ligands.smi              ▼
                    │              prep (boxed on pocket_0_vina.conf)
                    └────────────────►  │ ──► results/receptor_box/   (receptor.pdbqt, box.json)
                                         │ ──► results/ligands_pdbqt/ (one *.pdbqt per ligand)
                                         │
                             dock[00..NN]  (horus_map: one clone per ligand)
                              receptor_box/ + ligand.pdbqt ─► AutoDock Vina
                                         │
                                  results/docked/<i>/
                                    {ligand}_out.pdbqt, status.json
                                         ▼
                                     summary ──► results/scores.csv, results/poses.csv
```

**Why `prep` writes two folders, not one.** A `horus_map` task fans out over
the *children* of one folder input (`over.input_id`) and every clone also
receives a copy of the map task's other declared inputs. So `ligands_pdbqt/`
must contain nothing but ligand files — mapping over it treats every child as
one item — while `receptor_box/` (receptor + box, shared by every clone) has
to live in a separate folder that ligands cannot also occupy.

Single local target for every task. To scale ensemble generation onto a
cluster, give the `discover` task a `target:`/`resources:` block; nothing else
changes, since the pipeline is one CLI call rather than a fan-out. To move
docking onto a cluster, give the `dock` task's own `target:`/`resources:` a
Slurm or container target — every clone inherits it, since `horus_map` has no
separate per-clone template to configure.

## Input / Output

**Input**

- `examples/structures/receptor.pdb` — apo KRAS(G12C), PDB 4LDJ. Any single PDB
  or mmCIF file works; repoint the `receptor` artifact to use your own.
- `examples/ligands.smi` — a 3-compound SMILES demo set (imatinib, caffeine,
  aspirin), reused from W-02. It exists to prove the docking mechanics work
  end to end, not as a curated KRAS screening library; repoint the `ligands`
  artifact at a real library for a real screen.

**Output** (under `horus_workflow_results/results/`)

- `pockets/pocket_report.json` — every surviving pocket cluster: rank, druggability,
  persistence (fraction of conformers it appears in), crypticity (how much it opens
  relative to the input), contact residues, and per-conformer detail
- `pockets/pocket_*.pdb` — pseudoatom PDB files per pocket, for visualization
- `docking_inputs/` — for the top 5 ranked pockets: AutoDock Vina box configs,
  Boltz-2 YAML constraints, and pocket PDBs
- `receptor_box/` — the receptor PDBQT and the resolved box, boxed on
  `docking_inputs/pocket_0_vina.conf` (Lacuna's rank-1 pocket);
  `ligands_pdbqt/` — one PDBQT per ligand
- `docked/<i>/` — one slot per `dock` map clone: `{ligand}_out.pdbqt` (poses +
  affinities) and `status.json` recording whether that ligand docked
- `scores.csv` — ligands ranked by best affinity (kcal/mol, more negative is
  stronger); `poses.csv` — every pose of every ligand

## Parameterization

| What | Where |
|---|---|
| Ensemble size | `discover` task → `--conformers` |
| Ensemble backend | `discover` task → `--backend` (`nma` default, `openmm`/`boltz` need the matching extra) |
| Pocket detector | `discover` task → `--detector` (`alpha`, `surface`, `surface-fusion`, `p2rank`, `fusion`) |
| Ranking strategy | `discover` task → `--rank-by` (`learned`, `learned-plm`, `crypticity`, `druggability`, `balanced`, `persistence`) |
| Result filters | `discover` task → `--min-druggability`, `--min-persistence`, `--min-crypticity` |
| Dimer-interface pockets | `discover` task → `--homodimer` (needs a biological-assembly PDB with BIOMT records) |
| How many pockets to export for docking | `dock_prep` task → `--top` |
| Docking format | `dock_prep` task → `--format` (`vina`, `boltz`, `pdb`, `all`) |
| Which ranked pocket to dock into | `prep` task → `--box-config`, e.g. swap `pocket_0_vina.conf` for `pocket_3_vina.conf` to dock the switch-II cryptic pocket from the Overview instead of the default rank-1 (GDP) site |
| Ligand library | `ligands` artifact → point at your own `.smi`/`.sdf` (each ligand becomes its own `dock` clone automatically) |
| Docking search effort | `dock` task → `--exhaustiveness`, `--n-poses`, `--cpu` |
| Docking concurrency cap | `dock` task → `max_concurrency` (default: a conservative built-in cap; see Implementation Notes) |

## Implementation Notes

- **Two tasks instead of one.** `discover` could emit Vina boxes and Boltz
  constraints directly via `--emit-vina-boxes --emit-boltz-constraints`. It is
  split into `discover` + `dock_prep` instead so the number of pockets exported
  and their format can be changed (`--top`, `--format`) without rerunning ensemble
  generation and detection, the expensive part of the pipeline.
- **Two executors, split at the discovery/docking boundary.** `discover` and
  `dock_prep` need only `lacuna-pockets`, a plain pip package, so they run in a
  `uv_python_environment`. `prep` and `dock` need OpenBabel/Meeko/RDKit/Vina,
  which come from conda-forge for the same platform-coverage reason as W-02
  (see Tools & Dependencies), so they run in `conda_python_environment`.
- **`prep` strips the receptor to `ATOM` records before `obabel`.** An RCSB
  export's `HEADER`/`TITLE`/`COMPND`/... lines get copied verbatim into the
  PDBQT by `obabel`, which Vina's parser then rejects outright ("Unknown or
  inappropriate tag found in rigid receptor"). Dropping `HETATM` at the same
  time also removes the bound GDP and crystallographic waters — necessary
  because the default docked pocket (rank 1) *is* the GDP site; docking a new
  ligand there with GDP still present would score against an occupied pocket.
  See `scripts/prep.py:extract_protein_only`.
- **`dock` is a `kind: horus_map` task, not the older `map:`/`gather:` block.**
  horus-runtime replaced the nested `map: {over, template, gather}` shape
  (still used by [W-30's `dock`
  task](../../bioexcel_building_blocks/w22-cavity-guided-virtual-screening/README.md))
  with a first-class `horus_map` task kind: the task's own `inputs`,
  `outputs`, `executor`, and `runtime` *are* the per-item body, named by
  `over: {input_id, as}` instead of a nested template, and its single folder
  output already holds every clone's numbered slot with no separate `gather:`
  target or edge needed downstream. Pin `horus-runtime>=0.5.0` (this
  workflow's floor) if reusing this pattern elsewhere in the repo before that
  version is otherwise pulled in.
- **Two disjoint output folders make the fan-out possible.** A `FolderArtifact`
  maps over its own immediate children, so `ligands_pdbqt/` has to contain
  only ligand PDBQTs — see the Horus Configuration section above for why
  `prep` can't just write one `vina_inputs/` tree the way W-02 does.
- **Each `dock` clone must not raise, whatever the ligand does.** A clone
  failure aborts the run or blocks the ranking step, so `dock_one.py` catches
  every exception around the Vina call itself and records `status: failed` in
  its slot's `status.json` instead — `summary.py` treats that as a ligand to
  skip, not a zero-affinity result.
- **`--detector surface-fusion` auto-selects a matching ranker.** When both
  detectors are pooled and `--rank-by` is left at its default, Lacuna switches to
  `learned-fused`, the ranker fitted on the pooled candidate set; ranking a fused
  pool with the alpha-only weights would cost top-five recovery, because a surface
  proposal is a wrong answer that ranker scores highly.
- The conformer that seeds detection always includes conformer 0 (the input
  structure itself, unperturbed), so a pocket that never leaves the crystal
  structure is still reported.

Bundled result: docking the demo ligand library into Lacuna's rank-1 (GDP)
pocket on 4LDJ ranks imatinib best (~-7.3 kcal/mol), then caffeine (~-4.6),
then aspirin (~-4.3) — plausible relative to the ligands' sizes, and none of
the three were built or fitted with this pocket in mind, so treat it as a
mechanics check, not a hit. Vina's search is stochastic (no fixed seed here),
so exact values shift a few tenths between runs; the ranking is stable.

## Open Questions

- **Docking W-02 as a separate downstream workflow instead of inline
  `prep`/`dock`/`summary` tasks.** This workflow adapts W-02's `prep`/`summary`
  scripts rather than chaining to it, because W-02's `prep` task takes an
  explicit `--center`/`--size` while this one boxes on a Lacuna-emitted
  `pocket_N_vina.conf` — inlining kept the box source a single `--box-config`
  flag instead of a second bridging task. Revisit if W-02 grows a
  `--box-config` option of its own; its own `dock` task could similarly be
  ported to `horus_map` at that point.
- **No batching for very large libraries.** `dock` maps one clone per ligand,
  which is the simplest possible fan-out and fine for the 3-compound demo; a
  library of thousands of ligands would want a batching layer in front of it
  (group N ligands per clone) to bound clone count, the way [W-30's `dock`
  task](../../bioexcel_building_blocks/w22-cavity-guided-virtual-screening/README.md)
  batches SDF/SMILES records. Not needed at this workflow's demo scale.
- **Higher-fidelity ensembles.** `--backend openmm` (100 ps implicit-solvent MD) or
  `--backend boltz` (diffusion sampling, GPU) would need their extras added to
  `requirements:` and, for Boltz, a GPU-capable `target:`; not wired up here to
  keep the default run CPU-only and dependency-light.
- **Sequence-assisted ranking.** `--rank-by learned-plm` / `--seed-from-sequence`
  need the `plm` extra (`torch`, `transformers`) and download an ESM-2 checkpoint
  on first use; left off by default for the same reason.

## References

- Lacuna: [mooreneural/lacuna](https://github.com/mooreneural/lacuna),
  [PyPI](https://pypi.org/project/lacuna-pockets/)
- Moore CW. *Lacuna: Cryptic Binding Pocket Discovery via Conformational Ensemble
  Analysis.* bioRxiv 2026. doi:10.64898/2026.08.14.744956
- Moore CW. *Cryptic binding sites are detected but not ranked: coverage,
  conversion, and the limits of detector consensus.* bioRxiv 2026.
  doi:10.64898/2026.08.11.743381
- CryptoBench: Vavra et al. 2024
- Example structure: PDB [4LDJ](https://www.rcsb.org/structure/4LDJ) — Hunter et
  al., apo GDP-bound KRAS(G12C)
- Docking stack ported from: [W-02 AutoDock Vina Docking](../w02-autodock-vina-docking/README.md)
- Downstream (Boltz constraints for unchosen pockets):
  [W-01 Boltz-2 Virtual Screening](../w01-boltz2-virtual-screening/README.md)
- Related: [W-31 Cavity Analysis](../../bioexcel_building_blocks/w23-cavity-analysis/README.md)
- AutoDock Vina: Eberhardt et al., *J. Chem. Inf. Model.* (2021); Trott &
  Olson, *J. Comput. Chem.* (2010)
