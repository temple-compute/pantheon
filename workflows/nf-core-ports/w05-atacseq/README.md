# W-52 · nf-core/atacseq (native port)

ATAC-seq alignment, peak calling and QC: a native port of nf-core/atacseq 2.1.2.

![Domain: nf-core ports](https://img.shields.io/badge/domain-nf--core--ports-green)

## Overview

Runs the route `nextflow run nf-core/atacseq -r 2.1.2 -profile test,docker` takes, as Horus tasks with the same containers, rendered command lines and per-process cpus/memory: FastQC and TrimGalore, BWA, Picard library and replicate merging and MarkDuplicates, BAM filtering, deepTools, MACS2 broad peaks, HOMER annotation, consensus peaks with featureCounts and DESeq2 QC, ataqv, an IGV session and MultiQC. Per-run, per-library and per-replicate steps are `horus_map` stages over lists of meta files. The pipeline's grouping of runs into libraries and libraries into replicate groups, and its minimum trimmed reads filter, run as a decision task, so other samplesheets work too. The workflow has 73 tasks (47 maps).

## Pipeline

```
fetch_reference / samplesheet_check / stage_reads   URLs or a local mirror ──► work/reference/, work/reads/<run>/, work/runs/<run>
genome prep (single tasks)   GTF2BED, TSS_EXTRACT, CUSTOM_GETCHROMSIZES, GET_AUTOSOMES, GENOME_BLACKLIST_REGIONS, BWA_INDEX, KHMER_UNIQUEKMERS
fastqc, trimgalore           per run ──► results/fastqc/, results/trimgalore/
decide_trimmed               min_trimmed_reads ──► work/lists/{trim_pass,libraries,replicates}/
bwa_mem, sort, index, stats  per run
mlb_*                        per library: MergeSamFiles, MarkDuplicates, bamtools filter, orphan removal (paired-end),
                             CollectMultipleMetrics, bigWig, computeMatrix, plotProfile, plotHeatmap, plotFingerprint,
                             MACS2, FRiP, HOMER, ataqv ──► results/bwa/merged_library/
mlb aggregates               mkarv, MACS2 and HOMER QC plots, consensus peaks, featureCounts, DESeq2 QC
mrp_*                        per replicate group (more than one library): merge, MarkDuplicates, bigWig, MACS2, FRiP, HOMER
mrp aggregates               QC plots, consensus peaks, featureCounts, DESeq2 QC ──► results/bwa/merged_replicate/
igv, multiqc                 ──► results/igv/broad_peak/, results/multiqc/broad_peak/
```

## Inputs / Outputs

- Input: `examples/samplesheet.csv`, the test profile samplesheet (`sample,fastq_1,fastq_2,replicate`, 8 runs of 6 libraries in 4 samples, paired- and single-end, reads downloaded from nf-core/test-datasets). Rows sharing a sample and replicate are runs of one library.
- Input: the genome fasta and GTF URLs, defaulting to the test profile's. Set `input_mirror` to a folder with local copies to skip the downloads.
- `results/bwa/merged_library/`: filtered BAMs, Picard and samtools metrics, bigWigs, deepTools tables, MACS2 broad peaks with FRiP and HOMER annotation, consensus peaks with featureCounts and DESeq2 QC, ataqv.
- `results/bwa/merged_replicate/`: the same for samples with more than one library.
- `results/multiqc/broad_peak/`: the MultiQC report and its data tables.

The MultiQC report has no software versions or workflow summary sections, which nf-core builds from Nextflow run metadata.

Outputs match the Nextflow run (tc-os `scripts/bench/nfcore/atacseq/compare.py`): peaks, FRiP, samtools and Picard metrics, bigWigs, consensus peaks and counts are identical. Three differences are in row or column order only, and the check reads them that way. featureCounts columns and the DESeq2 and MACS2 QC sample order follow Nextflow's `.collect()` order, which changes from run to run; here samples are sorted by name, so PCA signs can flip. deepTools matrix and fingerprint rows follow thread chunks. When two genes are the same distance from a peak, HOMER names either one (about 5 peaks per file). Controls (`--with_control`), narrow peaks and the other aligners are not ported; the test route uses none of them.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `samplesheet` | `examples/samplesheet.csv` | Runs and their reads (`--input`) |
| `fasta_url`, `gtf_url` | test profile URLs | Genome and annotation, plain text (`--fasta`, `--gtf`) |
| `input_mirror` | empty | Folder searched by file name before downloading |
| `min_trimmed_reads` | `10000` | Drop runs with fewer reads after trimming |
| `read_length` | `50` | k-mer size for the MACS2 genome size (`--read_length`) |
| `fragment_size` | `200` | Single-end read extension for bigWigs and fingerprints |
| `fingerprint_bins` | `100` | plotFingerprint samples (test profile value) |
| `broad_cutoff` | `0.1` | MACS2 `--broad-cutoff` |
| `min_reps_consensus` | `1` | Libraries a consensus peak needs |
| `mito_name` | `MT` | Mitochondrial chromosome to exclude; empty keeps all |

## References

- nf-core/atacseq: https://nf-co.re/atacseq/2.1.2 and https://github.com/nf-core/atacseq (MIT; scripts and assets in `nfcore/`)
- BWA: Li and Durbin (2009), Bioinformatics 25(14):1754, https://doi.org/10.1093/bioinformatics/btp324
- MACS2: Zhang et al. (2008), Genome Biol 9:R137, https://doi.org/10.1186/gb-2008-9-9-r137
- HOMER: Heinz et al. (2010), Mol Cell 38(4):576, https://doi.org/10.1016/j.molcel.2010.05.004
- deepTools: Ramírez et al. (2016), Nucleic Acids Res 44(W1):W160, https://doi.org/10.1093/nar/gkw257
- ataqv: Orchard et al. (2020), Cell Syst 10(3):298, https://doi.org/10.1016/j.cels.2020.02.009
- MultiQC: Ewels et al. (2016), Bioinformatics 32(19):3047, https://doi.org/10.1093/bioinformatics/btw354
- nf-core: Ewels et al. (2020), Nat Biotechnol 38:276, https://doi.org/10.1038/s41587-020-0439-x
