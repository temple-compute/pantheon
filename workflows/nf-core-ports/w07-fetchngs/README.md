# W-54 · nf-core/fetchngs (native port)

Public sequencing reads and their metadata from SRA, ENA, DDBJ and GEO ids: a native port of nf-core/fetchngs 1.13.0.

![Domain: nf-core ports](https://img.shields.io/badge/domain-nf--core--ports-green)

## Overview

Runs the nf-core/fetchngs pipeline as a Horus workflow, with the same containers, command lines and per-process cpus/memory as `nextflow run nf-core/fetchngs -r 1.13.0 -profile test,docker`. Each id is resolved to its runs through the ENA and NCBI APIs. Runs with ENA FTP links are downloaded with wget and checked against their md5. Runs without them go through sra-tools (prefetch, then fasterq-dump). The workflow then writes a samplesheet for downstream nf-core pipelines and a MultiQC sample-name mapping. Per-id and per-run steps are `horus_map` stages; the pipeline's Groovy steps are `scripts/fetchngs.py`. The workflow has 10 tasks.

## Variants

- `workflow.chained.yaml`: SRA_RUNINFO_TO_FTP and SRATOOLS_FASTERQDUMP set `chain: true`, so an id or run moves to its next step without waiting for the others, with the same outputs. Needs horus-runtime 0.9.0 or later.

## Pipeline

```
split_ids                   ids list ──► work/ids/<id>                  (input schema check)
sra_ids_to_runinfo[*]       per id ──► work/runinfo/<slot>/<id>.runinfo.tsv
sra_runinfo_to_ftp[*]       per id ──► results/metadata/<slot>/<id>.runinfo_ftp.tsv
branch_downloads            ──► work/lists/ftp/<run>, work/lists/sratools/<run>
sra_fastq_ftp[*]            per FTP run ──► results/fastq/<slot>/<run>[_1|_2].fastq.gz, md5/
custom_sratoolsncbisettings ──► work/ncbi_settings/user-settings.mkfg   (only when a run needs sra-tools)
sratools_prefetch[*]        per sra-tools run ──► work/sra/<slot>/<accession>/
sratools_fasterqdump[*]     per sra-tools run ──► results/fastq_sratools/<slot>/<run>[_1|_2].fastq.gz
create_samplesheet          ──► results/samplesheet/{samplesheet.csv,id_mappings.csv}
multiqc_mappings_config     ──► results/multiqc_config/multiqc_config.yml
```

## Inputs / Outputs

- Input: `examples/sra_ids_test.csv`, the nf-core test id list (10 ids: SRA, ENA, DDBJ and GEO; 14 runs).
- `results/fastq/`: reads downloaded over FTP, with their md5 files in `md5/`.
- `results/fastq_sratools/`: reads from runs without FTP links, from sra-tools.
- `results/metadata/`: the run information table per id, with FTP links and md5 sums.
- `results/samplesheet/`: `samplesheet.csv` (read paths point at the downloaded files) and `id_mappings.csv`.
- `results/multiqc_config/multiqc_config.yml`: sample-name mappings for MultiQC.

Reads, md5 files, run tables, samplesheet, id mappings and MultiQC config match the Nextflow run (reads byte for byte; read paths compared by file name). Run tables match with the same header and the same set of rows: the row order for an id follows the ENA/NCBI API response, which can change between runs. There is no `pipeline_info/` software versions file, which nf-core builds from Nextflow run metadata.

Layout differences from the Nextflow outdir:

- Reads from sra-tools are in `results/fastq_sratools/` (Nextflow: `fastq/`, next to the FTP reads).
- Per-id and per-run files sit in one subfolder per map slot (`results/metadata/<slot>/`, `results/fastq/<slot>/`); Nextflow writes them flat.
- `multiqc_config.yml` is in `results/multiqc_config/` (Nextflow: `samplesheet/`).
- `custom/user-settings.mkfg` (the NCBI settings with a fresh GUID) stays in `work/ncbi_settings/` and is not published.

SRA_IDS_TO_RUNINFO and SRA_FASTQ_FTP have `label 'error_retry'` in the pipeline (`maxRetries 2`). Horus has no per-task retry, so their command runs the script up to 3 times; each try starts from an empty output folder.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `input` | `examples/sra_ids_test.csv` | One id per line (`--input`) |
| `ena_metadata_fields` | empty | ENA fields to fetch (`--ena_metadata_fields`) |
| `download_method` | `ftp` | `--download_method`; only `ftp` is ported (runs without FTP links use sra-tools, as in the pipeline) |
| `skip_fastq_download` | `false` | Only fetch metadata (`--skip_fastq_download`) |
| `nf_core_pipeline` | empty | Add the columns of this nf-core pipeline's samplesheet (`--nf_core_pipeline`) |
| `nf_core_rnaseq_strandedness` | `auto` | Strandedness column for `rnaseq` (`--nf_core_rnaseq_strandedness`) |
| `sample_mapping_fields` | `experiment_accession,...,sample_description` | Columns of `id_mappings.csv` (`--sample_mapping_fields`) |

Not ported: `--download_method aspera`, `fastq-dl` and `sratools` for every run, and `--dbgap_key` for controlled-access data.

## References

- nf-core/fetchngs: https://nf-co.re/fetchngs/1.13.0 and https://github.com/nf-core/fetchngs (MIT, `nfcore/LICENSE`)
- ENA Portal API: https://www.ebi.ac.uk/ena/portal/api/
- SRA Toolkit: https://github.com/ncbi/sra-tools
- nf-core: Ewels et al. (2020), Nat Biotechnol 38:276, https://doi.org/10.1038/s41587-020-0439-x
