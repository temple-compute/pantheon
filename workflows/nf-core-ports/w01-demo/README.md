# W-48 · nf-core/demo

Read QC, trimming and a MultiQC report: a native port of nf-core/demo 1.2.0.

![Domain: nf-core ports](https://img.shields.io/badge/domain-nf--core--ports-green)

## Overview

Runs the nf-core/demo pipeline as a Horus workflow, with the same containers, command lines and per-process cpus/memory as `nextflow run nf-core/demo -r 1.2.0 -profile test,docker`. A samplesheet is split into one folder per sample, FastQC and seqtk run once per sample as `horus_map` stages, and MultiQC reads the FastQC map's output folder. The workflow has 5 tasks.

## Pipeline

```
stage_samples      samplesheet.csv ──► samples/<sample>/ (reads + reads.txt; repeated rows merged)
fastqc[*]          horus_map over samples/ ──► results/fastqc/<slot>/<sample>_<n>_fastqc.{html,zip}
seqtk_trim[*]      horus_map over samples/ ──► results/fq/<slot>/<sample>_<read>.fastq.gz
cowpy              ──► results/cowpy/cowpy.txt
multiqc            results/fastqc/ ──► results/multiqc/ (multiqc_report.html, multiqc_data/)
```

## Inputs / Outputs

- Input: `examples/samplesheet.csv`, the nf-core test samplesheet (`sample,fastq_1,fastq_2`, 3 samples, reads downloaded from nf-core/test-datasets). Reads may also be paths relative to the samplesheet.
- Input: `examples/multiqc_config.yml`, the pipeline's MultiQC config.
- `results/fastqc/`: one FastQC HTML report and zip per read file.
- `results/fq/`: seqtk-trimmed reads, gzipped.
- `results/multiqc/`: the MultiQC report and its data tables.
- `results/cowpy/cowpy.txt`: the pipeline's ASCII-art greeting.

The FastQC, seqtk and MultiQC general statistics match the Nextflow run exactly. The MultiQC report has no software versions or Nextflow workflow summary sections, which nf-core builds from Nextflow run metadata.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `samplesheet` | `examples/samplesheet.csv` | Samples and their reads (`--input`) |
| `multiqc_config` | `examples/multiqc_config.yml` | MultiQC config (`--multiqc_config`) |
| `skip_trim` | `false` | Skip seqtk trimming (`--skip_trim`) |
| `multiqc_title` | empty | MultiQC report title (`--multiqc_title`) |

## References

- nf-core/demo: https://nf-co.re/demo/1.2.0 and https://github.com/nf-core/demo
- FastQC: https://www.bioinformatics.babraham.ac.uk/projects/fastqc/
- seqtk: https://github.com/lh3/seqtk
- MultiQC: Ewels et al. (2016), Bioinformatics 32(19):3047, https://doi.org/10.1093/bioinformatics/btw354
- nf-core: Ewels et al. (2020), Nat Biotechnol 38:276, https://doi.org/10.1038/s41587-020-0439-x
