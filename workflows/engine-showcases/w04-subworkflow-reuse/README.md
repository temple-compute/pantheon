# W-27 · Subworkflow Reuse Showcase

![Domain: Engine Showcases](https://img.shields.io/badge/domain-engine--showcases-orange)

## Overview

A minimal demonstration of horus-runtime's **subworkflow** construct: a
`sub:` block carries a complete child workflow, which gets inlined into the
parent's DAG when the workflow runs. There's no binding table to keep in
sync — the subworkflow's inputs and outputs are *derived* straight from the
child: the in-port is whatever root artifact the child reads, the out-port
is whatever task output nothing inside the child consumes.

This showcase leans on that to demonstrate **reuse**: a two-stage
`trim -> shout` cleaning pipeline is written **once**, as a YAML anchor, and
instantiated **twice** (`clean_a`, `clean_b`) via a YAML alias — a stdlib
YAML feature, no custom tooling. Each instance runs against a different
input and its inner tasks are inlined under a different prefix
(`clean_a/trim` vs `clean_b/trim`), so the two clones of the identical body
never collide.

## Pipeline

```
split (local)              examples/quotes.txt (2 lines) ──► quote_a.txt, quote_b.txt

clean_a (subworkflow)      clean_b (subworkflow)
   │  trim -> shout            │  trim -> shout
   │  (same body, inlined      │  (same body, inlined
   │   as clean_a/trim,        │   as clean_b/trim,
   │   clean_a/shout)          │   clean_b/shout)
   ──► clean.txt               ──► clean.txt

combine (local)             clean_a/clean.txt + clean_b/clean.txt ──► results/report.txt
   │  concatenates both cleaned quotes
```

## Quick start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

cd workflows/engine-showcases/w04-subworkflow-reuse
uv sync
# or: pip install horus-runtime

horus run workflow.yaml
```

Outputs land in `horus_workflow_results/`: `quote_a.txt`/`quote_b.txt`,
each `clean_<x>/clean.txt` (the inlined subworkflow's inner working
directory), and `results/report.txt`.

## Inputs / Outputs

**Input** — `examples/quotes.txt`: two lines of text.

**Outputs**
- `clean_a/clean.txt`, `clean_b/clean.txt` — each input line, trimmed then
  uppercased.
- `results/report.txt` — both cleaned lines, one per line.

## Parameterization

- `examples/quotes.txt` — swap in your own two lines.
- The `clean_pipeline` body (`workflow.yaml`) — change what `trim`/`shout`
  do (or add a stage) and both `clean_a` and `clean_b` pick it up, since
  they share the one YAML-anchored body.

## Implementation notes

- `clean_a`'s `sub:` value is tagged `&clean_pipeline`; `clean_b`'s `sub:`
  value is `*clean_pipeline`, a plain YAML alias. The loader sees two
  independent (but structurally identical) `sub:` blocks — reuse happens at
  the YAML-parsing level, before horus-runtime is involved at all.
- The child body is a normal `BaseWorkflow` document: a root `artifacts:`
  entry (`text`) is the in-port, and `shout`'s `clean` output is the
  out-port since no inner edge consumes it. Ports are never declared
  explicitly on the subworkflow task itself — see
  `horus_builtin/workflow/subworkflow/ports.py` in horus-runtime for the
  derivation rule this relies on.
- Both instances' inner tasks are inlined at `<subworkflow id>/<inner id>`
  (`clean_a/trim`, `clean_b/trim`, ...), which is why the same body can be
  reused verbatim without id or path collisions.
