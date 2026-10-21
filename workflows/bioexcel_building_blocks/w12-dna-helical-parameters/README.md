# W-17 · DNA Helical Parameters

Every DNA helical parameter, backbone torsion, stiffness and correlation from an MD trajectory, with Curves+ and Canal.

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

Analyzes a DNA MD trajectory with `biobb_dna` (Curves+ and Canal). The example is the Drew-Dickerson dodecamer (CGCGAATTCGCG, PDB 1BNA), a 500 ns trajectory from BigNASim. Curves+ extracts helical parameters, Canal builds time series and histograms, and a fan-out of tasks computes averages, time series, stiffness, bimodality and correlations. The workflow has 70 tasks.

## Pipeline

```
curves                  Helical parameters (Curves+)
canal                   Time series and histograms (Canal)
avg_*                   20 average helical parameters (step, base pair, axis, groove)
puckering, canonicalag, bipopulations   Sugar pucker, canonical alpha/gamma, BI/BII populations
ts_*                    36 time series of helical parameters and backbone torsions
average_stiffness, basepair_stiffness   Stiffness / elastic constants
dna_bimodality          Twist bimodality at the selected step
intraseqcorr, interseqcorr, intrahpcorr, interhpcorr, intrabpcorr, interbpcorr   Correlations
```

## Inputs / Outputs

- Inputs: solvent-stripped trajectory `traj` and matching topology `top` (defaults in `TRAJ/`), one double-stranded DNA with strand 2 numbered right after strand 1.
- Outputs (`results/`): `curves.out.lis`, `curves.out.cda`, `canal.out.zip`, `<param>.averages.{csv,jpg}`, `<param>.timeseries.zip`, the selected-position series `timeseries/series_<param>_step.csv` (step parameters) and `timeseries/series_<param>_bp.csv` (base-pair parameters), `twist.stiffness.csv`, `stiffness_bps.csv`, `twist.bimodality.csv`, and the correlation CSVs (`twist.intrabp_correlation.csv`, `twist.interbp_correlation.csv`, `helpar_bp(s)_correlation.csv`, `bp(s)_correlation.csv`).

## Parameters

| id | Default | Meaning |
|---|---|---|
| `traj` | `TRAJ/structure.stripped.nc` | NetCDF trajectory (500 ns dodecamer, BigNASim NAFlex_DDD_II) |
| `top` | `TRAJ/structure.stripped.top` | AMBER topology matching the trajectory |
| `sequence` | `CGCGAATTCGCG` | Strand 1, 5' to 3'; sets the Curves+ strand ranges and labels |
| `bp_step` | `3` | Position read by the stiffness, bimodality and helical-parameter correlation tasks: step i (bases i, i+1) and base pair i. Valid from 2 to sequence length minus 2; the default is the C3G4 CpG step |

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [biobb_dna](https://github.com/bioexcel/biobb_dna)
- [Curves+](https://curvesplus.bsc.es/)
- [biobb_wf_dna_helparms tutorial notebook](https://github.com/bioexcel/biobb_wf_dna_helparms)
- [NAFlex server](https://mmb.irbbarcelona.org/NAFlex)
