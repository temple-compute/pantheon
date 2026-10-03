# W-35 · Influenza Segments Starter

![Domain: Bioinformatics](https://img.shields.io/badge/domain-bioinformatics-teal)

## Overview

A small, fully local starter that shows what a familiar bioinformatics job looks
like in Horus: influenza segment FASTA in, per-segment QC, longest-ORF protein
translation and an HTML summary report out. It follows the first stages of
typical influenza genotyping pipelines (header parsing, QC, CDS translation,
report) but is an independent, from-scratch reimplementation of the ideas, not a
port of any of them. It runs in about a second on a laptop: no Docker, conda,
Slurm or network at runtime. Mutation calling and subtyping are deliberately out
of scope (see *What to try next*).

## What it demonstrates (in reading order of `workflow.yaml`)

1. **Artifacts and edges** – typed inputs/outputs (`file`, `folder`) wired into a DAG with `edges:`; workflow inputs are `artifact-<id>`.
2. **Shell executor vs uv environment executor** – tasks 1, 2, 4 run stdlib-only scripts with the host `python3`; task 3 gets a Biopython venv built by Horus.
3. **Parameters via `args`** – QC thresholds (`--max-n-frac`) are plain flags in the task's `runtime.args`.
4. **Re-runs** – every task sets `skip_if_complete: false`, so a re-run recomputes and overwrites `results/`. Set it to `true` on a task to skip it when its outputs already exist (note: a changed `args` value will then *not* trigger a re-run).
5. **Fan-out / gather** – not used here; see *Scaling out per sample*.

## Compute Pattern

| Task | Executor | Needs | Walltime |
|---|---|---|---|
| `organize_by_sample` | shell | stdlib | < 1 s |
| `qc_segments` | shell | stdlib | < 1 s |
| `translate_cds` | uv_python_environment | `biopython` | < 1 s (+ one-off venv build) |
| `summary_report` | shell | stdlib | < 1 s |

```
fasta ─► organize_by_sample ─┬─► qc_segments ─┬─► translate_cds ─┐
                             │                │                  ▼
                             └────────────────┴────────────► summary_report ◄─ metadata
```

## Tools & Dependencies

Python ≥ 3.13 and `uv` on the host; `horus-runtime`, `horus-environments` (via `uv sync`); Biopython (installed by Horus into the task venv, needs network once).

## Horus Configuration

Everything uses `target: {kind: local}`. Orchestrator working directory: `horus_workflow_results/`.

## Quick start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

cd workflows/bioinformatics/w01-flu-segments-starter
uv sync
uv run horus run workflow.yaml
```

Run all script self-tests (no input files needed):

```bash
for s in organize_by_sample qc_segments summary_report; do python3 scripts/$s.py --selftest; done
uv run --with biopython python scripts/translate_cds.py --selftest
```

## Input / Output

| | File | Description |
|---|---|---|
| in | `examples/segments.fasta` | Segment FASTA; headers `>Sample01_HA_2024_Spain` or `>Sample01\|NA\|x` (sample, segment first) |
| in | `examples/metadata.csv` | Optional, synthetic; `ID,DATE,LOCATION,AGE GROUP,SEX,ORIGINATING LAB`, merged by `ID` |
| out | `results/segments.csv` | sample, segment, length, header |
| out | `results/samples/<sample>.fasta` | per-sample FASTA, headers normalised to `sample\|segment` |
| out | `results/qc.csv` | per segment PASS/FAIL + reason |
| out | `results/proteins.faa`, `results/proteins.csv` | longest ORF per QC-passing segment (aa length, start, stop codon) |
| out | `results/report.html` | sample × segment grid, PASS/FAIL colouring, protein lengths, error count |
| out | `results/errors.log` | malformed/duplicate headers (run never aborts) |

Outputs are deterministic (sorted rows). The bundled example has two QC failures (Sample03 HA: ~7 % N; Sample03 NA: truncated) and one malformed header (`>Sample03`), so the error path is visible. Outputs land under `horus_workflow_results/results/`.

## Parameterization

- `qc_segments --max-n-frac` (default `0.01`), `--len-tolerance` (widens each range; default `0`). The per-segment length table is the `RANGES` dict in `scripts/qc_segments.py`: approximate influenza A values; edit for your data.
- The multiple-of-3 check applies to single-ORF segments (PB2, PB1, PA, HA, NP, NA); MP and NS are spliced/UTR-bearing and skipped.
- Drop `--metadata ${metadata}` from `summary_report` to skip the metadata merge.

## Mapping to a real pipeline

| Task here | Corresponding stage (e.g. FluTyper, conceptually) |
|---|---|
| `organize_by_sample` | OrganizeBySample; `errors.log` ~ `pipeline_errors.log` |
| `qc_segments` | input validation before translation |
| `translate_cds` | GetCDS + TranslateToProtein |
| `summary_report` | report generation + MetadataMerge |
| *(not included)* | SubtypeDetection / Genotyping (Nextclade, genin2), MutationsFinder |

## Scaling out per sample

Not included in v1. `map:` fans out over a folder of items with a single template task (see `engine-showcases/w01-fanout-map-gather`), so a per-sample variant needs `qc_segments` + `translate_cds` merged into one template task, with `summary_report` as the gather target. Suggested follow-up.

## Implementation Notes

- With the uv environment executor do **not** set `python:` in the runtime; the default routes through the venv.
- ORF search is forward-strand, 3 frames, ATG-initiated. Partial CDS without a stop are reported with `stop_codon=no`.
- Example data are real NCBI records (see `examples/SOURCES.md`); two segments are derived QC fixtures.

## What to try next

- Change `--max-n-frac` to `0.1` and re-run: Sample03 HA now passes.
- Append a record with a bad header to `examples/segments.fasta`: it lands in `errors.log`.
- Add a sample and a row in `metadata.csv`.
- Set `skip_if_complete: true` on a task and re-run.
- Add a subtype step (e.g. Nextclade) as a conda/Docker task, then a mutation finder against a licensed marker set.
- Implement the per-sample fan-out variant.

## Open Questions

- Fan-out variant: follow-up PR or part of v1?
- Whether to mention the originating clinical collaboration in this README (currently neutral).

## References

- Inspired by the stage layout of [FluTyper](https://github.com/ValldHebron-Bioinformatics/FluTyper) (Vall d'Hebron Bioinformatics). No code, scripts, marker databases or data from that repository are reused.
- Example sequences: NCBI GenBank, see `examples/SOURCES.md`.
- License: MIT (repo license).
