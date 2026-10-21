# W-31 · Cavity Analysis

Detect and filter cavities with fpocket on every structure of a conformational ensemble in parallel, then rank the models by their best cavity's volume, druggability and score.

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

Detects and ranks druggable cavities across a conformational ensemble (MD cluster representatives, NMR models or any set of related structures). fpocket runs on each model, cavities are filtered by score, druggability and volume, and models are ranked by their best cavity. The result indicates which conformation to dock into with [W-30](../w22-cavity-guided-virtual-screening/README.md). The workflow has 3 tasks.

## Pipeline

```
prepare_models                                  Wrap each structure in its own model folder
analyze[00..NN]                                 One clone per model: extract_molecule, fpocket_run, fpocket_filter, optional residue-distance filter
summarize                                       Rank models by volume, druggability and score
```

## Inputs / Outputs

Outputs (`results/`):
- `summaries/summary_by_volume.yml`, `summaries/summary_by_drug_score.yml`, `summaries/summary_by_score.yml`: models with at least one surviving cavity, ordered by largest cavity, most druggable cavity and best-scoring cavity
- `summaries/cavity_report.json`: models analysed, models with a cavity, winner per metric, failures
- `analyzed/<slot>/`: per-model `summary.json` (all cavities, pre-filter), `filtered_pockets.zip`, `model.pdb`, `status.json`

A model with no cavity inside the filter windows is absent from the summaries and counted in `cavity_report.json`. A failing model is recorded in `status.json` and does not fail the run.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `structures` | `examples/structures/` | Folder of PDB models (a single `.pdb` also works). |
| `min_druggability` | 0.2 | Cavities below this fpocket druggability score are dropped (0-1). |
| `min_volume` | 100 | Cavities smaller than this are dropped (0-5000). |
| `max_volume` | 5000 | Cavities larger than this are dropped (100-20000); keep above `min_volume`. |
| `residue_selection` | empty | MDAnalysis selection of a site of interest (e.g. `resid 31 or resid 21`); only cavities within 10 Å of its centre of mass are kept. Empty keeps every cavity. |

## References

- [BioExcel Building Blocks (biobb_vs)](https://github.com/bioexcel/biobb_vs)
- [fpocket](https://github.com/Discngine/fpocket)
- [MDAnalysis](https://github.com/MDAnalysis/mdanalysis)
- fpocket: Le Guilloux, Schmidtke & Tuffery, *BMC Bioinformatics* (2009)
- [BioExcel Building Blocks](https://mmb.irbbarcelona.org/biobb/) documentation
- Downstream: [W-30 Cavity-Guided Virtual Screening](../w22-cavity-guided-virtual-screening/README.md)
- Related: [W-06 Fan-out / Map / Gather](../../engine-showcases/w01-fanout-map-gather/README.md)
