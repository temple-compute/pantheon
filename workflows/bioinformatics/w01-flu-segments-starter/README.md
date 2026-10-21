# W-43 · Influenza Segments Starter

Influenza segment FASTA in, per-segment QC, longest-ORF protein translation and an HTML sample × segment report out.

![Domain: Bioinformatics](https://img.shields.io/badge/domain-bioinformatics-teal)

## Overview

Takes influenza segment FASTA, runs per-segment QC, translates the longest ORF of each passing segment and builds an HTML sample x segment report. Subtyping and mutation calling are out of scope. The workflow has 4 tasks.

## Pipeline

```
fasta ─► organize_by_sample ─┬─► qc_segments ─┬─► translate_cds ─┐
                             │                │                  ▼
                             └────────────────┴────────────► summary_report ◄─ metadata
```

| Task | Role |
|---|---|
| `organize_by_sample` | Parse headers, split FASTA per sample |
| `qc_segments` | PASS/FAIL per segment (N fraction, length range, multiple of 3) |
| `translate_cds` | Longest forward-strand ATG ORF per passing segment |
| `summary_report` | HTML report with optional metadata merge |

## Inputs / Outputs

| | File | Description |
|---|---|---|
| in | `examples/segments.fasta` | Segment FASTA; headers `>Sample01_HA_2024_Spain` or `>Sample01\|NA\|x` |
| in | `examples/metadata.csv` | Optional, synthetic; `ID,DATE,LOCATION,AGE GROUP,SEX,ORIGINATING LAB`, merged by `ID` |
| out | `results/segments.csv` | sample, segment, length, header |
| out | `results/samples/<sample>.fasta` | per-sample FASTA, headers `sample\|segment` |
| out | `results/qc.csv` | per-segment PASS/FAIL and reason |
| out | `results/proteins.faa`, `results/proteins.csv` | longest ORF per passing segment (aa length, start, stop codon) |
| out | `results/report.html` | sample x segment grid with PASS/FAIL, protein lengths, error count |
| out | `results/errors.log` | malformed or duplicate headers (the run never aborts) |

The example data are NCBI records (`examples/SOURCES.md`) with two QC failures (Sample03 HA, ~7 % N; Sample03 NA, truncated) and one malformed header (`>Sample03`).

## Parameters

| id | Default | Meaning |
|---|---|---|
| `fasta` | `examples/segments.fasta` | Segment sequences |
| `metadata` | `examples/metadata.csv` | Per-sample table merged into the report by `ID` |
| `max_n_frac` | 0.01 | A segment fails QC above this N/ambiguous fraction |
| `len_tolerance` | 0 | Widens each expected length range by this fraction |

## References

- Inspired by the stage layout of [FluTyper](https://github.com/ValldHebron-Bioinformatics/FluTyper) (Vall d'Hebron Bioinformatics).
- Example sequences: NCBI GenBank, see `examples/SOURCES.md`.
- License: MIT (repo license).
