# W-50 · nf-core/sarek (native port)

Germline variant calling from paired FASTQ: a native port of nf-core/sarek 3.12.0.

![Domain: nf-core ports](https://img.shields.io/badge/domain-nf--core--ports-green)

## Overview

Runs the route `nextflow run nf-core/sarek -r 3.12.0 -profile test,docker` takes, as Horus tasks with the same containers, rendered command lines and per-process cpus/memory: interval preparation, BWA index, FastQC and bwa mem per lane, GATK MarkDuplicates, base quality recalibration, mosdepth and samtools stats on both CRAMs, Strelka germline calling, bcftools stats, vcftools and MultiQC. Per-lane steps map over lane meta files and per-sample steps over sample meta files, so samplesheets with more samples and lanes work too. The samplesheet split builds sarek's read group (flowcell from the FASTQ header). The workflow has 22 tasks (14 maps).

## Pipeline

```
fetch_reference / stage_samples   URLs or a local mirror ──► work/reference/, work/reads/<sample>-<lane>/, work/lanes/, work/samples/
create_intervals_bed, intervallisttobed, tabix (split, combined)   interval_list ──► one BED per interval, combined BED
bwamem1_index                      genome.fasta ──► work/bwa_index/bwa/
fastqc[*], bwamem1_mem[*]          per lane ──► results/reports/fastqc/, work/mapped/<sample>-<lane>.sorted.bam
markduplicates[*]                  lanes of a sample ──► results/preprocessing/markduplicates/<sample>.md.cram (+ metrics)
md_samtools_stats, md_mosdepth     ──► results/reports/samtools/, results/reports/mosdepth/
baserecalibrator, applybqsr        ──► results/preprocessing/recal_table/, results/preprocessing/recalibrated/<sample>.recal.cram
recal_samtools_stats, recal_mosdepth
strelka_single[*]                  ──► results/variant_calling/strelka/<sample>.strelka.{variants,genome}.vcf.gz
bcftools_stats, vcftools (TsTv count, TsTv qual, FILTER summary)
multiqc                            ──► results/multiqc/multiqc_report.html
```

## Inputs / Outputs

- Input: `examples/samplesheet.csv`, the test profile samplesheet (`patient,sex,status,sample,lane,fastq_1,fastq_2`, one sample in two lanes, reads downloaded from nf-core/test-datasets). Rows sharing a sample are its lanes.
- Input: the reference URLs (genome, index, dictionary, interval_list, dbSNP and Mills indels with indexes), defaulting to the test profile's `testdata.nf-core.sarek` genome. Set `input_mirror` to a folder with local copies to skip the downloads.
- `results/variant_calling/strelka/`: Strelka variants and genome VCFs with tabix indexes.
- `results/preprocessing/`: MarkDuplicates and recalibrated CRAMs, the BQSR table and the MarkDuplicates metrics.
- `results/reports/`: FastQC, samtools stats, mosdepth, bcftools stats and vcftools tables.
- `results/multiqc/`: the MultiQC report and its data tables.

The VCF records, samtools stats (including the read checksums of both CRAMs), mosdepth, bcftools and vcftools outputs, FastQC data and the MultiQC tables match the Nextflow run. The MultiQC report has no software versions, workflow summary or methods sections, which nf-core builds from Nextflow run metadata.

MarkDuplicates gets a sample's lanes in samplesheet order. Nextflow passes them in the order bwa mem finishes, which changes from run to run. When two lanes hold the same reads, as in the test data, MarkDuplicates marks one lane's copy as duplicate, so the per-lane duplicate and BQSR tables can swap lane labels between runs of either engine. The CRAM content and the variant calls are the same either way.

## Left out

The port covers the test profile's route. Not ported: other aligners (bwa-mem2, DragMap, Sentieon, Parabricks), FASTQ splitting and trimming (fastp), UMI handling, input from BAM, CRAM or spring files, tumor samples and somatic calling, variant callers other than Strelka, annotation, joint germline calling, `--wes`, per-interval scatter of BQSR and Strelka (the workflow stops with an error when the interval_list has more than one interval), building missing reference indexes (`.fai`, `.dict`, known-sites `.tbi`), the `csv/` restart samplesheets and the `--skip_tools` switches. The stage task stops with an error on rows it cannot handle.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `samplesheet` | `examples/samplesheet.csv` | Samples and their lanes (`--input`) |
| `fasta_url` | test genome | Genome fasta (`--fasta`); also the read group `DS` tag |
| `fasta_fai_url`, `dict_url` | test genome | Fasta index and sequence dictionary (`--fasta_fai`, `--dict`) |
| `intervals_url` | `genome.interval_list` | Calling regions (`--intervals`, GATK interval_list, one interval) |
| `dbsnp_url`, `dbsnp_tbi_url` | `dbsnp_146.hg38.vcf.gz` | Known sites for BQSR (`--dbsnp`) |
| `known_indels_url`, `known_indels_tbi_url` | `mills_and_1000G.indels.vcf.gz` | Known indels for BQSR (`--known_indels`) |
| `seq_platform` | `ILLUMINA` | Read group `PL` (`--seq_platform`) |
| `seq_center` | empty | Read group `CN` (`--seq_center`) |
| `multiqc_title` | empty | MultiQC report title (`--multiqc_title`) |
| `input_mirror` | empty | Folder searched by file name before downloading |

## References

- nf-core/sarek: https://nf-co.re/sarek/3.12.0 and https://github.com/nf-core/sarek (MIT; `nfcore/assets/multiqc_config.yml`). Hanssen et al. (2024), NAR Genom Bioinform 6(2):lqae031, https://doi.org/10.1093/nargab/lqae031
- BWA: Li and Durbin (2009), Bioinformatics 25(14):1754, https://doi.org/10.1093/bioinformatics/btp324
- GATK: Van der Auwera and O'Connor (2020), Genomics in the Cloud, O'Reilly
- Strelka2: Kim et al. (2018), Nat Methods 15:591, https://doi.org/10.1038/s41592-018-0051-x
- mosdepth: Pedersen and Quinlan (2018), Bioinformatics 34(5):867, https://doi.org/10.1093/bioinformatics/btx699
- MultiQC: Ewels et al. (2016), Bioinformatics 32(19):3047, https://doi.org/10.1093/bioinformatics/btw354
- nf-core: Ewels et al. (2020), Nat Biotechnol 38:276, https://doi.org/10.1038/s41587-020-0439-x
