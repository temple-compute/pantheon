# W-04 · Single-Cell RNA-seq Analysis with GPU Acceleration (ScaleSC / RAPIDS)

![Status: draft](https://img.shields.io/badge/status-draft-lightgrey)
![Domain: Genomics](https://img.shields.io/badge/domain-genomics-purple)
![GTM: Tier 1](https://img.shields.io/badge/GTM-Tier%201-green)

## Overview

Full single-cell RNA sequencing (scRNA-seq) analysis pipeline from raw sequencing reads to annotated cell types and differential expression results. Handles datasets of 100k to 10M+ cells by leveraging GPU acceleration (ScaleSC, RAPIDS cuML) for the compute-intensive dimensionality reduction, clustering, and embedding steps.

GPU acceleration delivers 20× speedup over CPU-only pipelines for large datasets. Without it, clustering 1M cells on CPU can take 24h+; with A100 acceleration (ScaleSC), the same step takes under 1 hour. This makes the workflow a natural showcase for Horus: the first and last stages are CPU-bound HPC jobs, while the middle stages need GPU nodes.

**Target users:** Computational biologists, single-cell genomics labs, biotech/pharma genomics teams.

---

## Compute Pattern

| Stage | Name | Cluster Type | Resources | Est. Walltime |
|-------|------|-------------|-----------|---------------|
| 1 | `ALIGNMENT_AND_QC` | CPU cluster | 32–64 cores, 128GB RAM | 2–8h |
| 2 | `GPU_ANALYSIS` | GPU — mid-tier (A100-40GB) | 4×A100-40GB | 1–3h (1M–10M cells) |
| 3 | `ANNOTATION` | GPU — mid-tier | 2–4×A100-40GB | 30 min–2h |
| 4 | `DIFFERENTIAL_EXPRESSION` | CPU cluster | 32 cores | 1–4h |

---

## Tools & Dependencies

| Tool | Role | Source |
|------|------|--------|
| [STARsolo](https://github.com/alexdobin/STAR) | Read alignment + cell barcode demultiplexing | MIT |
| [CellRanger](https://www.10xgenomics.com/support/software/cell-ranger) | 10x Genomics alignment (alternative) | 10x license (free) |
| [ScaleSC](https://github.com/bioscinema/ScaleSC) | GPU-accelerated scRNA-seq analysis | MIT (2025) |
| [RAPIDS cuML](https://github.com/rapidsai/cuml) | GPU-accelerated ML: PCA, UMAP, k-NN | Apache 2.0 |
| [scanpy](https://scanpy.readthedocs.io/) | Python scRNA-seq analysis framework | BSD |
| [scGPT](https://github.com/bowang-lab/scGPT) | Foundation model for cell type annotation | MIT |
| [CellTypist](https://github.com/Teichlab/celltypist) | Automated cell type annotation (lighter alternative) | MIT |
| [DESeq2](https://bioconductor.org/packages/DESeq2/) | Pseudobulk differential expression | GPL |
| [edgeR](https://bioconductor.org/packages/edgeR/) | Alternative DE method | GPL |
| [AnnData](https://anndata.readthedocs.io/) | Data format for single-cell datasets | BSD |

---

## Input / Output

**Inputs:**
- `fastq/` — raw FASTQ files from sequencer (or pre-aligned `*.h5` / `*.h5ad` count matrix)
- `genome_ref/` — reference genome + GTF annotation (GRCh38 or GRCm39)
- `config.yaml` — workflow parameters
- `metadata.csv` — sample/cell metadata (optional, for multi-sample DE)

**Outputs:**
- `results/annotated.h5ad` — AnnData object with cell type labels, UMAP coordinates, all computed embeddings
- `results/cell_type_summary.csv` — cell type composition per sample
- `results/de_results/` — differential expression tables per comparison
- `results/report.html` — interactive UMAP plots, QC metrics, cell type visualizations

---

## Horus Configuration

```
Cluster A (stages 1, 4):  CPU cluster — high-memory preferred
                            cores: 32–64, RAM: 128–256GB
                            Note: CellRanger is memory-intensive; 128GB minimum

Cluster B (stages 2, 3):   GPU cluster — A100-40GB or equivalent
                             gpus: 4×A100-40GB
                             requires: CUDA >= 11.8, cuML >= 23.x
```

**Data flow:**
- Stage 1 → Stage 2: count matrix as HDF5 or AnnData h5ad file (~1–10GB)
- Stage 2 → Stage 3: AnnData object with embeddings and cluster labels (~1–5GB)
- Stage 3 → Stage 4: annotated AnnData + cluster-to-celltype mapping (~same size)

**Scheduler notes:**
- Stage 1 supports parallelism across samples (one STAR job per sample). Use Horus job arrays if running multi-sample experiments.
- Stage 2 is single-node multi-GPU. ScaleSC handles internal GPU parallelism; Horus needs to allocate 4 GPUs to a single job, not distribute across nodes.
- Stage 4 runs per comparison group. Can be parallelized as a job array if many DE comparisons are needed.

---

## Parameterization

| Parameter | Description | Default |
|-----------|-------------|---------|
| `genome` | Reference genome: `hg38`, `mm10`, `hg38+mm10` (xenograft) | `hg38` |
| `aligner` | `starsolo` or `cellranger` | `starsolo` |
| `min_genes_per_cell` | QC filter: minimum genes detected per cell | `200` |
| `max_mito_pct` | QC filter: maximum mitochondrial gene % | `20` |
| `n_top_genes` | Highly variable genes for downstream analysis | `3000` |
| `n_pcs` | Number of PCs for dimensionality reduction | `50` |
| `n_neighbors` | k-NN graph neighbors for clustering | `30` |
| `annotation_model` | `scgpt` or `celltypist` | `celltypist` |
| `de_method` | `deseq2` or `edger` | `deseq2` |
| `de_comparisons` | List of group pairs for DE | — |

---

## Implementation Notes

- ScaleSC (2025) handles datasets up to 20M cells with batches up to 1000 on a single A100-40GB. For larger datasets, contact the ScaleSC team for multi-GPU guidance.
- CellRanger is required for 10x Genomics data with proprietary chemistry features (Flex, Multiome); STARsolo covers standard 3' and 5' libraries and is faster.
- scGPT provides more accurate annotation than CellTypist but requires more GPU memory and runtime. For a quick first pass, use CellTypist; switch to scGPT for production annotation.
- DESeq2 pseudobulk requires ≥3 biological replicates per group. Single-sample experiments should use Wilcoxon rank-sum tests instead.
- The UMAP representation is stochastic. For reproducibility, always set a random seed in config.

---

## Open Questions

- [ ] Should the workflow support multi-modal data (ATAC-seq, CITE-seq) in addition to RNA? scATACpipe handles ATAC but requires a separate pipeline entry.
- [ ] What shared storage format is preferred for the h5ad artifact between stages? Need to confirm read/write performance on the Horus artifact store.
- [ ] Should Harmony or scVI be offered as batch correction alternatives in stage 2?
- [ ] Is there a standard reference atlas for automatic cell type annotation, or do we expect users to provide their own?

---

## References

- [ScaleSC paper (Oxford Bioinformatics Advances, 2025)](https://academic.oup.com/bioinformaticsadvances/article/5/1/vbaf167/8205667)
- [scGPT GitHub](https://github.com/bowang-lab/scGPT)
- [RAPIDS cuML for single-cell (NVIDIA)](https://developer.nvidia.com/blog/accelerating-single-cell-genomic-analysis-using-rapids/)
- [scanpy documentation](https://scanpy.readthedocs.io/)
- [DESeq2 paper](https://genomebiology.biomedcentral.com/articles/10.1186/s13059-014-0550-8)
