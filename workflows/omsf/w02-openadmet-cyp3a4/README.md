# W-38 · OpenADMET CYP3A4 Inhibition Models

Train and cross-validate OpenADMET models on CYP3A4 IC50 data in parallel, compare them statistically, and predict new compounds with the best one.

![Domain: OMSF](https://img.shields.io/badge/domain-omsf-blue)

## Overview

Predicts CYP3A4 inhibition (pIC50) with [OpenADMET](https://github.com/OpenADMET/openadmet-models) v0.2.0 models, ported from the OpenADMET Showcase in the OMSF workflow directory. It writes one `openadmet anvil` cross-validation recipe per model, trains all models in parallel (one map clone each), compares them statistically with `openadmet compare` and predicts the compound set with the model with the best mean CV R2. The workflow has 5 tasks.

## Pipeline

```
make_recipes  cleaned training data       --> data/cleaned.csv, recipes/<model>/{recipe.yaml,data.csv}
train         openadmet anvil, 1 per model --> trained/<slot>/model/
compare       openadmet compare           --> results/comparisons/
predict       best mean CV R2 model       --> results/predictions.csv
report        CV metrics + top compounds  --> results/metrics.csv, results/top_predictions.csv
```

`compare` and `predict` both run after `train`; `predict` picks the best model itself.

## Inputs / Outputs

- `dataset`: training parquet, one row per compound, with `OPENADMET_CANONICAL_SMILES` and `pchembl_value_mean`. Default: ChEMBL35 CYP3A4 IC50 aggregate from OpenADMET/data-catalogs.
- `compounds`: CSV to predict with an `OPENADMET_CANONICAL_SMILES` column. Default: 10,000 ZINC compounds from openadmet-demos `showcase/`.
- `results/metrics.csv`: per model, mean and 95% CI of R2, MAE, MSE, Spearman and Kendall tau over the CV folds, and a `best` flag for the picked model.
- `results/top_predictions.csv`: top 50 compounds by predicted pIC50. `results/predictions.csv`: every predicted compound.
- `results/comparisons/`: `openadmet compare` statistical tests (ANOVA, Levene, Tukey HSD) and PDF plots.
- `trained/<slot>/model/`: anvil output (model, CV metrics, plots, recipe).

## Parameters

| id | Default | Meaning |
|---|---|---|
| `dataset` | ChEMBL35 CYP3A4 parquet | Training set |
| `compounds` | `examples/compounds_for_inference.csv` | Compounds to predict |
| `target_name` | `CYP3A4` | Biological target label, written to the cleaned data's `Target` column and the recipes' `biotargets` |
| `models` | `lgbm`, `rf`, `xgboost`, `catboost` | Models to train; `chemprop` can be added |
| `cv_folds` | 5 | k of the repeated k-fold CV (2-10) |
| `cv_repeats` | 5 | Repeats of the k-fold CV (1-10) |

## References

- [OpenADMET models](https://github.com/OpenADMET/openadmet-models)
- [OpenADMET demos (GitHub)](https://github.com/OpenADMET/openadmet-demos)
- [molfeat (OpenADMET fork)](https://github.com/OpenADMET/molfeat)
- [Chemprop](https://github.com/chemprop/chemprop)
- [RDKit](https://github.com/rdkit/rdkit)
- [OpenADMET demos site](https://demos.openadmet.org)
- [OMSF workflow directory](https://directory.omsf.io/workflows/)
- [Model comparison guidelines followed by `openadmet compare` (ChemRxiv)](https://chemrxiv.org/engage/chemrxiv/article-details/672a91bd7be152b1d01a926b)
- License: workflow glue is MIT. openadmet-demos and openadmet-models are Apache-2.0; data-catalogs is Apache-2.0, derived from ChEMBL 35 (CC BY-SA 3.0), and the bundled training parquet keeps that license.
