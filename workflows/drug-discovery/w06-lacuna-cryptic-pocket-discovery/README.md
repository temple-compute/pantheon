# W-33 · Lacuna Cryptic Pocket Discovery

Find cryptic binding pockets in a protein (uploaded or fetched by PDB ID) across a generated conformational ensemble with Lacuna, ranked in an interactive report.

![Domain: Drug Discovery](https://img.shields.io/badge/domain-drug--discovery-blue)

## Overview

Finds cryptic binding pockets (sites that open only on ligand binding) with [Lacuna](https://github.com/mooreneural/lacuna). It generates a conformational ensemble from the input structure, detects pockets in every conformer, clusters them across the ensemble and ranks them with a fitted model that also scores crypticity. Since v1.4.0 it also scores every residue (`residue_propensity`) and flags pockets at chain interfaces; RNA/DNA input works with no extra flags. The example is apo KRAS(G12C), PDB 4LDJ. The workflow has 2 tasks; for docking into the top pocket see [W-34](../w07-lacuna-vina-docking/README.md).

## Pipeline

```
discover  receptor.pdb or RCSB pdb_id ──► results/pockets/ (pocket_report.json, pocket_*.pdb)
report    pocket_report.json          ──► results/report.html + results/pockets.csv + results/residue_propensity.csv
```

## Inputs / Outputs

- `receptor`: apo structure, PDB or mmCIF (default 4LDJ), or `pdb_id` to fetch from RCSB.
- `results/pockets/pocket_report.json`: every surviving pocket cluster with rank, druggability, persistence, crypticity, chain shares / interface flag, contact residues and per-conformer detail, plus the per-residue `residue_propensity` map.
- `results/pockets/pocket_*.pdb`: pseudoatom files per pocket; `results/pockets/receptor.pdb`: copy of the receptor used.
- `results/report.html`: ranked-pocket report with a sortable table and an interactive Mol* view.
- `results/pockets.csv`: the same ranking as a flat table.
- `results/residue_propensity.csv`: per-residue cryptic-pocket score (inverse-rank-weighted fraction of conformers in which the residue lines a pocket; can exceed 1, unlisted residues score 0), highest first. On the CryptoBench held-out fold it reaches AUROC 0.774 / AUPRC 0.345 with 20 conformers.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `receptor` | `examples/structures/receptor.pdb` (4LDJ) | Apo structure, used when `pdb_id` is empty |
| `pdb_id` | empty | 4-character PDB code to fetch instead of the upload |
| `conformers` | 20 | Ensemble size (5-200) |
| `detector` | `surface-fusion` | `surface-fusion`, `surface` or `alpha` |
| `rank_by` | `learned` | `learned`, `crypticity`, `druggability`, `balanced` or `persistence` |
| `top` | 10 | Pockets reported (1-50) |
| `min_druggability` | 0 | Drop pockets below this druggability (0-1) |

## References

- [Lacuna (GitHub)](https://github.com/mooreneural/lacuna)
- [Lacuna (PyPI)](https://pypi.org/project/lacuna-pockets/)
- Moore CW. *Lacuna: Cryptic Binding Pocket Discovery via Conformational Ensemble
  Analysis.* bioRxiv 2026. doi:10.64898/2026.08.14.744956
- Moore CW. *Cryptic binding sites are detected but not ranked: coverage,
  conversion, and the limits of detector consensus.* bioRxiv 2026.
  doi:10.64898/2026.08.11.743381
- [Lacuna v1.4.0 release notes](https://github.com/mooreneural/lacuna/releases/tag/v1.4.0)
- CryptoBench: Škrhák et al. 2025, *Bioinformatics* 41(1):btae745
- zPocket / PocketWatch: Portnoi T, Keys AM, DiFrancesco BR, Gruver N. [arXiv:2610.17696](https://arxiv.org/abs/2610.17696) (2026)
- Example structure: [PDB 4LDJ](https://www.rcsb.org/structure/4LDJ) — Hunter et
  al., apo GDP-bound KRAS(G12C)
- Downstream docking: [Lacuna + AutoDock Vina Docking](../w07-lacuna-vina-docking/README.md)
- Related: [W-31 Cavity Analysis](../../bioexcel_building_blocks/w23-cavity-analysis/README.md)
