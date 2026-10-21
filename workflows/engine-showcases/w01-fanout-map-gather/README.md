# W-06 · Fan-out / Map / Gather Showcase

Split a list into batches, score every batch concurrently with one `horus_map`, gather the results back into one summary.

![Domain: Engine Showcases](https://img.shields.io/badge/domain-engine--showcases-orange)

## Overview

Shows horus-runtime's `horus_map`: `split` chunks a JSON list into batch folders, `score` fans out one clone per batch (word count and uppercase), and `gather` reads the map's single folder output and merges the results. The workflow has 3 tasks.

## Pipeline

```
split              items.json (8 strings) ──► batches/batch_0..batch_3/data.txt
score[0..3]        horus_map over batches/, max_concurrency 4 ──► scored/<slot>/{count,upper}.txt
gather             scored/ (4 slots) ──► results/summary/
```

## Inputs / Outputs

- Input: `examples/items.json`, a JSON array of strings.
- `scored/<slot>/count.txt`: word count of one batch (2 for the bundled example).
- `scored/<slot>/upper.txt`: the batch text, uppercased.
- `results/summary/summary.json`: `{"total_words": 8, "batches": [...]}` for the bundled example.
- `results/summary/combined_upper.txt`: all uppercased text in batch order.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `items` | `examples/items.json` | Items to batch and score |
| `batch_size` | 2 | Items per batch; the batch count is the number of `score` clones |
