#!/usr/bin/env python3
"""
Generate workflow.yaml from the harvested nf-core/ampliseq 3.1.0 run.

Every Nextflow process becomes a Horus task that runs the rendered
``.command.sh`` of that process verbatim (spec.json ``script``), in the same
image, with the same cpus/memory. The task's command

1. links the process's inputs into the output folder under the names
   Nextflow staged them as (``lnas <name> <upstream file>``),
2. writes the script to ``/tmp/.command.sh`` and runs it with the
   pipeline's ``process.shell`` (``bash -C -e -u -o pipefail``) or
   ``Rscript``, as ``.command.run`` does,
3. removes the links again.

Values that differ per map slot (sample id, run, read direction, metadata
column, ...) are ``@NAME@`` placeholders in the script, filled in with sed
from the slot's meta file. Inputs are found by file name: a single task's
output is ``${art}/<file>``, a map's is ``${art}/*/<file>``.

stdlib only. Usage:
    gen_workflow.py --spec <tc-os>/scripts/bench/nfcore/ampliseq/spec.json > workflow.yaml
"""

from __future__ import annotations

import argparse
import json
import re
import sys

ENV = (
    "export PYTHONNOUSERSITE=1 R_PROFILE_USER=/.Rprofile R_ENVIRON_USER=/.Renviron "
    "JULIA_DEPOT_PATH=/usr/local/share/julia"
)
HELPERS = r"""lnas() { d=$$1; shift; if [ $$# -ne 1 ] || [ ! -e "$$1" ]; then echo "stage $$d: need one input, got: $$*" >&2; exit 1; fi; mkdir -p "$$(dirname "$$d")"; ln -s "$$1" "$$d"; echo "$$d" >> /tmp/.staged; }
lnk() { ld=$$1; shift; for lf in "$$@"; do lnas "$$ld/$${lf##*/}" "$$lf"; done; }"""

IMAGES = {
    "bash_coreutils_findutils_gawk_pruned": "coreutils",
    "bioconductor-dada2": "dada2",
    "bioconductor-decontam": "decontam",
    "duckdb-cli": "duckdb",
    "multiqc:": "multiqc",
    "r-base_r-data.table": "rtables",
    "samtools_vsearch": "vsearch",
    "barrnap": "barrnap",
    "bioconductor-biostrings": "biostrings",
    "bioconductor-phyloseq": "phyloseq",
    "bioconductor-treesummarizedexperiment": "tse",
    "cutadapt": "cutadapt",
    "fastqc": "fastqc",
    "mulled-v2-b2ec": "rmarkdown",
    "pandas": "pandas",
    "python:3.8.3": "python38",
    "python:3.9": "python39",
    "r-base:4.2.1": "rbase",
    "nf-core/ubuntu": "ubuntu",
    "qiime2/qiime2": "qiime2",
}

PAT = "pattern: '[^\"`$\\\\]*', "  # no quotes, backticks, $ or backslashes
# Root artifacts: (id, name, kind, path, extra)
ROOT = [
    ("samplesheet", "Samplesheet", "file", "examples/Samplesheet_v3.tsv",
     'description: "--input: sample, fastq_1, fastq_2 and optional run, control, quant_reading (tab separated). Default: the test profile samplesheet (4 paired-end samples)."'),
    ("nfcore", "nf-core/ampliseq files", "folder", "nfcore/",
     'description: "nf-core/ampliseq 3.1.0 bin/ scripts and report assets (MIT)."'),
    ("metadata_url", "Metadata", "string", "params/metadata_url.txt",
     PAT + 'description: "--metadata", value: "https://raw.githubusercontent.com/nf-core/test-datasets/ampliseq/samplesheets/Metadata.tsv"'),
    ("dada_ref_urls", "DADA2 reference", "string", "params/dada_ref_urls.txt",
     PAT + 'description: "--dada_ref_taxonomy gtdb=R07-RS207 files, comma separated", value: "https://data.gtdb.ecogenomic.org/releases/release207/207.0/genomic_files_reps/bac120_ssu_reps_r207.tar.gz,https://data.gtdb.ecogenomic.org/releases/release207/207.0/genomic_files_reps/ar53_ssu_reps_r207.tar.gz"'),
    ("qiime_ref_urls", "QIIME2 reference", "string", "params/qiime_ref_urls.txt",
     PAT + 'description: "--qiime_ref_taxonomy greengenes85 files, comma separated", value: "https://data.qiime2.org/2023.7/tutorials/training-feature-classifiers/85_otus.fasta,https://data.qiime2.org/2023.7/tutorials/training-feature-classifiers/85_otu_taxonomy.txt"'),
    ("input_mirror", "Local input mirror", "string", "params/input_mirror.txt",
     PAT + 'description: "Folder searched for each input file by name before downloading it. Empty downloads everything.", value: ""'),
]

# id -> (name, path) for every folder an internal task writes.
ART: dict[str, tuple[str, str]] = {}


