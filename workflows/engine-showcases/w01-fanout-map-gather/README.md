# W-06 · Fan-out / Map / Gather Showcase

<img src="assets/logo.png" width="96" align="right" alt="W-06 logo">

Split a list into batches, score every batch concurrently with one `horus_map`, gather the results back into one summary.

![Domain: Engine Showcases](https://img.shields.io/badge/domain-engine--showcases-orange)

![W-06 cover](assets/cover.png)

## Overview

A minimal, portable demonstration of horus-runtime's `horus_map` task: a producer
task splits a small input collection into batch folders, a `horus_map` fans a stage
out over every batch **concurrently**, and a gather stage reads the N results back
from the map's single folder output. There's no science here (no conda envs, no
domain data) — every task shells out to `wc`/`tr` or a stdlib-only script, so the
whole thing runs anywhere in a few seconds and is meant to be read as a template for
wiring up fan-out/fan-in on a real pipeline (e.g. batching a ligand library the way
W-01/W-02 do).

## Pipeline

```
split (local)             items.json (8 strings) ──► batches/batch_0..batch_3/data.txt
   │  chunks the JSON list into batch_size items per batch folder

score[0..3] (horus_map over batches/, max_concurrency 4)
   │  each clone: word-counts + uppercases its one batch
   │  ──► scored/<slot>/count.txt, scored/<slot>/upper.txt

gather (local)             scored/ (4 slots) ──► results/summary/
   │  sums the per-batch word counts, concatenates the uppercased text
```

## Quick start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

cd workflows/engine-showcases/w01-fanout-map-gather
uv sync
# or: pip install horus-runtime

uv run horus run workflow.yaml
```

Outputs land in `horus_workflow_results/`: `batches/` (4 folders), `scored/`
(4 slots, one per clone), and `results/summary/summary.json` +
`results/summary/combined_upper.txt`.

## Inputs / Outputs

**Outputs**
- `scored/<slot>/count.txt` — word count for one batch (always `2` for the
  bundled example: 2 items/batch, 1 word each).
- `scored/<slot>/upper.txt` — the batch's text, uppercased.
- `results/summary/summary.json` — `{"total_words": 8, "batches": [...]}` for
  the bundled example (4 batches × 2 words).
- `results/summary/combined_upper.txt` — every batch's uppercased text,
  concatenated in batch order.

## Parameterization

| id | Kind | Default | Range | Meaning |
|---|---|---|---|---|
| `items` | file | `examples/items.json` | JSON array of strings | Items to batch and score |
| `batch_size` | number | 2 | 1–20, step 1 | Items per batch; the number of batches is the number of concurrent `score` clones |

To change a value locally, edit its `value:` in `workflow.yaml`, then `rm -rf params/`:
Horus writes `params/<id>.txt` only when it is missing. `max_concurrency` on `score`
caps how many clones run at once.

## Running in Temple Compute

Start a campaign from the library: upload a JSON array of strings (or keep the
example) and pick the batch size. Each `score` clone carries a deliberately generous
`resources` hint (4 CPU / 8 GB / 5 min): every clone inherits it, so the tc-os
resources dashboard shows the gap between asked and used multiplied by the fan-out
width, which is what right-sizing recovers.
