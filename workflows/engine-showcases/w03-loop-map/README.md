# W-08 · Bounded Loop (Range Map) Showcase

Run N clones of one task over the indices 0..N-1 with a `horus_map`, then sum their outputs: a bounded loop in three tasks.

![Domain: Engine Showcases](https://img.shields.io/badge/domain-engine--showcases-orange)

## Overview

Shows a bounded loop in horus-runtime: `indices` writes `[0, 1, ..., N-1]` as JSON, `iterate` is a `horus_map` with one clone per index (each squares its index), and `gather` sums the squares. The workflow has 3 tasks.

## Pipeline

```
indices             iterations = N ──► indices.json
iterate[0..N-1]     horus_map over indices.json ──► squares/<slot>/square.txt
gather              squares/ ──► results/total.txt
```

## Inputs / Outputs

- `squares/<slot>/square.txt`: `i * i` for clone `i`.
- `results/total.txt`: sum of all squares (30 for N = 5).

## Parameters

| id | Default | Meaning |
|---|---|---|
| `iterations` | 5 | Number of clones (1-100); the total is `(N-1) * N * (2N-1) / 6` |
