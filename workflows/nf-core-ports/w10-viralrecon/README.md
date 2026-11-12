# W-57 · nf-core/viralrecon (native port)

SARS-CoV-2 amplicon variant calling, consensus and assembly: a native port of nf-core/viralrecon 3.0.0.

![Domain: nf-core ports](https://img.shields.io/badge/domain-nf--core--ports-green)

## Overview

Runs the route `nextflow run nf-core/viralrecon -r 3.0.0 -profile test,docker` takes, as Horus tasks with the same containers, rendered command lines and per-process cpus/memory. That route is Illumina amplicon reads (ARTIC V1 primers) through fastp, Kraken2, Bowtie2, iVar primer trimming and variant calling, SnpEff/SnpSift, Freyja, a BCFtools consensus checked with Nextclade, Pangolin and QUAST, SPAdes and Unicycler assemblies with Bandage, ABACAS, BLAST and QUAST, then MultiQC. Per-sample steps are `horus_map` stages over a list of sample meta files. The pipeline's Groovy filters run as small decision tasks: samples with no reads left after fastp, the minimum mapped reads filter and the empty iVar table filter. The Nextclade clade table for MultiQC is a decision task as well, so other samplesheets work too. The workflow has 86 tasks (60 maps).

Left out, because the test profile does not run them: the Nanopore route, `--variant_caller bcftools`, `--consensus_caller ivar`, the minia assembler, PlasmidID, Picard MarkDuplicates (`--skip_markduplicates` is the default), the metagenomic protocol and `--additional_annotation`.

## Pipeline

```
fetch_reference     genome fasta/GFF, primer BED, Kraken2 db, Nextclade dataset
stage_samples       samplesheet.csv ──► reads/<id>/, samples/<id> (single_end)
genome              GUNZIP, UNTAR, COLLAPSE_PRIMERS, GETCHROMSIZES, GETFASTA, PREPARE_PRIMER_FASTA,
                    MAKEBLASTDB, BOWTIE2_BUILD, SNPEFF_BUILD, FREYJA_UPDATE, PANGOLIN_UPDATEDATA
per sample          CAT_FASTQ ─► FASTQC_RAW, FASTP ─► [reads left] ─► FASTQC_TRIM, KRAKEN2
                    BOWTIE2 ─► SORT/INDEX/STATS ─► [min mapped reads] ─► IVAR_TRIM ─► SORT/INDEX/STATS
                    ─► PICARD, MOSDEPTH (genome, amplicon), FREYJA (variants, demix, boot)
                    ─► IVAR_VARIANTS ─► [non-empty] ─► VCF, SORT, TABIX, STATS, SNPEFF, SNPSIFT, QUERY
                    ─► BCFTOOLS_FILTER ─► mask ─► BCFTOOLS_CONSENSUS ─► NEXTCLADE, PANGOLIN, base density
                    KRAKEN2 unclassified ─► CUTADAPT ─► FASTQC, SPADES, UNICYCLER ─► BANDAGE, ABACAS, BLAST
all samples         PLOT_MOSDEPTH_REGIONS, QUAST (consensus, SPAdes, Unicycler), variants long table, MULTIQC
```

## Inputs / Outputs

- Input: `examples/samplesheet.csv`, the test profile samplesheet (`sample,fastq_1,fastq_2`, 4 runs of 3 samples, reads downloaded from nf-core/test-datasets). Rows sharing a sample are merged.
- Input: the reference URLs (genome, GFF, ARTIC primer BED, Kraken2 database, Nextclade dataset), defaulting to the test profile's. Set `input_mirror` to a folder with local copies to skip the downloads.
- `results/variants/`: Bowtie2 and primer-trimmed BAMs with samtools stats, Picard metrics, mosdepth coverage, iVar variants and VCFs, SnpEff/SnpSift, Freyja, the consensus with Nextclade, Pangolin and QUAST, and `long_table/variants_long_table.csv`.
- `results/assembly/`: Cutadapt primer trimming, SPAdes and Unicycler assemblies, Bandage images, ABACAS, BLAST and QUAST.
- `results/fastqc/`, `results/fastp/`, `results/kraken2/`: read QC.
- `results/multiqc/`: the MultiQC report, its data, and `summary_variants_metrics_mqc.csv` / `summary_assembly_metrics_mqc.csv`.

The summary tables, consensus sequences, variant tables, VCF records, read and alignment statistics, QUAST reports and MultiQC data match the Nextflow run. FREYJA_UPDATE and PANGOLIN_UPDATEDATA download the current Freyja barcodes and pangolin-data, as the pipeline does, so Freyja abundances and Pangolin lineages follow the release of the run day. The MultiQC report has no software versions, workflow summary or methods sections, which nf-core builds from Nextflow run metadata.

One MultiQC value depends on file order in the pipeline itself. `<id>.sorted.bam.flagstat` and `<id>.ivar_trim.sorted.bam.flagstat` both clean to the sample name, and the pipeline's MultiQC config has no path filters on its three samtools sections. So "# Mapped reads", "# Trimmed reads (iVar)" and the samtools sections hold whichever of the two files MultiQC reads last. The reference Nextflow run shows the raw count for one sample and the trimmed count for another. The flagstat files themselves match byte for byte; the parity check accepts either count there.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `samplesheet` | `examples/samplesheet.csv` | Samples and their reads (`--input`) |
| `fasta_url`, `gff_url` | MN908947.3 test genome | Genome and annotation (`--genome MN908947.3`) |
| `primer_bed_url` | ARTIC nCoV-2019 V1 | Primer BED (`--primer_set artic --primer_set_version 1`) |
| `kraken2_db_url` | `kraken2_hs22.tar.gz` | Kraken2 host database (`--kraken2_db`) |
| `nextclade_dataset_url` | 2024-10-17 MN908947 dataset | Nextclade dataset (`--nextclade_dataset`) |
| `input_mirror` | empty | Folder searched by file name before downloading |
| `min_mapped_reads` | `1000` | Drop samples with this many mapped reads or fewer |
| `freyja_repeats` | `10` | Freyja bootstrap repeats (`--freyja_repeats`) |

## References

- nf-core/viralrecon: https://nf-co.re/viralrecon/3.0.0 and https://github.com/nf-core/viralrecon (MIT, `nfcore/LICENSE`; the scripts under `nfcore/bin` and the assets under `nfcore/assets` are copied unchanged)
- iVar: Grubaugh et al. (2019), Genome Biol 20:8, https://doi.org/10.1186/s13059-018-1618-7
- fastp: Chen et al. (2018), Bioinformatics 34(17):i884, https://doi.org/10.1093/bioinformatics/bty560
- Kraken 2: Wood et al. (2019), Genome Biol 20:257, https://doi.org/10.1186/s13059-019-1891-0
- Bowtie 2: Langmead and Salzberg (2012), Nat Methods 9:357, https://doi.org/10.1038/nmeth.1923
- SnpEff: Cingolani et al. (2012), Fly 6(2):80, https://doi.org/10.4161/fly.19695
- Freyja: Karthikeyan et al. (2022), Nature 609:101, https://doi.org/10.1038/s41586-022-05049-6
- Nextclade: Aksamentov et al. (2021), JOSS 6(67):3773, https://doi.org/10.21105/joss.03773
- Pangolin: O'Toole et al. (2021), Virus Evol 7(2):veab064, https://doi.org/10.1093/ve/veab064
- SPAdes: Bankevich et al. (2012), J Comput Biol 19(5):455, https://doi.org/10.1089/cmb.2012.0021
- Unicycler: Wick et al. (2017), PLoS Comput Biol 13(6):e1005595, https://doi.org/10.1371/journal.pcbi.1005595
- QUAST: Gurevich et al. (2013), Bioinformatics 29(8):1072, https://doi.org/10.1093/bioinformatics/btt086
- MultiQC: Ewels et al. (2016), Bioinformatics 32(19):3047, https://doi.org/10.1093/bioinformatics/btw354
- nf-core: Ewels et al. (2020), Nat Biotechnol 38:276, https://doi.org/10.1038/s41587-020-0439-x
