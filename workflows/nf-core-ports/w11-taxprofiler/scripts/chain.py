#!/usr/bin/env python3
"""
Write workflow.chained.yaml from workflow.yaml: the same commands, with each
map that follows another map over the same jobs set to `chain: true`.

A chain head (the first map over a job folder) copies its job file into its
slot as <head>-<job>.job. A chained map iterates the previous map's output,
sources ${up}/*.job and carries it on to its own slot. The job's globs rooted
at the previous map ($FASTP/*/<file>, ...) point at a temp dir that links only
this item's slot, and direct ${<map>}/*/ reads become ${up}/. Bracken chains
on Kraken2 and drops (exit 10) the Kraken2 items that are not Bracken jobs.

stdlib only.

Usage:
    chain.py [workflow.yaml] > workflow.chained.yaml
"""

import re
import sys
from pathlib import Path

HEADS = ["fastp", "porechop", "kraken2", "centrifuge", "kaiju", "ganon", "kmcp", "sylph"]

# map: (previous map, env var its job globs are rooted at, {zip input: item name})
CHAINED = {
    "fastqc_short": ("fastp", "FASTP", {}),
    "nonpareil": ("fastp", "FASTP", {}),
    "nonpareil_curve": ("nonpareil", None, {}),
    "bbduk": ("fastp", "FASTP", {}),
    "bowtie2_align": ("bbduk", "BBDUK", {}),
    "samtools_index": ("bowtie2_align", None, {}),
    "stats_short": ("samtools_index", None, {"bowtie2_align": "aln"}),
    "nanoq": ("porechop", "PORECHOP", {}),
    "fastqc_long": ("nanoq", "NANOQ", {}),
    "minimap2_align": ("nanoq", "NANOQ", {}),
    "stats_long": ("minimap2_align", None, {}),
    "samtools_view": ("minimap2_align", None, {}),
    "samtools_fastq": ("samtools_view", None, {}),
    "ckreport": ("centrifuge", None, {}),
    "kaijutable": ("kaiju", None, {}),
    "kaiju2krona": ("kaiju", None, {}),
    "ganon_report": ("ganon", None, {}),
    "kmcp_profile": ("kmcp", None, {}),
    "sylphtax": ("sylph", None, {}),
    "bracken": ("kraken2", "KRAKEN2", {}),
}

HEADER = """kind: horus_workflow
name: nf-core taxprofiler chained

# Chained variant of workflow.yaml (scripts/chain.py writes it): same
# commands and outputs. Each map that follows another map over the same jobs
# sets `chain: true`, so an item's next step starts as soon as its own
# previous step is done, not when the whole map is: the short-read chain
# (fastp, BBDuk, bowtie2, samtools), the long-read chain (porechop_abi,
# nanoq, minimap2, samtools) and each profiler's own steps (Centrifuge
# kreport, kaiju2table, ganon report, KMCP profile, sylph-tax, Bracken). A
# chain head copies its job file into its slot; a chained map sources it from
# the previous slot (${up}). Bracken chains on Kraken2 and drops the Kraken2
# items that are not Bracken jobs (exit 10, drop_exit_codes). Steps that
# gather many items (run merging, the profilers, Krona, taxpasta, MultiQC)
# still wait for their whole inputs. Needs horus-runtime 0.9.0 or later.
"""


def block_span(text: str, task: str) -> tuple[int, int]:
    m = re.search(rf"\n  - kind: horus_map\n    id: {task}\n", text)
    assert m, task
    end = text.find("\n    target: *target\n", m.end())
    return m.start(), end


def sub1(block: str, old: str, new: str, task: str) -> str:
    assert block.count(old) == 1, (task, old)
    return block.replace(old, new)


def head(block: str, task: str) -> str:
    m = re.search(r"cd \$\{(\w+)\}\n", block)
    return sub1(block, m.group(0), m.group(0) + f"        cp ${{job}} {task}-$$(basename ${{job}}).job\n", task)


def chained(block: str, task: str, up: str, env: str | None, zips: dict[str, str]) -> str:
    over = re.search(r"over: \{input_id: (j_\w+), as: job\}", block)
    jobs = over.group(1)
    line = f"over: {{input_id: {up}, as: up}}\n    chain: true"
    if zips:
        line += "\n    zip: [" + ", ".join(f"{{input_id: {i}, as: {v}}}" for i, v in zips.items()) + "]"
    if task == "bracken":
        line += "\n    drop_exit_codes: [10]"
    block = sub1(block, over.group(0), line, task)
    if task != "bracken":
        block = sub1(block, f"*{jobs}, ", "", task)
    links = ""
    if env:
        block = sub1(block, f"{env}=${{{up}}}", f"{env}=$$(mktemp -d)", task)
        links = f"ln -s ${{up}} $${env}/0; "
    if task == "bracken":
        source = (links + "n=$$(basename ${up}/*.job .job); n=$${n#kraken2-}\n"
                  "        case $$n in *_bracken) ;; *) exit 10 ;; esac  # a Kraken2-only item\n"
                  f"        . ${{{jobs}}}/$${{n%_bracken}}")
    else:
        source = links + ". ${up}/*.job"
    block = sub1(block, ". ${job}", source, task)
    for i, v in {up: "up", **zips}.items():
        block = block.replace(f"${{{i}}}/*/", f"${{{v}}}/")
        assert f"${{{i}}}" not in block, (task, i)
    if task != "bracken":
        m = re.search(r"cd \$\{(\w+)\}\n", block)
        block = sub1(block, m.group(0), m.group(0) + "        cp ${up}/*.job .\n", task)
    return block


def main() -> None:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "workflow.yaml").read_text()
    text = src
    for task in HEADS:
        a, b = block_span(text, task)
        text = text[:a] + head(text[a:b], task) + text[b:]
    for task, (up, env, zips) in CHAINED.items():
        a, b = block_span(text, task)
        jobs = re.search(r"over: \{input_id: (j_\w+), as: job\}", text[a:b]).group(1)
        text = text[:a] + chained(text[a:b], task, up, env, zips) + text[b:]
        if task != "bracken":  # the job folder is no longer an input
            text = sub1(text, f"  - {{source: plan, source_output: {jobs}, target: {task}, target_input: {jobs}}}\n", "", task)
    # keep workflow.yaml's own header comment after the chained one
    body = text.split("\n", 2)[2]
    sys.stdout.write(HEADER + "\n" + body)


if __name__ == "__main__":
    main()