class Task:
    def __init__(self, id, proc, *, tag=None, full=None, name=None, over=None, inputs=(), outputs=None,
                 subs=(), path_subs=None, skip=(), stage=(), pre="", post="", stdout=None, image=None, runtime=None,
                 executor=None, comment=None):
        self.id, self.proc, self.tag, self.full = id, proc, tag, full
        self.name = name or proc
        self.over = over          # (artifact id, as)
        self.inputs = list(inputs)  # extra input artifact ids (beyond auto-detected ones)
        self.outputs = outputs or [id]
        self.subs = list(subs)    # (regex, VAR): VAR is a shell variable set in pre
        self.path_subs = list(path_subs or subs)  # the same for staged file names, when the regex differs
        self.skip = list(skip)    # regexes of staged input paths to stage by hand
        self.stage = list(stage)  # hand-written stage lines
        self.pre, self.post, self.stdout = pre, post, stdout
        self.image, self.runtime, self.executor, self.comment = image, runtime, executor, comment


def proc_spec(spec, t: Task):
    cands = [p for p in spec["processes"] if p["name"] == t.proc]
    if t.full:
        cands = [p for p in cands if t.full in p["full_names"]]
    (p,) = cands
    tasks = p["per_task"]
    task = next(x for x in tasks if x["tag"] == t.tag) if t.tag else tasks[0]
    return p, task


def gb(mem: str) -> int:
    v, unit = mem.split()
    assert unit == "GB", mem
    return int(float(v))


def sub_text(text: str, subs, fmt) -> str:
    for rx, var in subs:
        text = re.sub(rx, fmt(var), text)
    return text


def interpreter(script: str) -> str:
    first = script.splitlines()[0]
    if first == "#!/usr/bin/env bash -C -e -u -o pipefail":
        return "bash -C -e -u -o pipefail"
    if first == "#!/usr/bin/env Rscript":
        return "Rscript"
    raise SystemExit(f"unknown shebang {first!r}")


def source_of(inp, producers, t: Task) -> str | None:
    """Shell path of a staged input, or None to stage it by hand."""
    if any(re.search(rx, inp["path"]) for rx in t.skip):
        return None
    if "from_process" in inp:
        key = (inp["from_process"], inp.get("from_tag"))
        tid, is_map = producers.get(key) or producers[(inp["from_process"], None)]
        art = tid
        return f"${{{art}}}/" + ("*/" if is_map else "") + inp["file"]
    if "pipeline_asset" in inp:
        return "${nfcore}/" + inp["pipeline_asset"]
    name = inp["path"].rsplit("/", 1)[-1]
    if name == "ASV_tax_species.gtdb_R07-RS207.tsv":
        return "${dada2_addspecies}/ASV_tax_species.gtdb_R07-RS207.tsv"
    if name == "decontam_metadata.tsv" or name == "Metadata.tsv":
        return "${reference}/" + name
    if name == "Samplesheet_v3.tsv":
        return "${samplesheet}"
    raise SystemExit(f"{t.id}: no source for input {inp}")


def build_command(spec, t: Task, producers) -> tuple[str, set[str]]:
    p, task = proc_spec(spec, t)
    script = task["script"]
    used = set()
    stage = []
    for inp in task["inputs"]:
        src = source_of(inp, producers, t)
        if src is None:
            continue
        used.update(re.findall(r"(?<!\$)\$\{(\w+)\}", src))
        dest = sub_text(inp["path"], t.path_subs, lambda v: f"$${{{v}}}")
        src = sub_text(src, t.path_subs, lambda v: f"$${{{v}}}")
        stage.append(f'lnas "{dest}" {src}')
    for line in t.stage:
        used.update(re.findall(r"(?<!\$)\$\{(\w+)\}", line))
    body = sub_text(script, t.subs, lambda v: f"@{v}@").replace("$", "$$")
    seds = [f'sed -i "s|@{v}@|$${v}|g" /tmp/.command.sh' for v in dict.fromkeys(v for _rx, v in t.subs)]
    run = f"{interpreter(script)} /tmp/.command.sh"
    if t.stdout:
        run += f" > {t.stdout}"
    out = f"${{{t.outputs[0]}}}"
    lines = ["set -eu", ENV, 'export PATH="$$PATH:${nfcore}/bin"', ": > /tmp/.staged", HELPERS]
    if t.pre:
        lines.append(t.pre.strip())
    lines += [f"rm -rf {out} && mkdir -p {out} && cd {out}"]
    lines += stage + list(t.stage)
    lines += ["cat > /tmp/.command.sh <<'NF'", body.rstrip("\n"), "NF"] + seds + [run]
    lines.append('while read -r f; do rm -f "$$f"; done < /tmp/.staged')
    if t.post:
        lines.append(t.post.strip())
    used.update(re.findall(r"(?<!\$)\$\{(\w+)\}", (t.pre or "") + (t.post or "")))
    used.add("nfcore")
    if t.over:
        used.discard(t.over[1])  # the map slot, not an artifact
    return "\n".join(lines), used, p


