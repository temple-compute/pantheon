# W-34 · Lacuna + AutoDock Vina Docking

Find cryptic pockets in a protein with Lacuna, box the pocket you pick, and dock a ligand library into it with AutoDock Vina, one parallel job per ligand.

![Domain: Drug Discovery](https://img.shields.io/badge/domain-drug--discovery-blue)

## Overview

Finds cryptic pockets with [Lacuna](https://github.com/mooreneural/lacuna), boxes the pocket you pick and docks a ligand library into it with AutoDock Vina, one parallel clone per ligand. The example is apo KRAS(G12C), PDB 4LDJ, with a 3-compound demo library (imatinib, caffeine, aspirin). The workflow has 6 tasks; for discovery only see [W-33](../w06-lacuna-cryptic-pocket-discovery/README.md).

## Pipeline

```
discover  receptor.pdb or RCSB pdb_id ──► results/pockets/
dock_prep ranked pockets              ──► results/docking_inputs/ (Vina box + Boltz constraints, top 5)
prep      receptor + ligands.smi      ──► results/receptor_box/, results/ligands_pdbqt/
dock      AutoDock Vina, 1 per ligand ──► results/docked/<i>/
summary   parse affinities            ──► results/scores.csv + results/poses.csv
report    pocket_report.json          ──► results/report.html + results/pockets.csv
```

## Inputs / Outputs

- `receptor`: apo structure, PDB or mmCIF (default 4LDJ), or `pdb_id` to fetch from RCSB.
- `ligands`: SMILES or SDF; each ligand becomes one `dock` clone.
- `results/pockets/` (`pocket_report.json`, `pocket_*.pdb`, `receptor.pdb`), `results/report.html`, `results/pockets.csv`: ranked pockets, as in W-33.
- `results/docking_inputs/`: Vina box configs, Boltz-2 YAML constraints and pocket PDBs for the top 5 pockets.
- `results/receptor_box/`: `receptor.pdbqt` and `box.json`; `results/ligands_pdbqt/`: one PDBQT per ligand.
- `results/docked/<i>/`: `{ligand}_out.pdbqt` and `status.json` per clone; a failed ligand is skipped.
- `results/scores.csv`: ligands ranked by best affinity (kcal/mol, more negative is stronger); `results/poses.csv`: every pose.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `receptor` | `examples/structures/receptor.pdb` (4LDJ) | Apo structure, used when `pdb_id` is empty |
| `pdb_id` | empty | 4-character PDB code to fetch instead of the upload |
| `ligands` | `examples/ligands.smi` | Ligand library |
| `conformers` | 20 | Ensemble size (5-200) |
| `detector` | `surface-fusion` | `surface-fusion`, `surface` or `alpha` |
| `rank_by` | `learned` | `learned`, `crypticity`, `druggability`, `balanced` or `persistence` |
| `pocket` | Rank 1 | Ranked pocket (1-5) that gets the Vina box; on 4LDJ, Rank 4 is the switch-II pocket |
| `exhaustiveness` | 8 | Vina search effort per ligand (1-64) |
| `n_poses` | 9 | Poses per ligand (1-20) |

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
- Related: [W-31 Cavity Analysis](../../bioexcel_building_blocks/w23-cavity-analysis/README.md)
- AutoDock Vina: Eberhardt et al., *J. Chem. Inf. Model.* (2021); Trott &
  Olson, *J. Comput. Chem.* (2010)
