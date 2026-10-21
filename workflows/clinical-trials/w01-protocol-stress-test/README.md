# W-40 · Protocol Stress-Test

A public trial's eligibility criteria as computable rules on a Synthea population, with thousands of protocol variants fanned out to rank each criterion by the patients and the diversity it costs.

![Domain: Clinical Trials](https://img.shields.io/badge/domain-clinical--trials-blue)

## Overview

Turns the eligibility criteria of the public trial NCT03036150 (Dapa-CKD, sponsor AstraZeneca; not affiliated with or endorsed by the sponsor) into computable rules, applies them to a [Synthea](https://github.com/synthetichealth/synthea) v4.0.0 synthetic population and evaluates thousands of protocol variants in parallel, with each criterion removed or its threshold swept. Criteria are ranked by the eligible patients and demographic diversity (Gini-Simpson over race/ethnicity) each one costs. The metric is a screen-failure proxy, 1 - eligible / prescreened, where prescreened means alive adults with an active CKD diagnosis. Results are synthetic and are not clinical evidence. The workflow has 8 tasks.

## Pipeline

```
configure
parse_criteria   (optional LLM draft + diff vs reviewed rules) ─────────────────────────┐
plan_shards ──> generate_population  [horus_map, one Synthea JVM per shard]             │
                      └──> build_features ──┐                                           │
generate_variants ──────────────────────────┴──> evaluate [horus_map, one clone per batch] ──> gather_report
```

## Inputs / Outputs

- `examples/protocol/NCT03036150.json`: ClinicalTrials.gov API v2 record (never fetched at runtime).
- `examples/criteria.reviewed.json`: reviewed rules with SNOMED CT / LOINC / RxNorm codes, prescreen and sweep grids.
- `examples/config.json`: index date, population size, shards, seed, batch size, LLM model.
- `results/report.html`: headline, per-criterion costs, threshold sweeps, Pareto frontier, LLM diff, data coverage, provenance.
- `results/hero.png`, `results/summary.json`, `results/provenance.json`.
- `results/variants.csv`: one row per variant with eligible count, screen-failure proxy, composition, diversity, per-criterion fail counts.
- `results/features.parquet`, `results/prescreen.json`, `results/criteria_draft.json`, `results/criteria_diff.json` (`status: skipped` without an API key).

## Parameters

| id | Default | Meaning |
|---|---|---|
| `protocol` | `examples/protocol/NCT03036150.json` | Trial record (eligibility text) |
| `rules` | `examples/criteria.reviewed.json` | Reviewed computable criteria and sweep grids |
| `config` | `examples/config.json` | Advanced settings: age range, Synthea modules, JVM heap, `synthea_csv`, `variants.random_seed` |
| `population_size` | 5000 | Synthetic patients to generate |
| `population_shards` | 4 | Parallel Synthea runs, one map clone each |
| `population_seed` | 42 | Seed of shard 0; shard i uses seed + i |
| `state` | `Massachusetts` | US state for Synthea demographics |
| `index_date` | `2026-01-01` | Date eligibility is evaluated at |
| `variant_batch_size` | 50 | Variants per `evaluate` clone |
| `random_combinations` | 0 | Extra random multi-criterion variants |
| `llm_model` | `claude-opus-5-5` | Model for the optional rule draft (runs only with `ANTHROPIC_API_KEY`) |

## References

- Liu R, Rizzo S, Whipple S, et al. Evaluating eligibility criteria of oncology trials using real-world data and AI (Trial Pathfinder). *Nature* 592, 629–633 (2021). doi:[10.1038/s41586-021-03430-5](https://doi.org/10.1038/s41586-021-03430-5)
- Walonoski J, Kramer M, Nichols J, et al. Synthea: An approach, method, and software mechanism for generating synthetic patients and the synthetic electronic health care record. *JAMIA* 25(3), 230–238 (2018). <https://github.com/synthetichealth/synthea>
- ClinicalTrials.gov API v2, U.S. National Library of Medicine. <https://clinicaltrials.gov/data-api/api>. Record NCT03036150.
- Inker LA, Eneanya ND, Coresh J, et al. New creatinine- and cystatin C-based equations to estimate GFR without race. *N Engl J Med* 385, 1737–1749 (2021). (CKD-EPI 2021, used for the `egfr_ckdepi` sensitivity column.)
