#!/usr/bin/env python3
"""
Generate workflow.real.yaml from workflow.chained.yaml: the route

    nextflow run nf-core/rnaseq -r 3.27.0 -profile singularity -c slurm.config -params-file params.yaml

takes on the bench ParallelCluster (tc-os scripts/bench/nfcore/rnaseq-real):
plain fasta and GTF, prebuilt STAR and Salmon indexes, transcript fasta and
gene BED given, featurecounts_group_type gene_type, no BBSplit. Tasks run as
Slurm jobs in Apptainer, with the per-process cpus / memory / time Nextflow
gives them there. The YAML header (HEAD below) lists every change.

Edges are rebuilt from the input ids, as gen_tuned.py does, and the result is
checked (see check()).

usage: gen_real.py [--cache deep|fast] [workflow.chained.yaml] [workflow.real[.<cache>].yaml]   (needs PyYAML)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

from gen_tuned import derive_edges, edge_set

HERE = Path(__file__).resolve().parent.parent

# Nextflow's singularity cache file for each image: the module's
# `workflow.containerEngine == 'singularity'` container string, named as
# SingularityCache.simpleName does. Once /fsx/sif is listed, a value can be
# replaced by the bare file name found there.
SIF = {
    "community.wave.seqera.io/library/coreutils_grep_gzip_lbzip2_pruned:838ba80435a629f8":
        ("coreutils", "https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/52/52ccce28d2ab928ab862e25aae26314d69c8e38bd41ca9431c67ef05221348aa/data"),
    "community.wave.seqera.io/library/python:3.14.5--dc8358b3c5eeb927":
        ("python314", "https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/18/1841daa69f98a0b0ffcb8f545070c8350a75febb167202136eab0990131d31c0/data"),
    "quay.io/biocontainers/python:3.12.12":
        ("python31212", "https://depot.galaxyproject.org/singularity/python:3.12.12"),
    "quay.io/biocontainers/python:3.10.4":
        ("python310", "https://depot.galaxyproject.org/singularity/python:3.10.4"),
    "community.wave.seqera.io/library/htslib_samtools:1.24--d697cfb9dce007cd":
        ("samtools", "https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/e9/e994bf4eb3731150511a14f5706b7bdfd64df1b6d40898fff334286c027e0859/data"),
    "community.wave.seqera.io/library/htslib_samtools_star_gawk:ae438e9a604351a4":
        ("star", "https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/26/268b4c9c6cbf8fa6606c9b7fd4fafce18bf2c931d1a809a0ce51b105ec06c89d/data"),
    "quay.io/biocontainers/fq:0.12.0--h9ee0642_0":
        ("fq", "https://depot.galaxyproject.org/singularity/fq:0.12.0--h9ee0642_0"),
    "community.wave.seqera.io/library/trim-galore:2.3.0--6a38a479b4972363":
        ("trimgalore", "https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/e0/e00369598bd6b7b34a7c83d5496c381104bf8b885c31a4b65b92e6ea2059fbb3/data"),
    "quay.io/biocontainers/fastqc:0.12.1--hdfd78af_0":
        ("fastqc", "https://depot.galaxyproject.org/singularity/fastqc:0.12.1--hdfd78af_0"),
    "community.wave.seqera.io/library/salmon:2.7.0--74784226202c61b9":
        ("salmon", "https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/1c/1ce42a19f9e7135babf14432e80b33ec717a13f14734d150d53347e979919629/data"),
    "community.wave.seqera.io/library/picard:3.5.0--842d4c70c98af9b4":
        ("picard", "https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/b4/b474c6f12c0502377b95062b75ef4b7778864b1353c7fc1d5a3b1f3b3017fd2e/data"),
    "community.wave.seqera.io/library/stringtie:3.0.3--e8043d00caecd051":
        ("stringtie", "https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/3f/3facd74a0f728c9bb9e9a731b58c343895d2dbdfeb812ce5747f701103fc61cf/data"),
    "community.wave.seqera.io/library/bedtools_coreutils:a623c13f66d5262b":
        ("bedtools", "https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/63/6397750e9730a3fbcc5b4c43f14bd141c64c723fd7dad80e47921a68a7c3cd21/data"),
    "quay.io/biocontainers/ucsc-bedclip:482--h0b57e2e_0":
        ("bedclip", "https://depot.galaxyproject.org/singularity/ucsc-bedclip:482--h0b57e2e_0"),
    "quay.io/biocontainers/ucsc-bedgraphtobigwig:482--hdc0a859_0":
        ("bigwig", "https://depot.galaxyproject.org/singularity/ucsc-bedgraphtobigwig:482--hdc0a859_0"),
    "quay.io/biocontainers/subread:2.1.1--h577a1d6_0":
        ("subread", "https://depot.galaxyproject.org/singularity/subread:2.1.1--h577a1d6_0"),
    "quay.io/biocontainers/qualimap:2.3--hdfd78af_0":
        ("qualimap", "https://depot.galaxyproject.org/singularity/qualimap:2.3--hdfd78af_0"),
    "community.wave.seqera.io/library/bioconductor-dupradar:1.38.0--831da16eb40a64ab":
        ("dupradar", "https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/24/24bb76357588d05b5637e2954f2dfb3ba04e3eb1ff52c927ffe1906d7d69915a/data"),
    "community.wave.seqera.io/library/rseqc_r-base:2e29d2dfda9cef15":
        ("rseqc", "https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/6f/6f44b7933e2c2b1a340dc9485869974eb032d34e81af83716eb381964ee3e5e7/data"),
    "community.wave.seqera.io/library/bioconductor-tximeta_jq:78bccd386c46a07c":
        ("tximeta", "https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/bd/bdba33f8ad1b2df156f8f6775279fb217ce0f8233a3dc637337245de9ad2f29f/data"),
    "quay.io/biocontainers/bioconductor-summarizedexperiment:1.32.0--r43hdfd78af_0":
        ("se", "https://depot.galaxyproject.org/singularity/bioconductor-summarizedexperiment:1.32.0--r43hdfd78af_0"),
    "community.wave.seqera.io/library/r-base_r-optparse_r-ggplot2_r-rcolorbrewer_pruned:9e75394d0bc21987":
        ("deseq2", "https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/1d/1d425b12748ce54c44c01a535a1ef5867a6e16cbf62c43151012e893444b1673/data"),
    "community.wave.seqera.io/library/multiqc:1.35--c17fb751507e9dfc":
        ("multiqc", "https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/c8/c8e346f4f6080eadf1253505e6ff09ef004454fc18e8d672006fd7b222cc412e/data"),
}
SIF_DIR = "/fsx/sif"
# nextflow.config `env` scope, exported into every task.
NF_ENV = {"PYTHONNOUSERSITE": "1", "R_PROFILE_USER": "/.Rprofile", "R_ENVIRON_USER": "/.Renviron",
          "JULIA_DEPOT_PATH": "/usr/local/share/julia"}

# conf/base.config labels capped by slurm.config resourceLimits (16 cpus, 58 GB,
# 24 h; STAR_ALIGN 8 cpus on highmem). trimgalore: conf/modules/trimgalore.config
# cpus/memory on a process_medium time. long: process_long, default cpus/memory.
MEM_CAP = 58
RES = {
    "single": {"cpus": 1, "memory_gb": 6, "walltime": "04:00:00"},
    "low": {"cpus": 2, "memory_gb": 12, "walltime": "04:00:00"},
    "medium": {"cpus": 6, "memory_gb": 36, "walltime": "08:00:00"},
    "high": {"cpus": 8, "memory_gb": 58, "walltime": "16:00:00"},
    "trimgalore": {"cpus": 8, "memory_gb": 4, "walltime": "08:00:00"},
    "long": {"cpus": 1, "memory_gb": 6, "walltime": "20:00:00"},
}
# What each label gave under -profile test (4 cpus / 15 GB): checks LABEL
# against the resources of the verified chained port.
TEST = {"single": (1, 6), "low": (2, 12), "medium": (4, 15), "high": (4, 15), "trimgalore": (4, 4), "long": (1, 6)}
LABEL = {
    "cat_fastq": "single", "lint_raw": "low", "fastqc_raw": "low", "trimgalore": "trimgalore",
    "lint_trimmed": "low", "subsample": "single", "salmon_strand": "medium",
    "star_align": "high", "salmon_quant": "medium", "salmon_bam": "medium",
    "sort": "medium", "sort_index": "low", "sort_flagstat": "single", "sort_idxstats": "single",
    "sort_stats": "single", "markdup": "medium", "md_index": "low", "md_flagstat": "single",
    "md_idxstats": "single", "md_stats": "single", "stringtie": "medium",
    "cov_fw": "single", "cov_rev": "single", "cov_both": "single",
    "clip_fw": "medium", "clip_rev": "medium", "clip_both": "medium",
    "bigwig_fw": "single", "bigwig_rev": "single", "bigwig_both": "single",
    "featurecounts": "medium", "biotype": "single", "qualimap_sort": "medium", "qualimap": "medium",
    "dupradar": "long", **{f"rseqc_{m}": "medium" for m in
                           ("bamstat", "infer", "innerdist", "junc_annot", "junc_sat", "readdist", "readdup")},
    "ss_tx2gene": "single", "ps_tx2gene": "single", "ss_tximport": "medium", "ps_tximport": "medium",
    "ss_se_gene": "medium", "ss_se_tx": "medium", "ps_se_gene": "medium", "ps_se_tx": "medium",
    "ss_deseq2": "medium", "ps_deseq2": "medium", "mqc_inputs": "single", "multiqc": "single",
    "gtf_filtered": "single", "faidx": "single",
}

SLURM_DIR = "@SLURM_DIR@"  # replaced by the driver (rnaseq-real/matrix.sh)
TARGETS = {
    "local": {"kind": "local"},
    "compute": {"kind": "slurm", "partition": "compute", "working_directory": SLURM_DIR, "inner": {"kind": "local"}},
    "highmem": {"kind": "slurm", "partition": "highmem", "working_directory": SLURM_DIR, "inner": {"kind": "local"}},
}
HIGHMEM = {"star_align"}
# Containers on the head node. None: every container task is a Slurm job, as in
# Nextflow. Until bench run real2 cat_fastq, subsample, salmon_strand and mqc_inputs
# ran here, and on real data they competed with the runtime for the head's 2 vCPUs.
LOCAL: set[str] = set()
MAX_CONCURRENCY = 200  # Nextflow's queueSize in slurm.config

# The reference prep tasks the given files replace, and the BBSplit steps.
DROP = {"fetch_reference", "add_fasta", "salmon_idx", "gtf", "genome", "gene_bed", "bbsplit_idx", "star_idx",
        "bbsplit", "lint_bbsplit", "fastqc_filtered"}
DROPPED_ARTS = {"add_fasta", "bbsplit_idx", "bbsplit", "lint_bbsplit", "fastqc_filtered", "fasta_url", "gtf_url",
                "transcript_fasta_url", "additional_fasta_url", "bbsplit_fasta_list_url", "salmon_index_url"}

PATTERN = '[^"`$\\\\]*'
# params.yaml (tc-os scripts/bench/nfcore/rnaseq-real) as string artifacts.
PARAMS = [
    ("fasta_path", "Genome fasta", "--fasta (plain, on the cluster's shared filesystem)", "/fsx/data/ref/genome.fa"),
    ("gtf_path", "GTF", "--gtf (plain)", "/fsx/data/ref/genes.gtf"),
    ("transcript_fasta_path", "Transcript fasta", "--transcript_fasta (plain)", "/fsx/prep/outdir/genome/genome.transcripts.fa"),
    ("gene_bed_path", "Gene BED", "--gene_bed (plain)", "/fsx/prep/outdir/genome/genes.filtered.bed"),
    ("star_index_path", "STAR index", "--star_index (directory)", "/fsx/prep/outdir/genome/index/star"),
    ("salmon_index_path", "Salmon index", "--salmon_index (directory)", "/fsx/prep/outdir/genome/index/salmon"),
    ("featurecounts_group_type", "featureCounts group type", "--featurecounts_group_type (biotype attribute)", "gene_type"),
]

LINK_REFERENCE = """\
set -eu
rm -rf ${reference} ${gtf} ${gene_bed} ${star_idx} ${salmon_idx}
mkdir -p ${reference} ${gtf} ${gene_bed} ${star_idx} ${salmon_idx}
for f in "${fasta_path}" "${gtf_path}" "${transcript_fasta_path}" "${gene_bed_path}"; do
    case $$f in *.gz) echo "$$f: gzipped references need the GUNZIP steps this variant drops" >&2; exit 1 ;; esac
    test -f "$$f"
