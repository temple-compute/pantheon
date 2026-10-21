# W-07 · Programmatic Dynamic DAG Showcase

A task that reads its data and grows the rest of the DAG while it runs: one processing task per group it finds, plus a fan-in.

![Domain: Engine Showcases](https://img.shields.io/badge/domain-engine--showcases-orange)

## Overview

Shows runtime DAG mutation in horus-runtime. The `plan` task reads a JSON dataset, finds its distinct groups and, from inside its own function, adds one `process_<group>` task per group (`workflow.add_task`) plus a `combine` fan-in task with its edges (`workflow.expand`). Unlike a `horus_map` ([W-06](../w01-fanout-map-gather/README.md)), the fan-out is decided by the task. The DAG is built in Python (`run.py`), with no `workflow.yaml`. It starts with 1 task (`plan`) and grows to 5 for the bundled dataset (3 groups).

## Pipeline

```
plan                reads dataset, adds tasks at runtime
process_<group>     one per group ──► results/<group>.json
combine             results/*.json ──► results/combined.json
```

## Inputs / Outputs

- Input: `examples/dataset.json`, 6 records `{"group", "n"}` in 3 groups (`alpha` 2, `beta` 3, `gamma` 1).
- `results/<group>.json`: `{"group", "count", "sum", "values"}`.
- `results/combined.json`: `{"total_count": 6, "total_sum": 30, "per_group": {...}}` for the bundled dataset.

## Parameters

- `examples/dataset.json`: add or remove records or groups; the number of generated tasks follows.
