# W-56 · nf-core/mag (native port)

Metagenome assembly, binning and bin annotation: a native port of nf-core/mag 5.5.0.

![Domain: nf-core ports](https://img.shields.io/badge/domain-nf--core--ports-green)

## Overview

Runs the route `nextflow run nf-core/mag -r 5.5.0 -profile test,docker` takes, as Horus tasks with the same containers, rendered command lines and per-process cpus/memory: FastQC, fastp and Bowtie2 PhiX removal per run, run merging, MEGAHIT and metaSPAdes per sample, QUAST and Prodigal per assembly, Bowtie2 mapping for binning, MetaBAT2, MaxBin2 and SemiBin2, then BUSCO, QUAST, CAT, GTDB-Tk and Prokka on the bins, bin depths, the bin summary and MultiQC. Per-run, per-sample, per-assembly and per-bin steps are `horus_map` stages. The pipeline's channel logic after binning runs as decision tasks (`scripts/decide.py`): bin size filter, unbinned contig splits, the post-binning bin sets and the BUSCO filter in front of GTDB-Tk, so other samplesheets give the sets nf-core would. The workflow has 46 tasks (31 maps).

Route left out (not run by the test profile): long reads (Nanopore/PacBio preprocessing, Flye, metaMDBG, hybrid SPAdes, PyPolCA), host removal, adapterremoval/Trimmomatic, BBNorm, group co-assembly, Kraken2/Centrifuge read taxonomy, ALE, CONCOCT, COMEBin, MetaBinner, DAS Tool refinement, Tiara domain classification, CheckM/CheckM2/GUNC, geNomad, MetaEuk, ancient DNA validation and given assemblies (`--assembly_input`).

## Pipeline

```
stage_samples / fetch_databases   samplesheet ──► work/reads/, run, sample, assembly and mapping lists; database archives
BUSCO_UNTAR, CATPACK_DB_UNTAR, GTDBTK_DB_PREPARATION
fastqc_raw, fastp, phix_align, fastqc_trimmed   per run ──► results/QC_shortreads/
cat_fastq                         samples with several runs ──► <id>_[12].merged.fastq.gz
megahit, spades                   per sample ──► results/Assembly/
gunzip, quast, prodigal, bt2_build    per assembly
bt2_align                         each assembly x every sample of its group
depths, convert_depths, metabat2, maxbin2, semibin    per assembly ──► results/GenomeBinning/
binsets ─► seqkit, split_fasta ─► postbinning         bin sets, unbinned sets, one folder per bin
busco, quast_bins ─► concat_busco, concat_quast
gtdb_filter ─► gtdbtk ─► gtdbtk_summary
mag_depths ─► mag_depths_summary
catpack_bins ─► addnames ─► summarise; concat_unbins ─► catpack_unbins ─► addnames ─► summarise
prokka                            per bin ──► results/Annotation/Prokka/
bin_summary, multiqc              ──► results/GenomeBinning/summary/bin_summary.tsv, results/multiqc/
```

## Inputs / Outputs

- Input: `examples/samplesheet.csv`, the test profile samplesheet (`sample,run,group,short_reads_platform,short_reads_1,short_reads_2,long_reads`, 3 runs of 2 samples, reads downloaded from nf-core/test-datasets). Paired short reads only. Rows sharing a sample are runs of one sample.
- Input: the BUSCO lineage, CAT and GTDB-Tk database archives, defaulting to the test profile's small databases. Set `input_mirror` to a folder with local copies to skip the downloads.
- `results/GenomeBinning/summary/bin_summary.tsv`: depth, BUSCO, QUAST, GTDB-Tk and CAT per bin, plus `bat_summary.tsv`.
- `results/GenomeBinning/`: MetaBAT2, MaxBin2 and SemiBin2 bins, split unbinned contigs, BUSCO and QUAST per bin set, contig depths and `contig_to_bin/contig_to_bin_map.tsv`.
- `results/Assembly/`, `results/Annotation/`, `results/Taxonomy/`, `results/QC_shortreads/`: assemblies, Prodigal and Prokka, CAT and GTDB-Tk, read QC.
- `results/multiqc/`: the MultiQC report and its data tables.

Assemblies, bins, depth tables, every summary table and the MultiQC tables match the Nextflow run (`scripts/bench/nfcore/mag/compare.py` in tc-os). The MultiQC report has no software versions, workflow summary or methods sections, which nf-core builds from Nextflow run metadata. Where Nextflow orders inputs by task finish time, the port uses a fixed order: runs of a sample are merged in samplesheet order, an assembly's BAMs go to jgi_summarize_bam_contig_depths and SemiBin2 in reverse name order (the finish order of the test run), and CONCAT_BUSCO_TSV concatenates in BUSCO slot order. SemiBin2 and the depth column order depend on the BAM order, so another dataset can bin differently from a Nextflow run that happened to finish in another order. MaxBin2 assemblies it cannot bin (exit 1 or 255) are dropped, as the pipeline's `errorStrategy` ignores them.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `samplesheet` | `examples/samplesheet.csv` | Samples, runs and reads (`--input`) |
| `busco_db_url`, `busco_db_lineage` | test `bacteria_odb10` archive | BUSCO lineage (`--busco_db`, `--busco_db_lineage`) |
| `cat_db_url` | `minigut_cat.tar.gz` | CAT database (`--cat_db`) |
| `gtdb_db_url` | `gtdbtk_mockup_r232_20260507.tar.gz` | GTDB-Tk database (`--gtdb_db`) |
| `input_mirror` | empty | Folder searched by file name before downloading |
| `min_length_unbinned_contigs`, `max_unbinned_contigs` | `1`, `2` | Unbinned contigs kept as single-contig bins (test profile values) |
| `bin_min_size`, `bin_max_size` | `0`, `0` (none) | Bin size filter in bp |
| `gtdbtk_min_completeness`, `gtdbtk_max_contamination` | `0.01`, `10` | BUSCO thresholds for GTDB-Tk (test profile, default) |

## References

- nf-core/mag: https://nf-co.re/mag/5.5.0 and https://github.com/nf-core/mag (MIT; `bin/` scripts and assets in `nfcore/`). Krakau et al. (2022), NAR Genom Bioinform 4(1):lqac007, https://doi.org/10.1093/nargab/lqac007
- MEGAHIT: Li et al. (2015), Bioinformatics 31(10):1674, https://doi.org/10.1093/bioinformatics/btv033
- metaSPAdes: Nurk et al. (2017), Genome Res 27(5):824, https://doi.org/10.1101/gr.213959.116
- MetaBAT 2: Kang et al. (2019), PeerJ 7:e7359, https://doi.org/10.7717/peerj.7359
- SemiBin2: Pan et al. (2023), Bioinformatics 39(S1):i21, https://doi.org/10.1093/bioinformatics/btad209
- GTDB-Tk: Chaumeil et al. (2022), Bioinformatics 38(23):5315, https://doi.org/10.1093/bioinformatics/btac672
- MultiQC: Ewels et al. (2016), Bioinformatics 32(19):3047, https://doi.org/10.1093/bioinformatics/btw354
- nf-core: Ewels et al. (2020), Nat Biotechnol 38:276, https://doi.org/10.1038/s41587-020-0439-x
