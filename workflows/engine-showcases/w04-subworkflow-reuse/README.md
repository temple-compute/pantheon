# W-27 · Subworkflow Reuse Showcase

One trim-then-shout child workflow written once and reused twice through a YAML anchor, each instance on its own quote.

![Domain: Engine Showcases](https://img.shields.io/badge/domain-engine--showcases-orange)

## Overview

Shows horus-runtime subworkflows and reuse: a two-stage `trim -> shout` child workflow is written once as a YAML anchor and instantiated twice (`clean_a`, `clean_b`) through a YAML alias, each on its own quote. The subworkflow ports are derived from the child: the in-port is its root artifact and the out-port is the task output nothing inside consumes. Inner tasks are inlined under a prefix (`clean_a/trim`, `clean_b/trim`), so the clones do not collide. The workflow has 4 tasks (`split`, `clean_a`, `clean_b`, `combine`).

## Pipeline

```
split        examples/quotes.txt (2 lines) ──► quote_a.txt, quote_b.txt
clean_a      subworkflow: trim -> shout ──► clean_a.txt
clean_b      same body via alias ──► clean_b.txt
combine      clean_a.txt + clean_b.txt ──► results/report.txt
```

## Inputs / Outputs

- Input: `examples/quotes.txt`, two lines of text.
- `clean_a.txt`, `clean_b.txt`: each line trimmed and uppercased.
- `results/report.txt`: both cleaned lines.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `quotes` | `examples/quotes.txt` | One quote per line; each goes through its own subworkflow instance |
