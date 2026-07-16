# W-07 · Programmatic Dynamic DAG Showcase

![Domain: Engine Showcases](https://img.shields.io/badge/domain-engine--showcases-orange)

## Overview

A minimal demonstration of horus-runtime's runtime DAG-mutation API: a task
doesn't just consume/produce artifacts, it can **generate the rest of the DAG
while it's running**, based on data it only sees at execution time. Here,
`plan` reads a small JSON dataset, discovers how many distinct groups are in
it, and — from inside its own task function — adds one processing task per
group plus a fan-in task, none of which existed when the workflow started.
There is no science and no YAML here (this is the pure-Python builder path);
the point is the `HorusContext.get_context().workflow` / `add_task` /
`expand` pattern, which is the mechanism a real pipeline would use for e.g.
"one task per file format actually present in this upload" or "one task per
cluster returned by a discovery step" — cases the declarative `map:` block
(see W-06) can't express because the fan-out isn't over a static collection,
it's a decision the task itself makes.

## Pipeline

```
plan                       examples/dataset.json (6 records, 3 groups) ──► (no static output)
   │  reads the dataset, discovers groups {alpha, beta, gamma}, then AT RUNTIME:
   │    - adds one process_<group> task per group  (workflow.add_task, one at a time)
   │    - adds a combine task + all its fan-in edges in one call (workflow.expand)
   ▼
process_alpha  process_beta  process_gamma     (generated tasks, run after plan)
   │  each summarizes its group's records       ──► results/<group>.json
   └──────────────┬──────────────┘
                   ▼
combine                     results/alpha.json + beta.json + gamma.json ──► results/combined.json
   │  sums count/sum across every generated group task
```

## Quick start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

cd workflows/engine-showcases/w02-programmatic-dynamic-dag
uv sync
# or: pip install horus-runtime

uv run python run.py
```

`run.py` is the entrypoint (there's no `workflow.yaml` — the DAG is built and
mutated entirely in Python). Outputs land in `results/`: one
`<group>.json` per discovered group plus `combined.json`.

## Inputs / Outputs

**Input** — `examples/dataset.json`: 6 records, each `{"group": ..., "n": ...}`,
spanning 3 groups (`alpha`: 2 records, `beta`: 3, `gamma`: 1).

**Outputs**
- `results/<group>.json` — `{"group", "count", "sum", "values"}` for that group.
- `results/combined.json` — `{"total_count": 6, "total_sum": 30, "per_group": {...}}`
  for the bundled dataset (`alpha` sum 8, `beta` sum 12, `gamma` sum 10).

## Parameterization

- `examples/dataset.json` — add/remove records or groups; `plan` adapts the
  number of generated tasks to whatever groups are actually present, with no
  code changes.

## Implementation notes

- `plan` (`run.py`) is a normal `@FunctionTask.task`; the dynamic part is
  entirely inside its function body, via `HorusContext.get_context().workflow`
  — the *running* `BaseWorkflow` instance, reachable from any task's own code.
- Two mutation entry points are shown side by side: `workflow.add_task(task)`
  is called once per group (the granular "as tasks are generated" pattern —
  no edge is needed since each task is created *during* `plan`'s own
  execution, so it can only run after `plan` completes); `workflow.expand
  (tasks=[...], edges=[...])` adds the `combine` task together with all of its
  fan-in edges from the generated `process_<group>` tasks in one call.
- `combine`'s inputs (`in_<group>`, one per discovered group) aren't known
  until runtime, so its function signature uses `**kwargs` — the
  `python_function` runtime's parameter-name injection passes every declared
  input/output through when a function declares `**kwargs`.
