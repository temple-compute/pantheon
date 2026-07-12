# W-06 · Fan-out / Map / Gather Showcase

![Domain: Engine Showcases](https://img.shields.io/badge/domain-engine--showcases-orange)

> Requires horus-runtime ≥ the Dynamic-workflows features (milestone: fan-out/map/loops).

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

## Implementation notes

- The `map:` block on the `score` task (`workflow.yaml`) is the whole showcase:
  `over` names the upstream producer (`split`) and which of its outputs to
  fan out over (`batches`, a folder — one clone per file inside it); `template`
  is the task spec cloned once per item; `gather` names the downstream task +
  input artifact id that receives the fan-in. No `edges:` entry is needed for
  `split → score → gather` — the `map:` block is itself sufficient for the
  loader to derive the fan-out/fan-in edges.
- Per-clone outputs land under `score.gathered/<i>/` (`<i>` zero-indexed in
  clone order); the `gather` task's single `folder` input reads that whole
  tree at once rather than per-clone edges — that's how N results collapse
  into 1 fan-in artifact.
- Both scripts (`scripts/split.py`, `scripts/gather_summary.py`) are stdlib-only
  and have a `--selftest` (`python scripts/split.py --selftest`).
- The exact `map:` field names here (`over.source_task`, `over.source_output`,
  `over.item_input`, `gather.task`, `gather.input`) reflect the `MapOver` /
  `MapExpander` design in horus-runtime issues #113–#115 (milestone "Dynamic
  workflows: fan-out / map / loops") as of writing; double-check against the
  released schema if it has since shifted.

## References

- horus-runtime milestone: [Dynamic workflows: fan-out / map / loops](https://github.com/temple-compute/horus-runtime/milestone/6)
- horus-runtime #115 — Declarative map / fan-out / fan-in (MapExpander)
- horus-runtime #114 — Fan-in edge model: transfer flag on WorkflowEdge