def tasks() -> list[Task]:
    S = [(r"sampleID_1a", "id")]
    D = [(r"\bFW\b|(?<=\")FW|FW(?=_)", "direction")]
    RUN = [(r"(?<=\")1(?=[._])", "run")]
    RUNP = [(r"(?:(?<=^)|(?<=/))1(?=[._])", "run")]
    T = Task
    return [
        # ------------------------------------------------------------ inputs
        T("stage_inputs", None, name="Stage the reads, metadata and references",
          outputs=["reads", "samples", "runs", "directions", "reference"],
          inputs=["samplesheet", "metadata_url", "dada_ref_urls", "qiime_ref_urls", "input_mirror"],
          runtime="""kind: python_script
      script: scripts/stage_inputs.py
      python: python3 # stdlib only
      args: --samplesheet ${samplesheet} --metadata ${metadata_url} --ref ${dada_ref_urls} --ref ${qiime_ref_urls} --mirror ${input_mirror} --reads ${reads} --samples ${samples} --runs ${runs} --directions ${directions} --reference ${reference}"""),
        T("format_taxonomy", "FORMAT_TAXONOMY", skip=[r"\.tar\.gz$"],
          stage=["for f in $$(echo ${dada_ref_urls} | tr ',' ' '); do lnas $${f##*/} ${reference}/$${f##*/}; done"],
          inputs=["dada_ref_urls"]),
        T("format_taxonomy_qiime", "FORMAT_TAXONOMY_QIIME", skip=[r"."],
          # the format script renames its inputs: copy them, as links would dangle
          stage=["for f in $$(echo ${qiime_ref_urls} | tr ',' ' '); do cp ${reference}/$${f##*/} .; done"],
          inputs=["qiime_ref_urls"]),
        # ------------------------------------------------------------ per sample
        T("fastqc", "FASTQC", over=("samples", "sample"), subs=S, skip=[r"."],
          pre=". ${sample}",
          stage=["lnas 1/$${id}_1.fastq.gz ${reads}/$${id}/$${id}_1.fastq.gz",
                 "lnas 2/$${id}_2.fastq.gz ${reads}/$${id}/$${id}_2.fastq.gz"],
          post="rm -f $${id}_1.gz $${id}_2.gz && rmdir 1 2"),
        T("cutadapt", "CUTADAPT_BASIC", over=("samples", "sample"), subs=S, skip=[r"."],
          pre=". ${sample}",
          stage=["lnk . ${reads}/$${id}/$${id}_1.fastq.gz ${reads}/$${id}/$${id}_2.fastq.gz"]),
        T("cutadapt_summary", "CUTADAPT_SUMMARY_STD", skip=[r"."], stage=["lnk . ${cutadapt}/*/*.cutadapt.log"]),
        T("cutadapt_summary_merge", "CUTADAPT_SUMMARY_MERGE"),
        # ------------------------------------------------------------ DADA2 preprocessing
        T("dada2_quality1", "DADA2_QUALITY1", tag="FW", over=("directions", "direction"), subs=D, skip=[r"."],
          pre='. ${direction}; n=1; [ $$direction = RV ] && n=2',
          stage=["lnk . ${cutadapt}/*/*.trimmed_$${n}.trim.fastq.gz"]),
        T("trunclen", "TRUNCLEN", tag="FW", over=("directions", "direction"), subs=D,
          pre=". ${direction}", stdout="$${direction}.trunc.txt"),
        T("dada2_filtntrim", "DADA2_FILTNTRIM", over=("samples", "sample"),
          subs=S + [(r"230, 229", "trunc")], inputs=["trunclen"],
          pre='. ${sample}; trunc="$$(cat ${trunclen}/*/FW.trunc.txt), $$(cat ${trunclen}/*/RV.trunc.txt)"'),
        T("dada2_quality2", "DADA2_QUALITY2", tag="FW", over=("directions", "direction"), subs=D, skip=[r"."],
          pre='. ${direction}; n=1; [ $$direction = RV ] && n=2',
          stage=["lnk . ${dada2_filtntrim}/*/*_$${n}.filt.fastq.gz"]),
        # ------------------------------------------------------------ DADA2 per run
        T("dada2_err", "DADA2_ERR", over=("runs", "run_item"), subs=RUN, skip=[r"."],
          pre=". ${run_item}",
          stage=["for s in $$samples; do lnk . ${dada2_filtntrim}/*/$${s}_1.filt.fastq.gz ${dada2_filtntrim}/*/$${s}_2.filt.fastq.gz; done"],
          inputs=["dada2_filtntrim"]),
        T("dada2_denoising", "DADA2_DENOISING", over=("runs", "run_item"), path_subs=RUNP, subs=RUN, skip=[r"^filtered/"],
          pre=". ${run_item}",
          stage=["for s in $$samples; do lnk filtered ${dada2_filtntrim}/*/$${s}_1.filt.fastq.gz ${dada2_filtntrim}/*/$${s}_2.filt.fastq.gz; done"],
          inputs=["dada2_filtntrim"], post="rmdir filtered"),
        T("dada2_rmchimera", "DADA2_RMCHIMERA", over=("runs", "run_item"), path_subs=RUNP,
          subs=RUN + [(r"(?<=if \( )4(?= == 1 \))", "nsamples"), (r"(?<=<- \")sampleID_1(?=\" \})", "first")],
          pre='. ${run_item}; set -- $$samples; nsamples=$$#; first=$$1'),
        T("dada2_stats", "DADA2_STATS", over=("runs", "run_item"), path_subs=RUNP, subs=RUN, skip=[r"^filter_and_trim_files/"],
          pre=". ${run_item}",
          stage=["for s in $$samples; do lnk filter_and_trim_files ${dada2_filtntrim}/*/$${s}.filter_stats.tsv; done"],
          inputs=["dada2_filtntrim"], post="rmdir filter_and_trim_files"),
        T("dada2_merge", "DADA2_MERGE", skip=[r"."],
          stage=["lnk . ${dada2_stats}/*/*.stats.tsv ${dada2_rmchimera}/*/*.ASVtable.rds"]),
        T("merge_stats_dada", "MERGE_STATS_DADA"),
        T("summary_table_counts", "SUMMARY_TABLE_COUNTS"),
        T("duckdb_counts", "DUCKDB_TABLE2PARQUET", tag="ampliseq.counts"),
        # ------------------------------------------------------------ ASV post-processing
        T("vsearch_cluster", "VSEARCH_CLUSTER"),
        T("filter_clusters", "FILTER_CLUSTERS", skip=[r"clusters\.fasta"],
          subs=[(r"(?<=echo ')ASV_post_clustering\.clusters\.fasta[^']*(?=')", "clusters")],
          stage=["lnk . ${vsearch_cluster}/ASV_post_clustering.clusters.fasta*.gz",
                 "clusters=$$(ls ASV_post_clustering.clusters.fasta*.gz | LC_ALL=C sort | tr '\\n' ' ' | sed 's/ $$//')"]),
        T("decontam", "DECONTAM"),
        T("merge_stats_decontam", "MERGE_STATS_DECONTAM"),
        T("filter_seq_abund", "FILTER_SEQUENCES_ABUNDANCES"),
        T("barrnap", "BARRNAP"),
        T("barrnapsummary", "BARRNAPSUMMARY"),
        T("filter_ssu", "FILTER_SSU"),
        T("merge_stats_filterssu", "MERGE_STATS_FILTERSSU"),
        T("filter_len_asv", "FILTER_LEN_ASV", post="rmdir input"),
        T("merge_stats_filterlenasv", "MERGE_STATS_FILTERLENASV"),
        # ------------------------------------------------------------ DADA2 taxonomy
        T("cutadapt_taxonomy", "CUTADAPT_TAXONOMY"),
        # shortcut: one chunk (splitFasta by 10000, --dada_assign_chunksize); fails above that, split here when needed
        T("dada2_taxonomy", "DADA2_TAXONOMY", skip=[r"^ASV_seqs\.len\.1\.fasta$"],
          stage=['[ "$$(grep -c "^>" ${filter_len_asv}/ASV_seqs.len.fasta)" -le 10000 ] || { echo "more than 10000 ASVs: chunking not ported" >&2; exit 1; }',
                 "cp ${filter_len_asv}/ASV_seqs.len.fasta ASV_seqs.len.1.fasta"],
          inputs=["filter_len_asv"],
          post="cp ASV_seqs.len.1.ASV_tax.gtdb_R07-RS207.tsv ASV_tax.gtdb_R07-RS207.tsv  # collectFile of the chunks"),
        T("dada2_addspecies", "DADA2_ADDSPECIES",
          post="cp ASV_seqs.len.1.ASV_tax.gtdb_R07-RS207.species.tsv ASV_tax_species.gtdb_R07-RS207.tsv  # collectFile of the chunks"),
        # ------------------------------------------------------------ QIIME2 taxonomy
        T("qiime2_extract", "QIIME2_EXTRACT", skip=[r"."],
          stage=["lnas greengenes85.fna ${format_taxonomy_qiime}/greengenes85.fna",
                 "lnas greengenes85.tax ${format_taxonomy_qiime}/greengenes85.tax"],
          inputs=["format_taxonomy_qiime"]),
        T("qiime2_train", "QIIME2_TRAIN"),
        T("qiime2_inseq_tax", "QIIME2_TAXONOMY:QIIME2_INSEQ"),
        T("qiime2_classify", "QIIME2_CLASSIFY"),
        T("phyloseq_intax_qiime2", "PHYLOSEQ_INTAX_QIIME2"),
        T("qiime2_inseq", "AMPLISEQ:QIIME2_INSEQ"),
        T("build_asv_annotations", "BUILD_ASV_ANNOTATIONS"),
        T("summary_table_tax_qiime2", "SUMMARY_TABLE_TAXONOMY", tag="QIIME2.greengenes85"),
        T("summary_table_tax_dada2", "SUMMARY_TABLE_TAXONOMY", tag="DADA2.gtdb_R07-RS207", inputs=["dada2_addspecies"]),
        T("duckdb_tax_qiime2", "DUCKDB_TABLE2PARQUET", tag="ampliseq.taxonomy.QIIME2.greengenes85"),
        T("duckdb_tax_dada2", "DUCKDB_TABLE2PARQUET", tag="ampliseq.taxonomy.DADA2.gtdb_R07-RS207"),
        # ------------------------------------------------------------ QIIME2 tables
        T("filter_samples", "FILTER_SAMPLES", post="rmdir input"),
        T("metadata_all", "METADATA_ALL", stdout="category.txt"),
        T("metadata_pairwise", "METADATA_PAIRWISE", stdout="category.txt"),
        T("decide", None, name="Fan out the QIIME2 statistics",
          outputs=["l_ancom", "l_ancom_tax", "l_formula", "l_formula_tax", "l_formula2", "l_formula2_tax",
                   "l_alpha", "l_betaord", "l_beta", "l_adonis"],
          inputs=["metadata_all", "metadata_pairwise"],
          runtime="""kind: python_script
      script: scripts/decide.py
      python: python3 # stdlib only
      # --qiime_adonis_formula, --ancombc_formula, --ancombc2_formula, --tax_agglom_min/max of the test profile
      args: --all ${metadata_all}/category.txt --pairwise ${metadata_pairwise}/category.txt --adonis-formula treatment1,mix8 --ancombc-formula treatment1 --ancombc2-formula treatment1 --tax-agglom-min 2 --tax-agglom-max 2 --out ancom=${l_ancom} --out ancom_tax=${l_ancom_tax} --out formula=${l_formula} --out formula_tax=${l_formula_tax} --out formula2=${l_formula2} --out formula2_tax=${l_formula2_tax} --out alpha=${l_alpha} --out betaord=${l_betaord} --out beta=${l_beta} --out adonis=${l_adonis}"""),
        T("qiime2_inasv", "QIIME2_INASV"),
        T("qiime2_intax", "QIIME2_INTAX", inputs=["dada2_addspecies"]),
        T("tablefiltertaxa", "QIIME2_TABLEFILTERTAXA"),
        T("seqfiltertable", "QIIME2_SEQFILTERTABLE"),
        T("filter_stats", "FILTER_STATS"),
        T("merge_stats_filtertaxa", "MERGE_STATS_FILTERTAXA"),
        T("barplot", "QIIME2_BARPLOT"),
        T("export_relasv", "QIIME2_EXPORT_RELASV"),
        T("export_reltax", "QIIME2_EXPORT_RELTAX"),
        T("export_absolute", "QIIME2_EXPORT_ABSOLUTE"),
        T("phyloseq_inasv", "PHYLOSEQ_INASV"),
        T("inasv_bpavg", "QIIME2_INASV_BPAVG"),
        T("featuretable_group", "QIIME2_FEATURETABLE_GROUP"),
        T("bpavg", "QIIME2_BPAVG"),
        T("combine_table_qiime2", "COMBINE_TABLE", tag="QIIME2-greengenes85"),
        T("combine_table_dada2", "COMBINE_TABLE", tag="DADA2-gtdb_R07-RS207", inputs=["dada2_addspecies"]),
        # ------------------------------------------------------------ diversity
        T("qiime2_tree", "QIIME2_TREE"),
        T("alpha_rarefaction", "QIIME2_ALPHARAREFACTION"),
        T("diversity_core", "QIIME2_DIVERSITY_CORE"),
        T("diversity_alpha", "QIIME2_DIVERSITY_ALPHA", tag="evenness_vector", over=("l_alpha", "item"),
          subs=[(r"evenness_vector", "name")], pre=". ${item}"),
        T("diversity_betaord", "QIIME2_DIVERSITY_BETAORD", tag="bray_curtis_pcoa_results", over=("l_betaord", "item"),
          subs=[(r"bray_curtis_pcoa_results", "name")], pre=". ${item}"),
        T("diversity_beta", "QIIME2_DIVERSITY_BETA", tag="bray_curtis_distance_matrix-treatment1", over=("l_beta", "item"),
          subs=[(r"bray_curtis_distance_matrix", "matrix"), (r"treatment1", "col")], pre=". ${item}"),
        T("diversity_adonis", "QIIME2_DIVERSITY_ADONIS", tag="bray_curtis_distance_matrix-treatment1", over=("l_adonis", "item"),
          subs=[(r"bray_curtis_distance_matrix", "matrix"), (r"treatment1", "formula")], pre=". ${item}"),
        # ------------------------------------------------------------ differential abundance
        T("filtersamples_ancom", "QIIME2_FILTERSAMPLES_ANCOM", tag="treatment1", over=("l_ancom", "item"),
          subs=[(r"treatment1", "col")], pre=". ${item}"),
        T("ancombc_asv", "QIIME2_ANCOMBC_ASV", tag="treatment1-", over=("l_ancom", "item"),
          subs=[(r"treatment1", "col")], pre=". ${item}"),
        T("ancombc_tax", "QIIME2_ANCOMBC_TAX", tag="treatment1--2", over=("l_ancom_tax", "item"),
          subs=[(r"treatment1", "col"), (r"(?<=lvl)2|(?<=level )2|(?<=level-)2|(?<=--p-level )2|(?<=echo )2", "level")],
          pre=". ${item}"),
        T("ancombc2_asv", "QIIME2_ANCOMBC2_ASV", tag="treatment1-", over=("l_ancom", "item"),
          subs=[(r"treatment1", "col")], pre=". ${item}"),
        T("ancombc2_tax", "QIIME2_ANCOMBC2_TAX", tag="treatment1--2", over=("l_ancom_tax", "item"),
          subs=[(r"treatment1", "col"), (r"(?<=lvl)2|(?<=level )2|(?<=level-)2|(?<=--p-level )2|(?<=echo )2", "level")],
          pre=". ${item}"),
        # --ancombc_formula_reflvl / --ancombc2_formula_reflvl (treatment1::b) stay as rendered
        T("ancombc_formula_asv", "ANCOMBC_FORMULA_ASV", over=("l_formula", "item"),
          subs=[(r"treatment1(?!::)", "formula")], pre=". ${item}"),
        T("ancombc_formula_tax", "ANCOMBC_FORMULA_TAX", over=("l_formula_tax", "item"),
          subs=[(r"treatment1(?!::)", "formula"), (r"(?<=lvl)2|(?<=level )2|(?<=level-)2|(?<=--p-level )2|(?<=echo )2", "level")],
          pre=". ${item}"),
        T("ancombc2_formula_asv", "ANCOMBC2_FORMULA_ASV", over=("l_formula2", "item"),
          subs=[(r"treatment1(?!::)", "formula")], pre=". ${item}"),
        T("ancombc2_formula_tax", "ANCOMBC2_FORMULA_TAX", over=("l_formula2_tax", "item"),
          subs=[(r"treatment1(?!::)", "formula"), (r"(?<=lvl)2|(?<=level )2|(?<=level-)2|(?<=--p-level )2|(?<=echo )2", "level")],
          pre=". ${item}"),
        # ------------------------------------------------------------ R objects
        T("tse_qiime2", "TREESUMMARIZEDEXPERIMENT", tag="qiime2"),
        T("tse_dada2", "TREESUMMARIZEDEXPERIMENT", tag="dada2", inputs=["dada2_addspecies"]),
        T("phyloseq_qiime2", "PHYLOSEQ", tag="qiime2"),
        T("phyloseq_dada2", "PHYLOSEQ", tag="dada2", inputs=["dada2_addspecies"]),
        # ------------------------------------------------------------ reports
        T("multiqc", "MULTIQC", skip=[r"."],
          # multiqc_config.yml plus the FastQC zips and Cutadapt logs, one numbered dir each, as Nextflow stages them.
          # The workflow summary, methods and software versions sections come from Nextflow run metadata: left out.
          stage=['n=1; lnas 1/multiqc_config.yml ${nfcore}/assets/multiqc_config.yml',
                 'for f in ${fastqc}/*/*_fastqc.zip ${cutadapt}/*/*.cutadapt.log; do n=$$((n + 1)); lnas $$n/$${f##*/} $$f; done'],
          inputs=["fastqc", "cutadapt"], post="rmdir $$(seq 1 $$n)"),
        report_task(),
    ]


