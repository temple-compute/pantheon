# W-08 · Bounded Loop (Range Map) Showcase

![Domain: Engine Showcases](https://img.shields.io/badge/domain-engine--showcases-orange)

> Requires horus-runtime ≥ the Dynamic-workflows features (milestone: fan-out/map/loops).

## Overview

A minimal, deterministic demonstration of horus-runtime's **bounded loop**:
the same declarative `map:` construct as W-06, but with `range: N` instead of
an upstream collection — N clones, indices `0..N-1`, no producer task
required. Each clone squares its own iteration index; a gather stage sums
them. This is the "run this exact number of times" loop primitive (as
opposed to the milestone's other loop form, a conditional-repeat
`LoopController` that keeps injecting the next iteration until a predicate
says stop — see Implementation notes).

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

## Implementation notes

- `map.range` (no `over:`) is what makes this a **bounded** loop instead of a
  data-driven fan-out (W-06 uses `over:` to fan out over an upstream
  collection instead). `index_input: idx` names the template input artifact
  that each clone's 0-based iteration index is written into — the clone's
  command reads it from `$idx` and squares it.
- The milestone also defines a second loop form not shown here: a
  **conditional-repeat** `LoopController{predicate, body_template,
  max_iterations}` (horus-runtime #116) that injects the next iteration only
  if a predicate over the previous iteration's output says to continue,
  capped by `max_iterations` — a `while`-style loop rather than a fixed
  `for`-style one. It's a registered task like `MapExpander`, reachable from
  both YAML and the Python builder, but its exact YAML keyword wasn't
  settled as of writing, so this showcase sticks to the better-grounded
  `range:` form. `max_iterations` is the safety bound that keeps a
  conditional loop from growing the DAG unboundedly.
- `scripts/sum_squares.py` is stdlib-only and has a `--selftest`
  (`python scripts/sum_squares.py --selftest`).
- The exact `map:` field names here (`range`, `index_input`, `gather.task`,
  `gather.input`) reflect the `MapOver`/`MapExpander` design in horus-runtime
  issues #113–#116 as of writing; double-check against the released schema
  if it has since shifted.

## References

- horus-runtime milestone: [Dynamic workflows: fan-out / map / loops](https://github.com/temple-compute/horus-runtime/milestone/6)
- horus-runtime #116 — Loops: bounded range map + LoopController
- horus-runtime #115 — Declarative map / fan-out / fan-in (MapExpander)
