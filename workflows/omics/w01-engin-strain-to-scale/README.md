# W-33 · Engin Strain-to-Scale

![Domain: Omics](https://img.shields.io/badge/domain-omics-blue)

## Overview

[Engin](https://github.com/enginbio/engin-suite) is a three-question decision
aid for early bioprocess development: given a molecule you want to make, it
answers *which host?* (`engin-host`), *which route?* (`engin-pathway`), and
*what to run next?* (`engin-process`), each with a calibrated 90% confidence
band rather than a bare number. It is a library, not a framework -- three
small CLIs that each read one `project.yaml` and print an answer.

**The three stages are independent.** Each reads `project.yaml` and answers
its own question; none consumes another's output. So this workflow is one
input artifact fanning out to three parallel tasks, not a pipeline, with a
fourth `summary` task that merges the three answers into one decision brief.

This is deliberately not an HPC workload: each stage runs in under a couple
of seconds on 1 CPU (scikit-learn / scipy, no PyTorch, no cluster). Its value
here is as the cheap upstream step that decides what an expensive downstream
run (docking, MD, screening) should even be pointed at.

Engin is early, and honest about it: measured against 406 real industrial
fermentation batches, its interval coverage lands near the nominal 90% while
its point predictions collapse to near-uselessness (R² ≈ 0.02-0.11). This
workflow's `summary` stage keeps that posture (intervals, "illustrative" /
"synthetic" / "judgement" flags) in the merged brief rather than smoothing it
away into three confident numbers -- see **How to read this** in
`summary.md`.

## Pipeline

```
                              project.yaml
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
              host (chassis)  pathway (route)  process (next runs)
              uv env: engin-  uv env: engin-   uv env: engin-host[cli]
              host[cli]       pathway[cli]     (pulls in engin-core)
                    │              │              │
                    └──────────────┼──────────────┘
                                   ▼
                          summary (shell, stdlib)
                          results/summary.{json,md}
```

`host`, `pathway` and `process` run concurrently; `summary` waits on all
three. `summary` is listed first in `workflow.yaml`'s `tasks:` even though it
depends on the other three -- see the comment there: `horus run` with no
`--trigger` defaults to `tasks[0]`, and `summary` is the only task whose
ancestors cover the whole graph, since host/pathway/process share no
task-to-task edge with each other.

## Quick start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install horus-runtime and the environments plugin
uv sync
# or: pip install horus-runtime horus-environments

# Run the workflow
uv run horus run workflow.yaml
```

All four tasks run locally; `host`, `pathway` and `process` each provision
their own `uv`-managed virtualenv per the `horus-environments` plugin, so
nothing needs to be hand-built. `summary` is stdlib-only Python, run directly
by the target's `python3`.

Outputs land in `horus_workflow_results/results/`: `host.{json,txt}`,
`pathway.{json,txt}`, `process.{json,txt}`, and `summary.{json,md}`.

## Inputs / Outputs

**Input:** `examples/project.yaml` -- one file, read by all three stages.
Every section is optional; generate a fresh commented starter with
`engin-host --init project.yaml`.

**Outputs** (all under `horus_workflow_results/results/`)
- `host.json` / `host.txt` -- ranked host organisms, `engin-host`'s
  recommendation and its 90% band.
- `pathway.json` / `pathway.txt` -- ranked biosynthetic routes with
  manufacturability intervals.
- `process.json` / `process.txt` -- current best cost and the next runs to
  try, ranked by expected cost reduction.
- `summary.json` / `summary.md` -- the three answers merged into one
  decision brief, keeping every interval and caveat.

`examples/expected-output/` bundles a captured run of the CLIs directly
against the example `project.yaml` (`seed: 0`, so `engin-pathway` and
`engin-process` are deterministic) -- a reference for the shape of the JSON
and the numbers, not a fixture this workflow diffs against (see
Implementation Notes).

## Parameterization

Everything a user would change lives in `examples/project.yaml`:

| Section | Knob | Default |
|---|---|---|
| `host.weights` / `host.hard` | capability weights and non-negotiable minimums | secretion/titer 1.0, scaleup/cost 0.7; secretion hard-min 0.40 |
| `pathway.routes` | candidate routes, each step scored 0-1 (entered by hand) | route-A (2 steps), route-B (3 steps) |
| `process.reactor` | vessel geometry and run length | 1 L → 2.5 L, 48 h, 0.2 g/L inoculum |
| `process.cost` | substrate price, vessel occupancy, downstream cost, target $/kg | target `$200/kg` |
| `process.batch_size` / `seed` | how many runs to recommend; reproducibility | 4 runs, `seed: 0` |
| `host`/`pathway`/`process` executor `requirements` | pinned Engin version | `==0.1.1` |

## Implementation Notes

**Why three parallel tasks, not a pipeline.** Nothing computed by one stage
feeds another -- see Overview. Fanning out from one artifact is both the
honest shape of the science and the fastest way to run it.

**Why `process` installs `engin-host[cli]`, not `engin-core[cli]`.**
`engin-process` ships inside `engin-core`, but only `engin-host` and
`engin-pathway` publish a `[cli]` extra (which pulls in `pyyaml` for reading
`project.yaml`); `engin-host[cli]` transitively pulls in `engin-core[cli]`,
so it is the smallest pinned requirement that gets `engin-process` a working
CLI.

**The bundled `examples/expected-output/` was captured from a development
checkout of `engin-suite`, not the published `0.1.1` wheel.** Running this
workflow against PyPI's `engin-host==0.1.1` reproduces `pathway.json` and
`process.json` numerically (to floating-point noise) and `pathway.txt` /
`process.txt` verbatim, but `host.json` / `host.txt` from the live package
omit the "EFSA QPS status" section and the per-row `capability_profile` /
`qps` fields the bundled example shows (it instead carries an `unsourced`
list). `scripts/summary.py` only reads fields present in both shapes
(`decision.*`, `ranking[0].provenance`, `ranking[0].flags`), so `summary.md`
is unaffected either way; re-pin the `host` task's requirement once a PyPI
release ships the QPS feature if you want it in the brief.

## Open questions

(Carried over from Engin's own README, which flags these rather than
resolving them.)

- **Which stages to expose first for a UI.** `engin-process` tells the most
  self-contained story (one number, a target, a plan); `engin-host` and
  `engin-pathway` need their caveats surfaced to be read correctly.
- **Real data in.** The biggest upgrade is a user supplying ≥ 40 real routes
  or real run history, at which point `engin-pathway` and `engin-process`
  stop reasoning about a synthetic world.

## References

- Engin suite -- <https://github.com/enginbio/engin-suite> · docs
  <https://docs.engin.bio>
- Real-data calibration (the honest numbers) --
  <https://github.com/enginbio/engin-suite/blob/main/docs/methods/real-data-calibration.md>
- API stability (pin exact versions pre-1.0) --
  <https://github.com/enginbio/engin-suite/blob/main/docs/api-stability.md>
