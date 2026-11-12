# W-53 · nf-core/chipseq (native port)

ChIP-seq peak calling and QC: a native port of nf-core/chipseq 2.1.0.

![Domain: nf-core ports](https://img.shields.io/badge/domain-nf--core--ports-green)

## Overview

Runs the route `nextflow run nf-core/chipseq -r 2.1.0 -profile test,docker` takes, as Horus tasks with the same containers, rendered command lines and per-process cpus/memory: TrimGalore, BWA, Picard merge and MarkDuplicates, BAMTools filtering and orphan removal, Picard metrics, phantompeakqualtools, bigWigs, deepTools, MACS3 broad peaks with FRiP and HOMER annotation, consensus peaks with featureCounts and DESeq2 QC, an IGV session and MultiQC. Per-library, per-sample, per-IP and per-antibody steps are `horus_map` stages over lists of meta files. The pipeline's Groovy logic runs as tasks too: the samplesheet check, the library-to-sample merge, IP/control pairing, the empty-peaks filter and the consensus grouping per antibody, so other samplesheets work as well. The workflow has 53 tasks (40 maps).

## Variants

- `workflow.chained.yaml`: the per-library, per-sample and per-antibody maps set `chain: true`, so a library or sample moves to its next step without waiting for the others, with the same outputs. FRiP and HOMER drop an IP with no peaks themselves (`drop_exit_codes`). It needs horus-runtime 0.9.0 or later.

## Pipeline

```
fetch_reference / samplesheet_check / stage_samples   ──► work/reference/, work/reads/<lib>/, work/lists/{libs,samples,ips}/
genome prep (single tasks)        GTF2BED, CUSTOM_GETCHROMSIZES, GENOME_BLACKLIST_REGIONS, BWA_INDEX, KHMER_UNIQUEKMERS
per library                       FASTQC, TRIMGALORE, BWA_MEM, SAMTOOLS sort / index / stats / flagstat / idxstats
per sample                        PICARD_MERGESAMFILES, PICARD_MARKDUPLICATES (+ samtools stats)
                                  BAMTOOLS_FILTER, SAMTOOLS_SORT -n, BAM_REMOVE_ORPHANS, SAMTOOLS_SORT (+ samtools stats)
                                  PICARD_COLLECTMULTIPLEMETRICS, PHANTOMPEAKQUALTOOLS, bedGraph and bigWig, deepTools profile and heatmap
per IP sample (with its control)  DEEPTOOLS_PLOTFINGERPRINT, MACS3_CALLPEAK
filter_peaks                      empty peak files out, IP samples grouped by antibody ──► work/lists/{peak_pass,antibodies}/
per IP with peaks                 FRIP_SCORE, MULTIQC_CUSTOM_PEAKS, HOMER_ANNOTATEPEAKS; PLOT_MACS3_QC, PLOT_HOMER_ANNOTATEPEAKS
per antibody                      MACS3_CONSENSUS, HOMER_ANNOTATEPEAKS, ANNOTATE_BOOLEAN_PEAKS, SUBREAD_FEATURECOUNTS, DESEQ2_QC
igv, multiqc                      ──► results/igv/broad_peak/, results/multiqc/broad_peak/
```

## Inputs / Outputs

- Input: `examples/samplesheet.csv`, the test profile samplesheet (`sample,fastq_1,fastq_2,replicate,antibody,control,control_replicate`: SPT5 at two time points, two replicates each, and two input controls; reads downloaded from nf-core/test-datasets).
- Input: the genome fasta and GTF URLs, defaulting to the test profile's. Set `input_mirror` to a folder with local copies to skip the downloads.
- `results/bwa/merged_library/`: filtered BAMs, samtools and Picard metrics, phantompeakqualtools, bigWigs and deepTools plots.
- `results/bwa/merged_library/macs3/broad_peak/`: MACS3 peaks, HOMER annotation, FRiP and peak QC, and per-antibody consensus peaks with featureCounts and DESeq2 QC.
- `results/igv/broad_peak/` and `results/multiqc/broad_peak/`: the IGV session and the MultiQC report.

Peaks, consensus peaks, featureCounts tables, samtools, Picard, FastQC and phantompeakqualtools metrics, bigWigs and the MultiQC data match the Nextflow run (tc-os `scripts/bench/nfcore/chipseq/compare.py`). Where Nextflow orders inputs by arrival or by work-dir path (PLOT_MACS3_QC, PLOT_HOMER_ANNOTATEPEAKS, the featureCounts BAM list, the IGV file list), this port sorts them by name, so those tables have the same rows in a fixed order and the DESeq2 sample-distance matrix lists the samples in name order. Some outputs differ between any two runs, Nextflow or Horus: plotFingerprint writes its sampled bins in thread order, DESeq2 PCA components can flip sign, and HOMER picks either of two equally near genes for a peak (up to 23 of 6,300 annotated peaks in the test run; the distance to the TSS is the same). Floating-point values agree to 1e-6. The MultiQC report has no software versions, workflow summary or methods sections, which nf-core builds from Nextflow run metadata.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `samplesheet` | `examples/samplesheet.csv` | Samples, replicates, antibodies, controls and their reads (`--input`) |
| `fasta_url`, `gtf_url` | test profile URLs | Genome and annotation, uncompressed (`--fasta`, `--gtf`) |
| `input_mirror` | empty | Folder searched by file name before downloading |
| `read_length` | `50` | k-mer size for the MACS3 genome size (`--read_length`) |
| `fingerprint_bins` | `100` | deepTools plotFingerprint samples (`--fingerprint_bins`) |
| `min_reps_consensus` | `1` | Replicates a consensus peak needs (`--min_reps_consensus`) |

The port covers the test route: BWA, broad peaks, no blacklist, no Preseq. Other aligners (Bowtie2, Chromap, STAR), `--narrow_peak`, gzipped or iGenomes references and prebuilt indexes are not ported.

## References

- nf-core/chipseq: https://nf-co.re/chipseq/2.1.0 and https://github.com/nf-core/chipseq (MIT; scripts and assets in `nfcore/`)
- BWA: Li & Durbin (2009), Bioinformatics 25(14):1754, https://doi.org/10.1093/bioinformatics/btp324
- MACS: Zhang et al. (2008), Genome Biol 9:R137, https://doi.org/10.1186/gb-2008-9-9-r137
- HOMER: Heinz et al. (2010), Mol Cell 38(4):576, https://doi.org/10.1016/j.molcel.2010.05.004
- deepTools: Ramírez et al. (2016), Nucleic Acids Res 44(W1):W160, https://doi.org/10.1093/nar/gkw257
- phantompeakqualtools: Landt et al. (2012), Genome Res 22(9):1813, https://doi.org/10.1101/gr.136184.111
- MultiQC: Ewels et al. (2016), Bioinformatics 32(19):3047, https://doi.org/10.1093/bioinformatics/btw354
- nf-core: Ewels et al. (2020), Nat Biotechnol 38:276, https://doi.org/10.1038/s41587-020-0439-x
