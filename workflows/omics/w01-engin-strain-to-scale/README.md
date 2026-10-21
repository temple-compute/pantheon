# W-42 · Engin Strain-to-Scale

One Engin project file in; which host, which route and which runs to do next, each with a 90% band, merged into one decision brief.

![Domain: Omics](https://img.shields.io/badge/domain-omics-blue)

## Overview

Engin answers three questions for early bioprocess development, each with a calibrated 90% band: which host (`engin-host`), which route (`engin-pathway`) and what to run next (`engin-process`). The three stages read the same `project.yaml` and are independent, so they run in parallel and a `summary` task merges them into one decision brief that keeps every interval and caveat. Engin intervals land near nominal 90% coverage on 406 real fermentation batches, but its point predictions are weak (R² ≈ 0.02-0.11). The workflow has 4 tasks.

## Pipeline

```
                    project.yaml
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
    host (chassis)   pathway (route)   process (next runs)
          └────────────────┼────────────────┘
                           ▼
                  summary (results/summary.{json,md})
```

## Inputs / Outputs

- Input: `examples/project.yaml`, read by all three stages. Every section is optional.
- `results/host.{json,txt}`: ranked host organisms with recommendation and 90% band.
- `results/pathway.{json,txt}`: ranked biosynthetic routes with manufacturability intervals.
- `results/process.{json,txt}`: current best cost and next runs ranked by expected cost reduction.
- `results/summary.{json,md}`: merged decision brief.
- `examples/expected-output/`: captured reference run (`seed: 0`) of the three stages.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `project` | `examples/project.yaml` | Engin project file read by all three stages |

Settings live in the project file: `host.weights` / `host.hard`, `pathway.routes`, `process.reactor`, `process.cost` (default target $200/kg), `process.batch_size` (4) and `seed` (0).

## References

- [Engin suite (GitHub)](https://github.com/enginbio/engin-suite)
- [Engin docs](https://docs.engin.bio)
- [Engin real-data calibration](https://github.com/enginbio/engin-suite/blob/main/docs/methods/real-data-calibration.md)
- [Engin API stability](https://github.com/enginbio/engin-suite/blob/main/docs/api-stability.md)