done
test -d "${star_index_path}" && test -d "${salmon_index_path}"
ln -s "${fasta_path}" "${transcript_fasta_path}" ${reference}/
ln -s "${gtf_path}" ${gtf}/
ln -s "${gene_bed_path}" ${gene_bed}/
ln -s "${star_index_path}" ${star_idx}/star
ln -s "${salmon_index_path}" ${salmon_idx}/
# biotypeQcUsable: the biotype attribute on an exon row of the raw GTF
biotype_qc=$$(awk -F '\\t' -v b="${featurecounts_group_type}" \\
    '$$3 == "exon" { n = split($$NF, w, " "); for (i = 1; i <= n; i++) if (w[i] == b) { print "true"; exit } }' "${gtf_path}")
printf 'ref_fasta=%s\\nref_gtf=%s\\nref_transcript_fasta=%s\\nbiotype_qc=%s\\n' \\
    "$$(basename "${fasta_path}")" "$$(basename "${gtf_path}")" "$$(basename "${transcript_fasta_path}")" \\
    "$${biotype_qc:-false}" > ${reference}/refs.env
"""
LINK_GENOME = """\
set -eu
rm -rf ${genome} && mkdir -p ${genome}/out
. ${reference}/refs.env
g=$$(cd ${gtf_filtered} && ls *.gtf)
ln -s ${reference}/$$ref_fasta ${genome}/out/$$ref_fasta
ln -s ${gtf_filtered}/$$g ${genome}/out/$$g
"""

# TrimGalore's outputs, the reads every step after FQ_LINT_AFTER_TRIMMING gets.
READ_NAMES = [("_primary.fastq.gz", "_trimmed_trimmed.fq.gz"), ("_primary_1.fastq.gz", "_trimmed_1_val_1.fq.gz"),
              ("_primary_2.fastq.gz", "_trimmed_2_val_2.fq.gz")]

HEAD = """\
# Generated by scripts/gen_real.py from {src}; do not edit by hand.
#
# nf-core/rnaseq 3.27.0, the route `nextflow run nf-core/rnaseq -r 3.27.0
# -profile singularity -c slurm.config -params-file params.yaml` takes on the
# bench ParallelCluster (tc-os scripts/bench/nfcore/rnaseq-real): plain GENCODE
# fasta and GTF, prebuilt STAR and Salmon indexes, transcript fasta and gene BED
# given, featurecounts_group_type gene_type, no BBSplit. Same commands as the
# chained port ({src}, whose conventions hold), with these changes:
#
# - References: link_reference (head node) symlinks the given paths into the
#   folders GUNZIP_GTF, EAUTILS_GTF2BED, UNTAR_SALMON_INDEX and
#   STAR_GENOMEGENERATE wrote, and writes refs.env with biotype_qc
#   (biotypeQcUsable on the raw GTF). CUSTOM_GTFFILTER and SAMTOOLS_FAIDX still
#   run. With no additional fasta there is no CUSTOM_CATADDITIONALFASTA:
#   link_genome links the genome and the filtered GTF into genome/out/, and the
#   `ls *.fasta` lookups are `ls *.f*a` (genome.fa). Gzipped references and
#   tarred indexes are not handled: link_reference fails on them.
# - No BBSplit: STAR, Salmon and the strandedness probe read the TrimGalore reads
#   (<id>_trimmed_1_val_1.fq.gz, ...) once FQ_LINT_AFTER_TRIMMING passed.
#   FASTQC_FILTERED does not run on this route (it needs BBSplit or rRNA removal).
# - featureCounts and the biotype check use featurecounts_group_type.
# - Resources: base.config labels capped by slurm.config (16 cpus / 58 GB / 24 h):
#   STAR_ALIGN 8 cpus / 58 GB on partition highmem, everything else on compute,
#   one Slurm job per process as Nextflow submits them.
# - Containers: Apptainer with the .sif files Nextflow caches in /fsx/sif (named
#   after each module's singularity URL, SIF in gen_real.py), /fsx bound, the
#   nextflow.config `env` scope, and --cleanenv --no-home as Nextflow launches
#   singularity (`env -` and its default --no-home). Not its --pid: commands
#   write /tmp/.command.$$$$.sh on the host's shared /tmp, so PIDs must stay unique.
# - Head node (kind: local): only the shell glue Nextflow runs as Groovy there
#   (staging, links, filters, strandedness). Every container task is a Slurm
#   job, cat_fastq, subsample, salmon_strand and mqc_inputs included. For
#   single-run and known-strand samples the first three only pass meta.env on,
#   where Nextflow runs no job, so each still books its label on Slurm briefly.
# - Input cache mode: {cache}.
# - stage_inputs.py links local absolute read paths instead of copying them.
# - No capacity block; max_concurrency {mc} (Nextflow's queueSize), so Slurm queues.
# - Slurm working_directory is {slurm}; the driver replaces it (matrix.sh).
#
# {n} tasks ({maps} maps).
"""


KEYS = ("kind", "id", "name", "description", "over", "chain", "zip", "drop_exit_codes", "max_concurrency", "inputs",
        "outputs", "resources", "executor", "runtime", "target")


def sub(t: dict, old: str, new: str) -> None:
    cmd = t["runtime"]["command"]
    assert old in cmd, f"{t['id']}: {old!r} not in its command"
    t["runtime"]["command"] = cmd.replace(old, new)


def sif_name(url: str) -> str:
    """nextflow.container.SingularityCache.simpleName."""
    p = url.find("://")
    name = url[p + 3:] if p != -1 else url
    ext = ".img"
    if ".sif:" in name:
        ext, name = ".sif", name.replace(".sif:", "-")
    elif name.endswith(".sif"):
        ext, name = ".sif", name[:-4]
    return name.replace(":", "-").replace("/", "-") + ext


def build(doc: dict, cache: str | None = None) -> dict:
    canon: dict[str, dict] = {}  # one shared dict per artifact id, so the dump anchors it

    def art(a: dict) -> dict:
        c = canon.setdefault(a["id"], a)
        assert (c["kind"], c["path"]) == (a["kind"], a["path"]), a["id"]
        return c

    for t in doc["tasks"]:
        for key in ("inputs", "outputs"):
            t[key] = [art(a) for a in t.get(key, [])]
    params = {pid: art({"id": pid, "name": name, "kind": "string", "path": f"params/{pid}.txt"})
              for pid, name, _d, _v in PARAMS}

    res = {k: dict(v) for k, v in RES.items()}
    targets = {k: dict(v) for k, v in TARGETS.items()}
    img = {}
    for docker, (key, url) in SIF.items():
        img[docker] = {"kind": "apptainer", "image": f"{SIF_DIR}/{sif_name(url) if '://' in url else url}",
                       "binds": {"/fsx": "/fsx"}, "env": dict(NF_ENV), "extra_args": ["--cleanenv", "--no-home"]}

    link_reference = {
        "kind": "horus_task", "id": "link_reference", "name": "Link the given references",
        "description": "Stands in for the reference prep the given files make unnecessary: links them where those "
                       "steps wrote, and writes refs.env (file names, biotype_qc).",
        "inputs": list(params.values()),
        "outputs": [canon[i] for i in ("reference", "gtf", "gene_bed", "star_idx", "salmon_idx")],
        "executor": {"kind": "shell"}, "runtime": {"kind": "command", "command": LINK_REFERENCE},
    }
    link_genome = {
        "kind": "horus_task", "id": "link_genome", "name": "Link genome and filtered GTF",
        "description": "genome/out/ as CUSTOM_CATADDITIONALFASTA left it, without an additional fasta: the genome "
                       "and the CUSTOM_GTFFILTER output.",
        "inputs": [canon["reference"], canon["gtf_filtered"]], "outputs": [canon["genome"]],
        "executor": {"kind": "shell"}, "runtime": {"kind": "command", "command": LINK_GENOME},
    }

    out = []
    for t in doc["tasks"]:
        tid = t["id"]
        if tid == "fetch_reference":
            out.append(link_reference)
        if tid in DROP:
            continue
        if tid in ("subsample", "star_align", "salmon_quant"):
            # Read the trimmed reads, as nf passes them after FQ_LINT_AFTER_TRIMMING.
            t["over"] = {"input_id": "lint_trimmed", "as": t["over"]["as"]}
            t["zip"] = [z for z in t.get("zip", []) if z["input_id"] != "lint_bbsplit"] + [
                {"input_id": "trimgalore", "as": "trim"}]
            ins = [canon["lint_trimmed"] if a["id"] == "bbsplit" else a for a in t["inputs"] if a["id"] != "lint_bbsplit"]
            t["inputs"] = ins[:1] + [canon["trimgalore"]] + ins[1:]
            cmd = t["runtime"]["command"]
            t["runtime"]["command"] = cmd.replace("${sample}/$${id}_primary", "${trim}/$${id}_primary").replace(
                "ln -s ${sample}/$$f .", "ln -s ${trim}/$$f .")
            for old, new in READ_NAMES:
                sub(t, old, new)
        if tid == "set_strandedness":
            t["zip"] = [{"input_id": "lint_trimmed", "as": "lint"}]
            t["inputs"] = [canon["lint_trimmed"] if a["id"] == "lint_bbsplit" else a for a in t["inputs"]]
            t["description"] = t["description"].replace("FQ_LINT_AFTER_BBSPLIT", "FQ_LINT_AFTER_TRIMMING")
        if tid == "faidx":  # needs the genome only, not the filtered GTF in genome/out/
            sub(t, "fa=$$(cd ${genome}/out && ls *.fasta)\nln -s ${genome}/out/$$fa $$fa",
                ". ${reference}/refs.env; fa=$$ref_fasta\nln -s ${reference}/$$fa $$fa")
            t["inputs"] = [canon["reference"]]
        if tid == "featurecounts":
            sub(t, "-g gene_biotype", "-g ${featurecounts_group_type}")
            t["inputs"].append(params["featurecounts_group_type"])
        if tid == "multiqc":
            sub(t, "stage ${bbsplit}/*/*.stats.txt\n", "")
            sub(t, "stage ${fastqc_filtered}/*/*_fastqc.zip\n", "")
            t["inputs"] = [a for a in t["inputs"] if a["id"] not in ("bbsplit", "fastqc_filtered")]
        rt = t["runtime"]
        if "command" in rt:
            rt["command"] = rt["command"].replace("/tmp/.command.sh", "/tmp/.command.$$$$.sh").replace(
                "ls *.fasta", "ls *.f*a")
        shell = t["executor"]["kind"] == "shell"
        if not shell:
            assert TEST[LABEL[tid]] == (t["resources"]["cpus"], t["resources"]["memory_gb"]), tid
            t["resources"] = res[LABEL[tid]]
            t["executor"] = img[t["executor"]["image"]]
        t["target"] = targets["local" if shell or tid in LOCAL else "highmem" if tid in HIGHMEM else "compute"]
        if t["kind"] == "horus_map":
            t["max_concurrency"] = MAX_CONCURRENCY
        assert set(t) <= set(KEYS), set(t) - set(KEYS)
        out.append({k: t[k] for k in KEYS if k in t})  # a zip added above goes next to over
        if tid == "gtf_filtered":
            out.append(link_genome)
    for t in (link_reference, link_genome):
        t["target"] = targets["local"]

    used = {id(t["executor"]) for t in out}
    live = {id(a) for t in out for a in (*t.get("inputs", []), *t.get("outputs", []))}
    roots = [a for a in doc["artifacts"] if a["id"] not in DROPPED_ARTS]
    i = next(k for k, a in enumerate(roots) if a["id"] == "input_mirror") + 1
    roots[i:i] = [{**params[pid], "description": d, "value": v,
                   "pattern": "[A-Za-z0-9_]+" if pid == "featurecounts_group_type" else PATTERN}
                  for pid, _n, d, v in PARAMS]
    for a in roots:
        if a["id"] == "samplesheet":
            a["description"] = ("nf-core/rnaseq samplesheet (sample,fastq_1,fastq_2,strandedness). Reads may be URLs, "
                                "paths relative to the samplesheet, or absolute local paths (linked, not copied); "
                                "rows sharing a sample are runs of one sample.")
    new = {
        "kind": doc["kind"], "name": "nf-core rnaseq real", "max_concurrency": MAX_CONCURRENCY,
        **({"cache": cache} if cache else {}),
        "_targets": targets, "_res": res,
        "_img": {SIF[d][0]: e for d, e in img.items() if id(e) in used},
        "_art": [a for a in canon.values() if id(a) in live],
        "artifacts": roots, "tasks": out, "edges": [],
        "orchestrator_target": doc["orchestrator_target"],
    }
    new["edges"] = derive_edges(new)
    return new


def check(doc: dict) -> None:
    declared = {a["id"] for a in doc["artifacts"]}
    produced = {o["id"] for t in doc["tasks"] for o in t.get("outputs", [])}
    assert not declared & produced, declared & produced
    assert not {a["id"] for a in doc["_art"]} & DROPPED_ARTS
    for t in doc["tasks"]:
        tid, ins = t["id"], {a["id"] for a in t.get("inputs", [])}
        outs = {a["id"] for a in t.get("outputs", [])}
        assert not (ins | outs) & DROPPED_ARTS, (tid, (ins | outs) & DROPPED_ARTS)
        missing = ins - declared - produced
        assert not missing, f"{tid} reads {missing}, which nothing produces"
        names = {"task"} | ins | outs
        if t["kind"] == "horus_map":
            pairs = [t["over"], *t.get("zip", [])]
            assert {p["input_id"] for p in pairs} <= ins, tid
            names |= {p["as"] for p in pairs}
            assert t["max_concurrency"] == MAX_CONCURRENCY, tid
        cmd = t["runtime"].get("command", "") + t["runtime"].get("args", "")
        used = {m.group(1) for m in re.finditer(r"\$\$|\$\{([A-Za-z_]\w*)", cmd) if m.group(1)}
        assert used <= names, f"{tid} uses ${{{used - names}}}, not one of its artifacts"
        for bad in ("/tmp/.command.sh", "_primary", "*.fasta", "bbsplit", "fastqc_filtered", "gene_biotype"):
            assert bad not in cmd, (tid, bad)
        assert cmd.count("/tmp/.command.$$$$.sh") in (0, 2), tid
        tg, ex = t["target"], t["executor"]
        if ex["kind"] == "shell":
            assert tg["kind"] == "local", tid
            continue
        assert ex["kind"] == "apptainer" and ex["image"].startswith(SIF_DIR + "/"), tid
        r = t["resources"]
        assert r["memory_gb"] <= MEM_CAP and r["cpus"] <= (8 if tid == "star_align" else 16), (tid, r)
        if tg["kind"] == "slurm":
            assert tg["working_directory"] == SLURM_DIR, tid
            assert tg["partition"] == ("highmem" if tid == "star_align" else "compute"), tid
        else:
            assert tid in LOCAL, tid
    star = next(t for t in doc["tasks"] if t["id"] == "star_align")
    assert star["target"]["partition"] == "highmem" and star["resources"] == RES["high"]
    assert "capacity" not in doc
    assert edge_set(derive_edges(doc)) == edge_set(doc["edges"])


class Dumper(yaml.SafeDumper):
    names: dict[int, str] = {}

    def generate_anchor(self, node):
        for key, n in self.represented_objects.items():
            if n is node and key in self.names:
                return self.names[key]
        raise AssertionError(f"unnamed shared object: {node}")


def _scalar(v) -> bool:
    return isinstance(v, (str, int, float, bool)) and "\n" not in str(v)


def _dict(d: Dumper, data: dict):
    node = d.represent_mapping("tag:yaml.org,2002:map", data)
    node.flow_style = all(_scalar(v) for v in data.values()) and len(str(data)) < 200
    return node


def _list(d: Dumper, data: list):
    node = d.represent_sequence("tag:yaml.org,2002:seq", data)
    node.flow_style = all(_scalar(v) for v in data)
    return node


Dumper.add_representer(str, lambda d, s: d.represent_scalar("tag:yaml.org,2002:str", s, style="|" if "\n" in s else None))
Dumper.add_representer(dict, _dict)
Dumper.add_representer(list, _list)


def dump(doc: dict) -> str:
    names = {id(v): f"t_{k}" for k, v in doc["_targets"].items()}
    names |= {id(v): f"res_{k}" for k, v in doc["_res"].items()}
    names |= {id(v): f"img_{k}" for k, v in doc["_img"].items()}
    names |= {id(a): f"a_{a['id']}" for a in doc["_art"]}
    Dumper.names = names
    return yaml.dump(doc, Dumper=Dumper, sort_keys=False, width=4096, allow_unicode=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate the real-data rnaseq port.")
    ap.add_argument("--cache", choices=("deep", "fast"), help="workflow-level input cache mode (runtime default: deep)")
    ap.add_argument("src", nargs="?", type=Path, default=HERE / "workflow.chained.yaml")
    ap.add_argument("dst", nargs="?", type=Path)
    a = ap.parse_args()
    src = a.src
    dst = a.dst or HERE / (f"workflow.real.{a.cache}.yaml" if a.cache else "workflow.real.yaml")
    doc = yaml.safe_load(src.read_text())
    assert edge_set(derive_edges(doc)) == edge_set(doc["edges"]), f"{src.name} edges differ from its input ids"
    new = build(doc, a.cache)
    assert new.get("cache") == a.cache
    check(new)
    text = dump(new)
    check(yaml.safe_load(text))  # the dumped file reads back the same
    maps = sum(t["kind"] == "horus_map" for t in new["tasks"])
    dst.write_text(HEAD.format(src=src.name, mc=MAX_CONCURRENCY, slurm=SLURM_DIR, n=len(new["tasks"]), maps=maps,
                               cache=f"cache: {a.cache}" if a.cache else "runtime default (deep)")
                   + text)
    print(f"wrote {dst}: {len(new['tasks'])} tasks, {maps} maps")
    return 0


if __name__ == "__main__":
    sys.exit(main())
