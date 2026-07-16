# W-08 · Bounded Loop (Range Map) Showcase

![Domain: Engine Showcases](https://img.shields.io/badge/domain-engine--showcases-orange)

## Overview

A minimal, deterministic demonstration of horus-runtime's **bounded loop**:
the same declarative `map:` construct as W-06, but with `range: N` instead of
an upstream collection — N clones, indices `0..N-1`, no producer task
required. Each clone squares its own iteration index; a gather stage sums
them.

## Pipeline

```
iterate[00..04] (map, range: 5, 5x concurrent clones, no upstream collection)
   │  each clone: reads its own iteration index, squares it
   │  ──► square.txt   (fan-in target: iterate.gathered/<i>/)

gather (local)              iterate.gathered/ (5 subfolders) ──► results/total.txt
   │  sums every clone's square.txt: 0² + 1² + 2² + 3² + 4² = 30
```

## Quick start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

cd workflows/engine-showcases/w03-loop-map
uv sync
# or: pip install horus-runtime

horus run workflow.yaml
```

Outputs land in `horus_workflow_results/`: `iterate.gathered/` (5 subfolders,
one per clone) and `results/total.txt`, which is `30` for the bundled example.

## Inputs / Outputs

**Input** — none; `range: 5` in `workflow.yaml` is the only "input".

**Outputs**
- `iterate.gathered/<i>/square.txt` — `i * i` for each clone `i` in `0..4`.
- `results/total.txt` — the sum of all five squares, `30`.

## Parameterization

- `iterate` task's `map.range` (`workflow.yaml`) — number of iterations /
  clones. Changing it changes `results/total.txt` predictably: it's the sum
  of squares `0..N-1`, i.e. `(N-1) * N * (2N-1) / 6`.

