# W-58 · nf-core/taxprofiler (native port)

Metagenomic taxonomic profiling with many profilers at once: a native port of nf-core/taxprofiler 2.0.1.

![Domain: nf-core ports](https://img.shields.io/badge/domain-nf--core--ports-green)

## Overview

Runs the route `nextflow run nf-core/taxprofiler -r 2.0.1 -profile test,docker` takes, as Horus tasks with the same containers, rendered command lines and per-process cpus/memory: read QC, host removal and run merging, then Kraken2, Bracken, Centrifuge, MetaPhlAn, Kaiju, DIAMOND, ganon, KMCP, sylph, Melon and MetaCache against every database in the database sheet, Krona charts, taxpasta tables and MultiQC. The pipeline's Groovy channel logic depends only on the two sheets, so one planning task (`scripts/plan.py`) decides which runs get which preprocessing and which (sample, database) pairs each profiler gets, and writes one folder of job files per process. Every per-run, per-pair and per-group process is a `horus_map` over its folder. The workflow has 52 tasks (46 maps).

## Variants

- `workflow.chained.yaml` (`scripts/chain.py` writes it from `workflow.yaml`): every map that follows another map over the same runs or (sample, database) pairs sets `chain: true`, so an item moves to its next step without waiting for the others, with the same outputs. Needs horus-runtime 0.9.0 or later.

## Pipeline

```
plan                          samplesheet + database sheet ──► work/reads/, work/dbs/, work/jobs/<process>/
untar[*]                      .tar.gz databases ──► work/untar/
fastqc_raw[*]                 FASTQC on raw short and nanopore runs
fastp, fastqc_short, nonpareil, bbduk[*]       short runs: fastp with pair merging, FastQC, Nonpareil, BBDuk
nonpareil_curve[*], nonpareil_set, nonpareil_curvesr
bowtie2_build, bowtie2_align, samtools_index, stats_short    short-read host removal
porechop, nanoq, fastqc_long[*]                nanopore runs: porechop_abi, nanoq, FastQC
minimap2_index, minimap2_align, stats_long, samtools_view, samtools_fastq   long-read host removal
merge_runs[*]                 runs of one sample ──► <id>.merged.fastq.gz
kraken2, bracken, centrifuge, ckreport, metaphlan, kaiju, kaijutable, diamond,
ganon, ganon_report, kmcp, kmcp_profile, sylph, sylphtax, melon, metacache[*]   per (sample, database)
kreport2krona, kaiju2krona, krona[*]           Krona charts per (tool, database)
taxpasta_merge, taxpasta_standardise[*]        standardised tables per (tool, database)
bracken_combined, centrifuge_combined, kaiju_combined, kraken2_combined,
metaphlan_combined, ganon_combined, sylph_combined[*]   each tool's own merged table
multiqc                       ──► results/multiqc/multiqc_report.html
```

## Inputs / Outputs

- Input: `examples/samplesheet.csv`, the test profile samplesheet (7 runs of 6 samples: paired and single-end Illumina, Nanopore, and FASTA rows). Rows sharing a sample are merged after host removal.
- Input: `examples/databases.csv`, the test profile database sheet (`tool,db_name,db_params,db_type,db_path`, 19 databases).
- Input: the host reference and sylph taxonomy URLs, defaulting to the test profile's. Set `input_mirror` to a folder with local copies to skip the downloads.
- `results/<tool>/`: per-sample profiles, reports and logs of each profiler, and each tool's merged table.
- `results/taxpasta/`: one standardised table per tool and database.
- `results/krona/`: Krona HTML charts.
- `results/multiqc/`: the MultiQC report and its data tables.

Profiles, taxpasta tables, the tools' merged tables and the MultiQC general statistics match the Nextflow run. Some files match only up to order, in both engines: multithreaded tools (Kaiju, Centrifuge, MetaCache, bowtie2 unmapped reads) write reads in a different order, and Nextflow collects samples into the merged tables in completion order, so the columns come in a different order. DIAMOND aligns a few more or fewer reads between runs of the same input, which moves them to or from the unclassified count: Nextflow on a Horus node (blackbox run 85fa0f6c) aligned 1 more read of sample 2612 than the local Nextflow run, and the native run 0dc08bce 2 fewer of 2613 (7,813 vs 7,815). Nonpareil subsamples reads at random with no seed, so its curves and diversity values differ slightly on every run. The MultiQC report has no software versions, workflow summary or methods sections, which nf-core builds from Nextflow run metadata.

Not ported (off in the test profile): MALT and MEGAN, mOTUs, KrakenUniq (no database in the test sheet; `plan` stops on a KrakenUniq row), AdapterRemoval, Falco, PRINSEQ++, Filtlong, Porechop, PacBio FASTQ input, prebuilt host indexes and the other `--perform_*` / `--save_*` switches. Their params are fixed at the test profile's values.

Bracken, the Centrifuge kreport and the merged Kraken-style tables keep the pipeline's `errorStrategy 'ignore'`: a failed tool leaves no output and the task succeeds. Nextflow then drops that file from the downstream groups; here the Krona, taxpasta and merge tasks that list it fail on the missing file and stop the run. The test profile does not take this path.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `samplesheet` | `examples/samplesheet.csv` | Runs and their reads (`--input`) |
| `databases` | `examples/databases.csv` | Profilers and their databases (`--databases`) |
| `hostremoval_reference` | test profile `genome.fasta` | Host genome to remove (`--hostremoval_reference`) |
| `sylph_taxonomy` | test profile `test_taxonomy.tsv.gz` | sylph-tax taxonomy (`--sylph_taxonomy`) |
| `input_mirror` | empty | Folder searched by file name before downloading |

## References

- nf-core/taxprofiler: https://nf-co.re/taxprofiler/2.0.1 and https://github.com/nf-core/taxprofiler (MIT; MultiQC config in `nfcore/`)
- Stamouli et al. (2023), nf-core/taxprofiler, bioRxiv, https://doi.org/10.1101/2023.10.20.563221
- Kraken2: Wood et al. (2019), Genome Biol 20:257, https://doi.org/10.1186/s13059-019-1891-0
- MetaPhlAn 4: Blanco-Míguez et al. (2023), Nat Biotechnol 41:1633, https://doi.org/10.1038/s41587-023-01688-w
- Kaiju: Menzel et al. (2016), Nat Commun 7:11257, https://doi.org/10.1038/ncomms11257
- taxpasta: Beber et al. (2023), JOSS 8(87):5627, https://doi.org/10.21105/joss.05627
- MultiQC: Ewels et al. (2016), Bioinformatics 32(19):3047, https://doi.org/10.1093/bioinformatics/btw354
- nf-core: Ewels et al. (2020), Nat Biotechnol 38:276, https://doi.org/10.1038/s41587-020-0439-x
