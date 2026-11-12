# W-59 · nf-core/methylseq (native port)

Bisulfite sequencing methylation calls with Bismark: a native port of nf-core/methylseq 4.2.0.

![Domain: nf-core ports](https://img.shields.io/badge/domain-nf--core--ports-green)

## Overview

Runs the route `nextflow run nf-core/methylseq -r 4.2.0 -profile test,docker` takes, as Horus tasks with the same containers, rendered command lines and per-process cpus/memory: a Bismark (bowtie2) index built from the fasta, FastQC, TrimGalore, Bismark alignment, deduplication and methylation extraction, per-sample and summary Bismark reports, samtools sort/index and MultiQC. Per-sample steps are `horus_map` stages over a list of sample meta files. The workflow has 14 tasks (8 maps).

## Variants

- `workflow.chained.yaml`: per-sample maps after TrimGalore set `chain: true`, so a sample moves to its next step without waiting for the others, with the same outputs. Needs horus-runtime 0.9.0 or later.

## Pipeline

```
fetch_reference / stage_samples   URLs or a local mirror ──► work/reference/, work/reads/<id>/, work/samples/<id>
gunzip, genome_prep               GUNZIP, BISMARK_GENOMEPREPARATION ──► work/genome/bismark_index/
fastqc, trimgalore                per sample ──► results/fastqc/, results/trimgalore/
bismark_align, dedup              per sample ──► results/bismark/alignments/, results/bismark/deduplicated/
sort, index                       per sample ──► <id>.deduplicated.sorted.bam(.bai)
extract                           per sample ──► results/bismark/methylation_calls/ (coverage, bedGraph, calls, M-bias)
report, summary                   bismark2report per sample, bismark2summary ──► results/bismark/reports/, results/bismark/summary/
multiqc                           ──► results/multiqc/bismark/multiqc_report.html
```

## Inputs / Outputs

- Input: `examples/samplesheet.csv`, the test profile samplesheet (`sample,fastq_1,fastq_2,genome`: three single-end and one paired-end sample from nf-core/test-datasets). Rows sharing a sample are concatenated in row order, as CAT_FASTQ does.
- Input: the genome fasta URL, defaulting to the test profile's `genome.fa.gz`. Set `input_mirror` to a folder with local copies to skip the downloads.
- `results/bismark/methylation_calls/`: per-context methylation calls, `.bismark.cov.gz` coverage, bedGraphs, splitting reports and M-bias tables.
- `results/bismark/sorted/`: deduplicated, sorted BAMs, with indexes in `results/bismark/sorted_index/`.
- `results/bismark/summary/` and `results/multiqc/bismark/`: the Bismark summary and the MultiQC report with its data tables.

Methylation calls, coverage, bedGraphs, BAM records, Bismark and TrimGalore reports, FastQC data and the MultiQC tables match the Nextflow run. Bismark reports name the genome folder by absolute path and print their run time, so those two lines differ. TrimGalore prints its adapter counts in random (Perl hash) order, in Nextflow too. The MultiQC report has no software versions, workflow summary or methods sections, which nf-core builds from Nextflow run metadata.

Left out: the other aligners (`bismark_hisat`, `bwameth`, `bwamem`) and the optional steps the test profile does not run (coverage2cytosine, Qualimap, Preseq, targeted sequencing, TAPS).

## Parameters

| id | Default | Meaning |
|---|---|---|
| `samplesheet` | `examples/samplesheet.csv` | Samples and their reads (`--input`) |
| `fasta_url` | test profile `genome.fa.gz` | Genome fasta, gzipped or plain (`--fasta`) |
| `input_mirror` | empty | Folder searched by file name before downloading |
| `multiqc_config` | `nfcore/assets/multiqc_config.yml` | The pipeline's MultiQC config |

## References

- nf-core/methylseq: https://nf-co.re/methylseq/4.2.0 and https://github.com/nf-core/methylseq (MIT; `nfcore/`)
- Bismark: Krueger and Andrews (2011), Bioinformatics 27(11):1571, https://doi.org/10.1093/bioinformatics/btr167
- Trim Galore: https://github.com/FelixKrueger/TrimGalore
- FastQC: https://www.bioinformatics.babraham.ac.uk/projects/fastqc/
- SAMtools: Danecek et al. (2021), GigaScience 10(2):giab008, https://doi.org/10.1093/gigascience/giab008
- MultiQC: Ewels et al. (2016), Bioinformatics 32(19):3047, https://doi.org/10.1093/bioinformatics/btw354
- nf-core: Ewels et al. (2020), Nat Biotechnol 38:276, https://doi.org/10.1038/s41587-020-0439-x