def report_task() -> Task:
    """SUMMARY_REPORT: the data-derived render params are computed from the staged files."""
    lists = {
        "dada_err_path": "$$(ls *.err.svg | paste -sd,)",
        "dada_err_run": "$$(ls ${runs} | paste -sd,)",
        "qiime2_filtertaxa": "$$(wc -l < ${filter_samples}/table.tsv),$$(wc -l < ${tablefiltertaxa}/filtered-table.tsv)",
        "diversity_indices_depth": "$$(cd ${diversity_core} && ls *rarefaction.txt)",
        "diversity_indices_beta": "$$(ls -d beta_diversity/*_distance_matrix-* | paste -sd,)",
        "diversity_indices_adonis": "$$(ls -d beta_diversity/adonis/* | paste -sd,)",
        "ancombc": "$$(ls -d ancombc/da_barplot/* | paste -sd,)",
        "ancombc_formula": "$$(ls -d ancombc_formula/da_barplot/* | paste -sd,)",
        "ancombc2": "$$(ls ancombc2/* | paste -sd,)",
        "ancombc2_formula": "$$(ls ancombc2_formula/* | paste -sd,)",
        "phyloseq": "$$(ls phyloseq/* | paste -sd,)",
        "tse": "$$(ls tse/* | paste -sd,)",
    }
    subs = [(rf"(?<=[(,]){k}='[^']*'", f"NF_{k}") for k in lists]
    stage = [
        "lnk . ${dada2_quality1}/*/*_qual_stats.svg ${dada2_quality2}/*/*_preprocessed_qual_stats.svg ${dada2_err}/*/*.err.svg",
        "lnas filterAndTrim.args.txt $$(ls ${dada2_filtntrim}/*/filterAndTrim.args.txt | head -1)",
        "lnk . ${barplot}/barplot/*",
        "lnk . ${diversity_core}/*rarefaction.txt",
        "lnk alpha_diversity ${diversity_alpha}/*/alpha_diversity/*",
        "lnk beta_diversity ${diversity_beta}/*/beta_diversity/*",
        "lnk beta_diversity/adonis ${diversity_adonis}/*/adonis/*",
        "lnk ancombc/da_barplot ${ancombc_asv}/*/da_barplot/* ${ancombc_tax}/*/da_barplot/*",
        "lnk ancombc_formula/da_barplot ${ancombc_formula_asv}/*/da_barplot/* ${ancombc_formula_tax}/*/da_barplot/*",
        "lnk ancombc2 ${ancombc2_asv}/*/Category-*/*.volcano_plot.svg ${ancombc2_tax}/*/Category-*/*.volcano_plot.svg",
        "lnk ancombc2_formula ${ancombc2_formula_asv}/*/Category-*/*.volcano_plot.svg ${ancombc2_formula_tax}/*/Category-*/*.volcano_plot.svg",
        "lnk phyloseq ${phyloseq_qiime2}/qiime2_phyloseq.rds ${phyloseq_dada2}/dada2_phyloseq.rds",
        "lnk tse ${tse_qiime2}/qiime2_TreeSummarizedExperiment.rds ${tse_dada2}/dada2_TreeSummarizedExperiment.rds",
    ]
    stage += [f'{k}="{v}"; NF_{k}="{k}=\'$${k}\'"' for k, v in lists.items()]
    skip = [r"\.svg$", r"^filterAndTrim\.args\.txt$", r"^(dist|index\.html|q2templateassets|level-\d\.(csv|jsonp))$",
            r"^(alpha_diversity|beta_diversity|ancombc|ancombc2|ancombc_formula|ancombc2_formula|phyloseq|tse)/"]
    return Task("summary_report", "SUMMARY_REPORT", subs=subs, skip=skip, stage=stage,
                inputs=["dada2_quality1", "dada2_quality2", "dada2_err", "dada2_filtntrim", "runs", "barplot", "diversity_alpha",
                        "diversity_beta", "diversity_adonis", "ancombc_asv", "ancombc_tax", "ancombc_formula_asv",
                        "ancombc_formula_tax", "ancombc2_asv", "ancombc2_tax", "ancombc2_formula_asv",
                        "ancombc2_formula_tax", "phyloseq_qiime2", "phyloseq_dada2", "tse_qiime2", "tse_dada2",
                        "filter_samples", "tablefiltertaxa", "diversity_core"],
                post="rmdir alpha_diversity beta_diversity/adonis beta_diversity ancombc/da_barplot ancombc "
                     "ancombc_formula/da_barplot ancombc_formula ancombc2 ancombc2_formula phyloseq tse "
                     "report_abstract metadata input_samplesheet abundance_tables 2>/dev/null || true")


