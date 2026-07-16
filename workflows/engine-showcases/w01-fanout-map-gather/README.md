# W-06 · Fan-out / Map / Gather Showcase

![Domain: Engine Showcases](https://img.shields.io/badge/domain-engine--showcases-orange)

## Overview

A minimal, portable demonstration of horus-runtime's declarative `map:`
construct: a producer task splits a small input collection into batches, a
`map:` block fans a stage out over every batch **concurrently**, and a gather
stage collects the N results back into a single folder. There's no science
here (no conda envs, no domain data) — every task shells out to `echo`/`wc`/`tr`
or a stdlib-only script, so the whole thing runs anywhere in a few seconds and
is meant to be read as a template for wiring up map/fan-out/fan-in on a real
pipeline (e.g. batching a ligand library the way W-01/W-02 do, but with the
new engine-level fan-out instead of a single serial stage).

## Pipeline

```
split (local)             examples/items.json (8 strings) ──► batches/ (4 files)
   │  chunks the JSON list into batch_0..batch_3.txt, 2 items each

score[00..03] (map, 4x concurrent clones over batches/)
   │  each clone: word-counts + uppercases its one batch file
   │  ──► scored/count.txt, scored/upper.txt   (fan-in target: score.gathered/<i>/)

gather (local)             score.gathered/ (4 subfolders) ──► results/summary/
   │  sums the per-batch word counts, concatenates the uppercased text
```

## Quick start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

cd workflows/engine-showcases/w01-fanout-map-gather
uv sync
# or: pip install horus-runtime

horus run workflow.yaml
```

Outputs land in `workflow_results/`: `batches/` (4 files), `score.gathered/`
(4 subfolders, one per clone), and `results/summary/summary.json` +
`results/summary/combined_upper.txt`.

## Inputs / Outputs

**Input** — `examples/items.json`: a JSON array of 8 short strings.

**Outputs**
- `score.gathered/<i>/scored/count.txt` — word count for batch `<i>` (1 per
  clone, always `2` for the bundled example: 2 items/batch, 1 word each).
- `score.gathered/<i>/scored/upper.txt` — the batch's text, uppercased.
- `results/summary/summary.json` — `{"total_words": 8, "batches": [...]}` for
  the bundled example (4 batches × 2 words).
- `results/summary/combined_upper.txt` — every batch's uppercased text,
  concatenated in batch order.

## Parameterization

- `examples/items.json` — swap in your own JSON array of items.
- `split` task's `--batch-size` arg (`workflow.yaml`) — items per batch; the
  number of batches this produces is the number of concurrent `score` clones
  the `map:` block creates.