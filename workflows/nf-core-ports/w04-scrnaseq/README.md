# W-51 · nf-core/scrnaseq (native port)

Single-cell RNA-seq with STARsolo, h5ad and Seurat/SCE conversion and a MultiQC report: a native port of nf-core/scrnaseq 4.2.0.

![Domain: nf-core ports](https://img.shields.io/badge/domain-nf--core--ports-green)

## Overview

Runs the route `nextflow run nf-core/scrnaseq -r 4.2.0 -profile test,docker` takes (`--aligner star --protocol 10XV2`), as Horus tasks with the same containers, rendered command lines and per-process cpus/memory: FastQC, the GTF gene filter, the STAR index, STARsolo per sample, MTX to h5ad per sample and matrix type, the combined h5ad per type, Seurat and SingleCellExperiment objects for every h5ad, and MultiQC. Per-sample steps are `horus_map` stages; the h5ad steps map over one item per (sample, matrix type), as Nextflow runs them. The workflow has 11 tasks (5 maps). On the test data they run the same 19 process commands as Nextflow, plus three staging tasks.

## Variants

- `workflow.chained.yaml`: per-sample maps set `chain: true`, so a sample moves to its next step without waiting for the others, with the same outputs. MTX_TO_H5AD and ANNDATAR_CONVERT run once per sample for both matrix types, and the combined objects come from their own map (`results/mtx_conversions/rds_combined/`). Needs horus-runtime 0.9.0 or later.

## Pipeline

```
fetch_reference / stage_samples   URLs ──► work/reference/, work/samples/<id>/ (reads, reads.txt, meta.env)
gtf_filter                        GTF_GENE_FILTER ──► <fasta>_genes.gtf
star_idx                          STAR_GENOMEGENERATE ──► work/star_index/star/
fastqc[*]                         per sample ──► results/fastqc/
star_align[*]                     STARsolo per sample (CB_UMI_Simple, 10x V2 whitelist) ──► results/star/<slot>/<id>.Solo.out, BAM, logs
list_matrices                     one item per (id, raw|filtered), plus combined per type
mtx[*], concat[*], convert[*]     MTX_TO_H5AD, CONCAT_H5AD, ANNDATAR_CONVERT ──► results/mtx_conversions/
multiqc                           FastQC + STAR logs ──► results/multiqc/
```

## Inputs / Outputs

- Input: `examples/samplesheet.csv`, the test profile samplesheet (`sample,fastq_1,fastq_2,expected_cells,seq_center`, 3 runs of 2 samples, reads downloaded from nf-core/test-datasets). Rows sharing a sample are runs of one sample; the first row's `expected_cells` and `seq_center` apply, as in the pipeline.
- Input: `fasta_url` and `gtf_url`, the mouse chr19 genome and GENCODE annotation of the test profile (plain, not gzipped).
- Input: `nfcore/`, the pipeline's 10x V2 barcode whitelist, MultiQC config, GTF filter script and the MTX_TO_H5AD, CONCAT_H5AD and ANNDATAR_CONVERT templates (MIT). The templates read their Groovy values from `NF_*` environment variables.
- `results/star/`: per sample the STARsolo raw and filtered matrices, `Barcodes.stats`, `Features.stats`, `Summary.csv`, the sorted BAM, `SJ.out.tab` and the STAR logs.
- `results/mtx_conversions/`: `<id>_{raw,filtered}_matrix.h5ad`, `combined_{raw,filtered}_matrix.h5ad`, and a `.seurat.rds` and `.sce.rds` for each.
- `results/fastqc/`, `results/multiqc/`: read QC and the MultiQC report with its data tables.

The STARsolo matrices and stats, STAR logs and splice junctions, FastQC data, h5ad contents and the MultiQC general, FastQC and STAR tables match the Nextflow run. The combined h5ad may list cells in another order: CONCAT_H5AD concatenates samples in directory-listing order, in both engines. The STAR BAMs have the same records and header lines apart from `@PG`, which holds the command line with its work paths. h5ad and RDS bytes carry run metadata, so they are compared by name, and h5ad files also by content (X, layers, obs and var). The MultiQC report has no software versions, workflow summary or methods sections, which nf-core builds from Nextflow run metadata.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `samplesheet` | `examples/samplesheet.csv` | Samples and their reads (`--input`) |
| `fasta_url` | test profile `GRCm38.p6.genome.chr19.fa` | Genome fasta (`--fasta`) |
| `gtf_url` | test profile `gencode.vM19.annotation.chr19.gtf` | Annotation (`--gtf`) |

Fixed to the test route: `--aligner star`, `--protocol 10XV2`, `--star_feature Gene`, `--skip_cellbender`, `--skip_qcatch`. Other aligners (simpleaf, kallisto, Cell Ranger), other protocols, velocity matrices, CellBender, QCatch and prebuilt STAR indexes are not ported.

## References

- nf-core/scrnaseq: https://nf-co.re/scrnaseq/4.2.0 and https://github.com/nf-core/scrnaseq
- STARsolo: Kaminow et al. (2021), bioRxiv, https://doi.org/10.1101/2021.05.05.442755
- STAR: Dobin et al. (2013), Bioinformatics 29(1):15, https://doi.org/10.1093/bioinformatics/bts635
- Scanpy: Wolf et al. (2018), Genome Biol 19:15, https://doi.org/10.1186/s13059-017-1382-0
- anndataR: https://github.com/scverse/anndataR
- FastQC: https://www.bioinformatics.babraham.ac.uk/projects/fastqc/
- MultiQC: Ewels et al. (2016), Bioinformatics 32(19):3047, https://doi.org/10.1093/bioinformatics/btw354
- nf-core: Ewels et al. (2020), Nat Biotechnol 38:276, https://doi.org/10.1038/s41587-020-0439-x
