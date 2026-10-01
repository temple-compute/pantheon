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

This workflow stops at discovery. To go on and dock a ligand library into the
top pocket, see [Lacuna + AutoDock Vina Docking](../w07-lacuna-vina-docking/README.md).

## Quick start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

cd workflows/drug-discovery/w06-lacuna-cryptic-pocket-discovery
uv sync
# or: pip install horus-runtime horus-environments

# First run builds the uv-managed lacuna environment.
uv run horus run workflow.yaml
```

## Compute Pattern

| Stage | Task | Executor | Concurrency | Est. walltime (example) |
|---|---|---|---|---|
| Ensemble generation + pocket discovery | `discover` | uv venv | serial | ~1-2 min (20 conformers, NMA backend, CPU-only) |
| HTML report + CSV table | `report` | shell (stdlib) | serial | <1 s |

Serial, CPU-only tasks.

## Tools & Dependencies

- **horus-runtime**, **horus-environments** (`uv_python_environment` executor)
- **lacuna-pockets** ≥ 1.1.0 (PyPI), installed into a `uv`-managed venv via
  `requirements:` — no `openmm`, `plm`, or `boltz` extras needed for the defaults
  used here
- `lacuna discover` CLI entrypoint (installed by the package)

## Horus Configuration

```
examples/structures/receptor.pdb ──► discover ──► results/pockets/
                                                     pocket_report.json
                                                     pocket_*.pdb
                                          │
                                       report ──► results/report.html
                                              └─► results/pockets.csv
```

Single local target. To scale ensemble generation onto a cluster, give the
`discover` task a `target:`/`resources:` block.

## Input / Output

**Input**

- `examples/structures/receptor.pdb` — apo KRAS(G12C), PDB 4LDJ. Any single PDB
  or mmCIF file works; repoint the `receptor` artifact to use your own.

**Output** (under `horus_workflow_results/results/`)

- `pockets/pocket_report.json` — every surviving pocket cluster: rank, druggability,
  persistence (fraction of conformers it appears in), crypticity (how much it opens
  relative to the input), contact residues, and per-conformer detail
- `pockets/pocket_*.pdb` — pseudoatom PDB files per pocket, for visualization
- `report.html` — single-file ranked-pocket report (stats plus a sortable, filterable AG Grid table) with an interactive Mol* view of the receptor; each row's View button selects that pocket's lining residues and moves the camera to them; renders as a live page in the Horus UI. Mol* and AG Grid are loaded from the jsDelivr CDN, so the report needs internet access
- `pockets.csv` — the same ranking as a flat table; renders as a table in the Horus UI

## Parameterization

| What | Where |
|---|---|
| Ensemble size | `discover` task → `--conformers` |
| Ensemble backend | `discover` task → `--backend` (`nma` default, `openmm`/`boltz` need the matching extra) |
| Pocket detector | `discover` task → `--detector` (`alpha`, `surface`, `surface-fusion`, `p2rank`, `fusion`) |
| Ranking strategy | `discover` task → `--rank-by` (`learned`, `learned-plm`, `crypticity`, `druggability`, `balanced`, `persistence`) |
| Result filters | `discover` task → `--min-druggability`, `--min-persistence`, `--min-crypticity` |
| Dimer-interface pockets | `discover` task → `--homodimer` (needs a biological-assembly PDB with BIOMT records) |

## Implementation Notes

- **`--detector surface-fusion` auto-selects a matching ranker.** When both
  detectors are pooled and `--rank-by` is left at its default, Lacuna switches to
  `learned-fused`, the ranker fitted on the pooled candidate set; ranking a fused
  pool with the alpha-only weights would cost top-five recovery, because a surface
  proposal is a wrong answer that ranker scores highly.
- The conformer that seeds detection always includes conformer 0 (the input
  structure itself, unperturbed), so a pocket that never leaves the crystal
  structure is still reported.

## Open Questions

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
- Downstream docking: [Lacuna + AutoDock Vina Docking](../w07-lacuna-vina-docking/README.md)
- Related: [W-31 Cavity Analysis](../../bioexcel_building_blocks/w23-cavity-analysis/README.md)