def image_anchor(image: str) -> str:
    for key, name in IMAGES.items():
        if key in image:
            return name
    raise SystemExit(f"no anchor for {image}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    a = ap.parse_args()
    spec = json.load(open(a.spec))
    ts = tasks()

    producers: dict[tuple[str, str | None], tuple[str, bool]] = {}
    for t in ts:
        if t.proc is None:
            continue
        p, task = proc_spec(spec, t)
        is_map = t.over is not None
        producers[(t.proc, task["tag"])] = (t.id, is_map)
        producers.setdefault((t.proc, None), (t.id, is_map))

    out_paths = {"reads": "work/reads/", "samples": "work/samples/", "runs": "work/runs/",
                 "directions": "work/directions/", "reference": "work/reference/"}
    for t in ts:
        for o in t.outputs:
            if o.startswith("l_"):
                out_paths[o] = f"work/lists/{o[2:]}/"
            else:
                out_paths.setdefault(o, f"results/{o}/")
    root_ids = {r[0] for r in ROOT}
    producer_of = {o: t.id for t in ts for o in t.outputs}

    images: dict[str, str] = {}
    blocks, edges = [], []
    for t in ts:
        if t.proc is None:
            cmd, used, p = None, set(t.inputs), None
        else:
            cmd, used, p = build_command(spec, t, producers)
        ins = list(dict.fromkeys(([t.over[0]] if t.over else []) + sorted(used | set(t.inputs))))
        for i in ins:
            assert i in root_ids or i in producer_of, (t.id, i)
        lines = [f"  - kind: {'horus_map' if t.over else 'horus_task'}", f"    id: {t.id}", f"    name: {t.name}"]
        if t.over:
            lines += [f"    over: {{input_id: {t.over[0]}, as: {t.over[1]}}}", "    max_concurrency: 16"]
        lines.append("    inputs: [" + ", ".join(f"*a_{i}" for i in ins) + "]")
        lines.append("    outputs: [" + ", ".join(f"*a_{o}" for o in t.outputs) + "]")
        if p is None:
            lines += ["    executor: {kind: shell}", "    runtime:", "      " + t.runtime]
        else:
            img = p["container"]
            anchor = image_anchor(img)
            images[anchor] = img
            lines.append(f"    resources: {{cpus: {p['cpus']}, memory_gb: {gb(p['memory'])}, walltime: \"01:00:00\"}}")
            lines.append(f"    executor: *{anchor}")
            lines += ["    runtime:", "      kind: command", "      command: |"]
            lines += [("        " + ln) if ln else "" for ln in cmd.split("\n")]
        lines.append("    target: *target")
        blocks.append("\n".join(lines))
        for i in ins:
            src = f"artifact-{i}" if i in root_ids else producer_of[i]
            edges.append(f"  - {{source: {src}, source_output: {i}, target: {t.id}, target_input: {i}}}")

    names = {o: o.replace("_", " ") for o in out_paths}
    out = [HEADER.rstrip()]
    out.append("_img:")
    out += [f'  {k}: &{k} {{kind: docker, user: host, image: "{v}"}}' for k, v in sorted(images.items())]
    out.append("\n# Artifacts, shared by the producing task's outputs and every consumer's inputs.")
    out.append("_art:")
    for rid, name, kind, path, _extra in ROOT:
        out.append(f"  - &a_{rid} {{id: {rid}, name: {name}, kind: {kind}, path: {path}}}")
    for o, path in out_paths.items():
        out.append(f"  - &a_{o} {{id: {o}, name: {names[o]}, kind: folder, path: {path}}}")
    out.append("\nartifacts:")
    for rid, _n, _k, _p, extra in ROOT:
        out.append(f"  - {{<<: *a_{rid}, {extra}}}")
    out.append("\ntasks:")
    out.append("\n\n".join(blocks))
    out.append("\nedges:")
    out += edges
    out.append("\norchestrator_target:\n  kind: local\n  working_directory: horus_workflow_results")
    sys.stdout.write("\n".join(out) + "\n")


HEADER = """\
kind: horus_workflow
name: nf-core ampliseq

# Native port of nf-core/ampliseq 3.1.0, the route `-profile test,docker`
# runs: Cutadapt, DADA2 (quality profiles, automatic truncation, filtering,
# error models, denoising, chimera removal), VSEARCH clustering, decontam,
# Barrnap SSU and length filters, DADA2 (GTDB R07-RS207) and QIIME2
# (Greengenes 85%) taxonomy, QIIME2 filtering, barplots, abundance tables,
# diversity, ANCOM-BC and ANCOM-BC2, phyloseq and TreeSummarizedExperiment
# objects, MultiQC and the summary report.
#
# Generated by scripts/gen_workflow.py from the harvested Nextflow run: each
# task runs the process's rendered .command.sh verbatim (ext.args and the
# test profile parameters as rendered), in the same image, with the same
# cpus/memory (the test profile caps processes at 4 cpus / 15 GB). Inputs
# are linked under the names Nextflow staged them as, the script runs with
# the pipeline's process.shell (bash -C -e -u -o pipefail) or Rscript from
# /tmp/.command.sh, and the links are removed again. Per-sample, per-run,
# per-direction and per-metadata-column steps are horus_map stages; their
# slot values are @NAME@ placeholders filled in from the slot's meta file.
#
# capacity: memory-based admission like Nextflow's local executor. The key
# is the target's location_id (local://<hostname>); set it to the host that
# runs the tasks, or the gate does not apply.

capacity:
  local://ubuntu-awow:
    cpus: 16
    memory_gb: 31
max_concurrency: 16

_target: &target
  kind: local

# Run on a remote node instead: point every task at this anchor.
# _target: &target
#   kind: ssh
#   host: bench-node.example.org
#   username: ubuntu
#   working_directory: /home/ubuntu/horus

# Containers (.command.run docker lines); `user: host` runs them as the
# calling user, as nf-core's `-u $(id -u):$(id -g)` does.
"""

if __name__ == "__main__":
    main()
