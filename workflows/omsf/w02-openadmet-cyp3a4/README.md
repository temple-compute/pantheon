# W-38 · OpenADMET CYP3A4 Inhibition Models

![Domain: OMSF](https://img.shields.io/badge/domain-omsf-blue)

## Overview

A native Horus port of the **OpenADMET Showcase** from the
[OMSF workflow directory](https://directory.omsf.io/workflows/): predict how
strongly small molecules inhibit CYP3A4, a common drug-drug-interaction
anti-target. Upstream it is one notebook
([OpenADMET/openadmet-demos](https://github.com/OpenADMET/openadmet-demos),
`showcase/OpenADMET_Models_Showcase.ipynb`, plus `demos/02`-`05`). Here each
notebook stage is its own task:

1. fetch the ChEMBL35 CYP3A4 IC50 aggregate and a set of ZINC compounds,
2. write one `openadmet anvil` cross-validation recipe per model type,
3. train every model in parallel (one map clone each),
4. compare the models statistically with `openadmet compare`,
5. predict the inference set with the best model (`openadmet predict`),
6. tabulate CV metrics and the top predicted inhibitors.

Tree models train on CPU in minutes. Chemprop (a graph neural network) needs
a GPU, which is why the full profile sends the training map to Slurm.

## Pipeline

```
fetch_data    (local, shell)   curl parquet + inference CSV at pinned commits
   │
make_recipes  (local, conda)   OPENADMET_* headers, recipes/<model>/{recipe.yaml,data.csv}
   │
train         (map, conda)     openadmet anvil, one clone per model    smoke: local CPU / full: _gpu Slurm
   ├──────────────┐
compare           predict      openadmet compare  |  best mean CV R2 -> openadmet predict
                     │
                  report       metrics.csv, top_predictions.csv
```

## Quick start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install the horus-runtime and plugins (one time)
uv sync

# Run the workflow (smoke profile by default)
uv run horus run workflow.yaml
```

Executor: `conda_python_environment` with `micromamba` (set `conda:` in the
`_conda` anchor to `mamba` or `conda` if that is what you have). The first
task builds the env from `conda_env.yaml` into
`horus_workflow_results/.horus_conda_env/` (about 1 min with a warm package cache). Later runs reuse it.

## Compute Pattern

| Stage | Smoke (default) | Full |
|---|---|---|
| fetch_data | local, seconds | same |
| make_recipes | local CPU, seconds | same |
| train (map) | 2 clones (lgbm, rf) in parallel, 2 threads each, local CPU, about 5 min | 5 clones (lgbm, rf, xgboost, catboost, chemprop) on the `_gpu` Slurm anchor, 1 GPU + 8 CPUs each, hours |
| compare | local CPU, about 20 s | same |
| predict | best model on the first 2000 compounds, about 40 s | all 10,000 compounds, a few min |
| report | seconds | same |

## Tools & Dependencies

- [openadmet-models](https://github.com/OpenADMET/openadmet-models) **v0.2.0**
  (git tag, commit `cdf3e9f7`). It is not on PyPI or conda-forge, so the env
  file installs it from the tag. v0.2.0 has every CLI command and flag the
  showcase uses (`anvil --recipe-path/--output-dir`, `compare
  --model-stats-fns/--labels/--task-names/--output-dir/--report`, `predict
  --input-path/--input-col/--model-dir/--output-csv/--accelerator`), so no
  `main` commit is needed. One difference from `main`: `predict
  --accelerator` defaults to `gpu` in v0.2.0, so the workflow always passes
  `--accelerator cpu`.
- `conda_env.yaml`: the runtime part of upstream
  `devtools/conda-envs/openadmet-models.yaml` (pytorch, chemprop, lightgbm,
  xgboost, catboost, rdkit, the OpenADMET molfeat fork at a pinned commit, and
  so on). Test and notebook tools and the optional TabPFN/TabICL/NePaRe extras
  are left out. Every package is pinned to the versions of a working solve.
- Data: [OpenADMET/data-catalogs](https://github.com/OpenADMET/data-catalogs)
  at `65dd4ee3` and `showcase/compounds_for_inference.csv` from
  openadmet-demos at `8b2c5f34`. Both are downloaded at run time.

### Container option

OpenADMET publishes `ghcr.io/openadmet/openadmet-models:main`. That tag
moves, so it is not the default. To use it, replace the `_conda` anchor with:

```yaml
_conda: &conda
  kind: docker
  image: ghcr.io/openadmet/openadmet-models:main
  gpus: all # only on a GPU host
```

## Horus Configuration

- **profile** (`choice` artifact, `smoke` | `full`, default `smoke`). It is
  stored at `params/profile.txt` as the bare option text, and `${profile}`
  renders as `smoke` or `full`. `make_recipes.py` and `models.py predict`
  read it from `--profile`.
- **train** is a `horus_map` over `recipes/`. Each child folder
  (`recipes/lgbm/`, `recipes/rf/`, ...) holds `recipe.yaml` and its own copy
  of the data. The recipe points at `{{ ANVIL_DIR }}/data.csv`, so the slot
  works on any target the clone is copied to. Each clone writes its anvil
  output to `trained/<slot>/model/`. Slots are numbered (`0`, `1`, ...), and
  the model name is read from `model/anvil_recipe.yaml`.
- **Full on Slurm/GPU**: set `partition` and `account` in the `_gpu` anchor,
  change the train task's `target: *local` to `target: *gpu`, and set the
  `profile` artifact to `full` (edit `value:` in `workflow.yaml` or pick it
  in the UI). That target change is the only edit. `resources.gpus: 1` is
  already on the task; the local target ignores it unless a capacity is
  declared. A map runs every clone on one target, so the tree models also
  land on GPU nodes in the full run. They only use the allocation's CPUs.
- Threads: smoke sets `n_jobs: 2` (catboost: `thread_count`) on the
  featurizers and models, with `max_concurrency: 2`. Full sets `n_jobs: -1`,
  which means the whole Slurm allocation. The upstream featurizers default to
  `-1` (every core on the host), so the recipes always set it explicitly.

## Input / Output

**Inputs**: none to provide. Both data files are fetched from pinned commits.

**Outputs** (under `horus_workflow_results/`):

| File | Renders as | What |
|---|---|---|
| `results/metrics.csv` | table | One row per model: mean and 95% CI of R2, MAE, MSE, Spearman, Kendall tau over the CV folds, and which model was picked |
| `results/top_predictions.csv` | table | Top 50 compounds by predicted pIC50 (strongest predicted inhibitors) |
| `results/predictions.csv` | table | Every predicted compound, `OADMET_PRED_openadmet-chembl_OPENADMET_LOGAC50` column |
| `results/comparisons/` | PDFs + JSON | `openadmet compare` report: `anova.pdf`, `mcs_plots.pdf`, `mean_diffs.pdf`, `normality_plots.pdf`, `paired_plots.pdf`, `posthoc.pdf`, `Levene.json`, `Tukey_HSD.json` |
| `trained/<slot>/model/` | files | anvil output: `model.pkl`/`model.pth`, `cross_validation_metrics.json`, `regression_metrics.json`, CV plots (PNG), `anvil_recipe.yaml` |
| `data/cleaned_cyp3a4.csv` | table | Training data with the `OPENADMET_*` headers |

## Parameterization

| Parameter | Where | Smoke | Full |
|---|---|---|---|
| models | `PROFILES` in `scripts/make_recipes.py` | lgbm, rf | lgbm, rf, xgboost, catboost, chemprop |
| CV (splits x repeats) | same | 2 x 2 | 5 x 5 (upstream) |
| trees per model | same | at most 50 | lgbm 500 (upstream), rf 100, xgboost/catboost 500 |
| threads | same | 2 | all of the allocation |
| inference compounds | `SMOKE_COMPOUNDS` in `scripts/models.py` | 2000 | 10,000 |
| selection metric | `--metric` of `models.py predict` | mean CV R2 | same |

## Expected runtime

- Smoke, measured on this repo's 16-core shared dev host with about 5 cores:
  **7 min** for a cold run, including about 1 min to build the env
  (fetch 1 s, make_recipes 58 s with the env build, train 5 min 16 s with
  lgbm 3.4 min and rf 5.3 min in parallel, compare 22 s, predict 41 s,
  report < 1 s). A re-run takes about 1 s: every task is skipped by
  `skip_if_complete`. Peak use was about 4 cores and under 4 GB RAM per clone.
  The smoke run picked rf (mean CV R2 0.51 against 0.45 for lgbm).
- Full: not run by us (no GPU or Slurm on the dev host). Upstream 5x5 CV on
  about 4900 compounds is minutes per tree model and tens of minutes to hours
  for Chemprop on one GPU (25 CV refits of up to 50 epochs).

## Implementation Notes

- No notebook code is copied. The glue is two scripts:
  `scripts/make_recipes.py` (cleaning as in showcase cells 9-13, plus recipe
  generation) and `scripts/models.py` (compare, best-model pick + predict,
  report). Both have `--selftest`; run them with the env's python:
  `horus_workflow_results/.horus_conda_env/bin/python scripts/models.py --selftest`.
- Recipes follow upstream `showcase/anvil_lgbm-cv.yaml` (sklearn models) and
  `showcase/chemprop/anvil_recipe.yaml` (Chemprop). Upstream ships no rf,
  xgboost or catboost recipe. Those use the same featurization (RDKit 2D
  descriptors + ECFP4), split and CV as lgbm, with library-default
  hyperparameters except the tree count.
- `openadmet anvil` renames an `--output-dir` that already exists, so each
  clone trains into a fresh `model/` subfolder of its slot.
- anvil prints many sklearn warnings. They go to `trained/<slot>/anvil.log`,
  and the task log shows only the tail, or the last 40 lines on failure.
- `openadmet compare` needs its `--output-dir` to exist; `models.py` creates it.

## Open Questions

- The full profile has not been run on a GPU cluster.
- A `horus_map` runs every clone on one target, so the CPU tree models
  cannot stay on CPU nodes while Chemprop goes to a GPU. Splitting the map
  into a CPU map and a GPU map would fix that at the cost of a second recipe
  folder.

## License and credit

The workflow glue in this folder is MIT (repo license). It reproduces the
OpenADMET Showcase from
[OpenADMET/openadmet-demos](https://github.com/OpenADMET/openadmet-demos)
(Apache-2.0) and runs
[openadmet-models](https://github.com/OpenADMET/openadmet-models) (Apache-2.0)
on data from [OpenADMET/data-catalogs](https://github.com/OpenADMET/data-catalogs)
(Apache-2.0; derived from ChEMBL 35, CC BY-SA 3.0). Recipes generated by
`make_recipes.py` are derived from the upstream showcase recipes and carry an
Apache-2.0 credit header. Credit for the science, models and data goes to the
OpenADMET contributors.

## References

- OMSF workflow directory: https://directory.omsf.io/workflows/
- OpenADMET demos: https://demos.openadmet.org · https://github.com/OpenADMET/openadmet-demos
- openadmet-models: https://github.com/OpenADMET/openadmet-models
- Model comparison guidelines followed by `openadmet compare`: https://chemrxiv.org/engage/chemrxiv/article-details/672a91bd7be152b1d01a926b
