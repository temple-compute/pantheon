# W-49 · nf-core/rnaseq (native port)

RNA-seq QC, alignment and quantification: a native port of nf-core/rnaseq 3.27.0.

![Domain: nf-core ports](https://img.shields.io/badge/domain-nf--core--ports-green)

## Overview

Runs the route `nextflow run nf-core/rnaseq -r 3.27.0 -profile test,docker` takes, as Horus tasks with the same containers, rendered command lines and per-process cpus/memory: TrimGalore, BBSplit, STAR with Salmon (`star_salmon`), Salmon pseudo-alignment, Picard MarkDuplicates, StringTie, featureCounts biotypes, Qualimap, dupRadar, RSeQC, bigWigs and MultiQC. Per-sample steps are `horus_map` stages over a list of sample meta files. The pipeline's Groovy logic runs as small decision tasks: the minimum trimmed reads filter, `auto` strandedness from a Salmon subsample, the minimum mapped reads filter and the MultiQC sample renaming, so other samplesheets and references work too. The workflow has 71 tasks (45 maps).

## Variants

Other entry points next to `workflow.yaml`. Each file's header says how it was generated.

- `workflow.tuned.yaml` (54 tasks, 28 maps): per-sample steps that share an image run as one task, with the same outputs.
- `workflow.chained.yaml`: per-sample maps set `chain: true`, so a sample moves to its next step without waiting for the others, with the same outputs.
- `workflow.unrolled.yaml`: the chained DAG with every map unrolled into one task per sample of the example samplesheet (263 tasks), for timing against chaining.
- `workflow.rightsized.yaml`: per-task resources from a measured run, on managed nodes per size class.
- `workflow.real.yaml`, `workflow.real.deep.yaml`, `workflow.real.fast.yaml`: the chained port on a Slurm cluster with Apptainer, given references and prebuilt STAR and Salmon indexes, and no BBSplit (`scripts/gen_real.py`). The deep and fast files set the input `cache:` mode. `workflow.real.rightsized.yaml` sets each task's resources from a measured real-data run.

`chain: true` and `cache:` need horus-runtime 0.9.0 or later, so the chained and real variants do too.

## Pipeline

```
fetch_reference / stage_samples   URLs or a local mirror ──► work/reference/, work/reads/<id>/, work/samples/<id>
genome prep (single tasks)        GUNZIP, CUSTOM_GTFFILTER, CUSTOM_CATADDITIONALFASTA, SAMTOOLS_FAIDX, GTF2BED, UNTAR_SALMON_INDEX, BBSplit and STAR indices
cat_fastq[*]                      runs of one sample ──► <id>_1.merged.fastq.gz
lint_raw, fastqc_raw, trimgalore  per sample ──► results/fq_lint/raw/, results/fastqc/raw/, results/trimgalore/
filter_trimmed                    min_trimmed_reads ──► work/lists/trim_pass/, work/lists/auto_strand/
lint_trimmed, bbsplit, lint_bbsplit, fastqc_filtered   per passing sample
subsample, salmon_strand, set_strandedness             auto samples ──► forward / reverse / unstranded
star_align, salmon_bam, salmon_quant                   ──► results/star_salmon/, results/salmon/
sort + index + flagstat/idxstats/stats, filter_mapped  min_mapped_reads ──► work/lists/map_pass/
markdup, stringtie, featurecounts, biotype, qualimap, dupradar, rseqc (7), bigWig (cov, clip, bigWig x3)
tx2gene, tximport, SE gene/transcript, DESeq2 QC       once per route ──► salmon.merged.*.tsv
mqc_inputs, multiqc               ──► results/multiqc/star_salmon/multiqc_report.html
```

## Inputs / Outputs

- Input: `examples/samplesheet.csv`, the test profile samplesheet (`sample,fastq_1,fastq_2,strandedness`, 7 runs of 5 samples, reads downloaded from nf-core/test-datasets). Rows sharing a sample are merged.
- Input: the reference URLs (genome, GTF, transcriptome, GFP fasta, BBSplit fasta list, prebuilt Salmon index), defaulting to the test profile's. Set `input_mirror` to a folder with local copies to skip the downloads.
- `results/star_salmon/tximport/` and `results/salmon/tximport/`: `salmon.merged.gene_counts.tsv`, TPM and transcript-level tables per route.
- `results/star_salmon/`: STAR logs, MarkDuplicates BAMs and metrics, featureCounts, StringTie, Qualimap, dupRadar, RSeQC, bigWigs, DESeq2 QC.
- `results/multiqc/star_salmon/`: the MultiQC report and its data tables.

Gene and transcript counts, featureCounts summaries, bigWigs and the MultiQC general statistics match the Nextflow run. BBSplit sometimes keeps one read pair more or less for the same input, in both engines. The MultiQC report has no software versions, workflow summary or methods sections, which nf-core builds from Nextflow run metadata.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `samplesheet` | `examples/samplesheet.csv` | Samples and their reads (`--input`) |
| `fasta_url`, `gtf_url`, `transcript_fasta_url` | test profile URLs | Genome, annotation and transcriptome (`--fasta`, `--gtf`, `--transcript_fasta`) |
| `additional_fasta_url` | `gfp.fa.gz` | Extra sequences added to the genome (`--additional_fasta`) |
| `bbsplit_fasta_list_url` | test profile list | Genomes to remove with BBSplit (`--bbsplit_fasta_list`) |
| `salmon_index_url` | `salmon_2.7.0.tar.gz` | Prebuilt Salmon index (`--salmon_index`) |
| `input_mirror` | empty | Folder searched by file name before downloading |
| `min_trimmed_reads` | `10000` | Drop samples with fewer reads after trimming |
| `min_mapped_reads` | `5` | Drop BAMs under this STAR uniquely mapped % |
| `stranded_threshold`, `unstranded_threshold` | `0.8`, `0.1` | Strandedness calls for `auto` samples |

## References

- nf-core/rnaseq: https://nf-co.re/rnaseq/3.27.0 and https://github.com/nf-core/rnaseq (MIT; module templates and assets in `nfcore/`)
- STAR: Dobin et al. (2013), Bioinformatics 29(1):15, https://doi.org/10.1093/bioinformatics/bts635
- Salmon: Patro et al. (2017), Nat Methods 14:417, https://doi.org/10.1038/nmeth.4197
- RSeQC: Wang et al. (2012), Bioinformatics 28(16):2184, https://doi.org/10.1093/bioinformatics/bts356
- MultiQC: Ewels et al. (2016), Bioinformatics 32(19):3047, https://doi.org/10.1093/bioinformatics/btw354
- nf-core: Ewels et al. (2020), Nat Biotechnol 38:276, https://doi.org/10.1038/s41587-020-0439-x
