#!/usr/bin/env python3
"""
workflow.yaml -> workflow.chained.yaml: the same commands with chained maps.

Each item space (runs, libraries, replicate groups) has a head map that writes
meta.env (id plus the meta file) into its slot. Every later map of that space
sets `chain: true`, iterates the map given in CHAIN and pairs the other maps of
the space it reads through `zip`, so a body reads `${<item>}/` or
`${<map>_item}/` instead of `${<map>}/*/`. The min_trimmed_reads filter
becomes a chained map that exits 10 (drop_exit_codes); the library and
replicate grouping stays a task, as Nextflow's groupTuple waits for every run.
Edges are rebuilt from the task inputs.

Usage: gen_chained.py [workflow.yaml] [workflow.chained.yaml]; gen_chained.py --check
(--check: the committed workflow.chained.yaml is what this script writes)
"""

import re
import sys
from pathlib import Path

import yaml

HEADS = {"trimgalore": "run", "mlb_merge": "lib", "mrp_merge": "rep"}
# map -> (over, zip): the maps of its own item space that it reads
CHAIN = {
    "bwa_mem": ("filter_trimmed", ["trimgalore"]),
    "lb_sort": ("bwa_mem", []),
    "lb_index": ("lb_sort", []),
    "lb_stats": ("lb_index", ["lb_sort"]),
    "lb_flagstat": ("lb_index", ["lb_sort"]),
    "lb_idxstats": ("lb_index", ["lb_sort"]),
    "mlb_markdup": ("mlb_merge", []),
    "mlb_md_index": ("mlb_markdup", []),
    "mlb_md_stats": ("mlb_md_index", ["mlb_markdup"]),
    "mlb_md_flagstat": ("mlb_md_index", ["mlb_markdup"]),
    "mlb_md_idxstats": ("mlb_md_index", ["mlb_markdup"]),
    "mlb_filter": ("mlb_md_index", ["mlb_markdup"]),
    "mlb_name_sort": ("mlb_filter", []),
    "mlb_orphans": ("mlb_name_sort", []),
    "mlb_clean_sort": ("mlb_orphans", []),
    "mlb_clean_index": ("mlb_clean_sort", ["mlb_filter"]),
    "mlb_stats": ("mlb_clean_index", ["mlb_filter", "mlb_clean_sort"]),
    "mlb_flagstat": ("mlb_clean_index", ["mlb_filter", "mlb_clean_sort"]),
    "mlb_idxstats": ("mlb_clean_index", ["mlb_filter", "mlb_clean_sort"]),
    "mlb_cmm": ("mlb_clean_sort", ["mlb_filter"]),
    "mlb_genomecov": ("mlb_flagstat", ["mlb_filter", "mlb_clean_sort"]),
    "mlb_bigwig": ("mlb_genomecov", []),
    "mlb_mat_scale": ("mlb_bigwig", []),
    "mlb_mat_ref": ("mlb_bigwig", []),
    "mlb_profile": ("mlb_mat_scale", []),
    "mlb_heatmap": ("mlb_mat_ref", []),
    "mlb_fingerprint": ("mlb_clean_index", ["mlb_filter", "mlb_clean_sort"]),
    "mlb_macs2": ("mlb_clean_index", ["mlb_filter", "mlb_clean_sort"]),
    "mlb_frip": ("mlb_macs2", ["mlb_filter", "mlb_clean_sort"]),
    "mlb_peaks_mqc": ("mlb_frip", ["mlb_macs2"]),
    "mlb_homer": ("mlb_macs2", []),
    "mlb_ataqv": ("mlb_macs2", ["mlb_markdup", "mlb_md_index"]),
    "mrp_markdup": ("mrp_merge", []),
    "mrp_index": ("mrp_markdup", []),
    "mrp_stats": ("mrp_index", ["mrp_markdup"]),
    "mrp_flagstat": ("mrp_index", ["mrp_markdup"]),
    "mrp_idxstats": ("mrp_index", ["mrp_markdup"]),
    "mrp_genomecov": ("mrp_flagstat", ["mrp_markdup"]),
    "mrp_bigwig": ("mrp_genomecov", []),
    "mrp_macs2": ("mrp_index", ["mrp_markdup"]),
    "mrp_frip": ("mrp_macs2", ["mrp_markdup"]),
    "mrp_peaks_mqc": ("mrp_frip", ["mrp_macs2"]),
    "mrp_homer": ("mrp_macs2", []),
}
SPACE_LISTS = {"trim_pass", "libraries", "replicates"}  # the faithful port's per-item lists

HEADER_OLD = re.compile(r"# Per-run, per-library and per-replicate processes.*?# left empty\.\n", re.S)
HEADER_NEW = """\
# Chained variant of workflow.yaml (scripts/gen_chained.py): same commands and
# outputs. Each item space (runs, libraries, replicate groups) has a head map
# (trimgalore, mlb_merge, mrp_merge) that writes meta.env into its slot: id
# plus the bash-sourceable meta (single_end, library, runs, libraries). Every
# later map of the space sets `chain: true` and iterates an upstream map of the
# same space, so a run or library moves to its next process as soon as its own
# slot is done, not when the whole map is. A body sources ${<item>}/meta.env
# and reads the upstream slot ${<item>}/, or a slot of another map of the space
# paired through `zip` (${<map>_item}/). Runs under min_trimmed_reads drop out
# with exit 10 (drop_exit_codes). The space changes stay barriers, as in
# Nextflow: grouping runs into libraries and libraries into replicate groups
# waits for every run (scripts/decide.py groups). Groovy branches that depend
# on one item (paired-end only steps, empty peak files) are guards inside the
# command, as in workflow.yaml: the slot then holds only meta.env. Every map
# keeps max_concurrency 16, above the item count (8 runs, 6 libraries, 2
# replicate groups), so no clone waits for a slot. Needs horus-runtime 0.9.0
# or later (horus_map chain, zip, drop_exit_codes).
"""

NEW_MAPS = """\
  - kind: horus_map
    id: filter_trimmed
    name: Filter runs by trimmed reads
    description: Drops a run under min_trimmed_reads after trimming (exit 10).
    over: {input_id: trimgalore, as: run}
    chain: true
    drop_exit_codes: [10]
    max_concurrency: 16
    inputs: [*a_trimgalore, *a_min_trimmed]
    outputs: [*a_filter_trimmed]
    executor: {kind: shell}
    runtime:
      kind: python_script
      script: scripts/decide.py
      python: python3 # stdlib only
      args: trim-item --slot ${run} --min-trimmed-reads ${min_trimmed_reads} --out ${filter_trimmed}
    target: *target

  - kind: horus_task
    id: decide_groups
    name: Group libraries and replicates
    description: Groups the passing runs into libraries and libraries into replicate groups.
    inputs: [*a_filter_trimmed]
    outputs: [*a_libraries, *a_replicates]
    executor: {kind: shell}
    runtime:
      kind: python_script
      script: scripts/decide.py
      python: python3 # stdlib only
      args: groups --runs ${filter_trimmed} --libraries ${libraries} --replicates ${replicates}
    target: *target

"""


def blocks(text):
    """Task blocks: a `  - kind:` line (with the `  #` comments above it) up to the next one."""
    starts = [m.start() for m in re.finditer(r"^(?:  #[^\n]*\n)*  - kind: ", text, re.M)]
    return [text[a:b] for a, b in zip(starts, starts[1:] + [len(text)])]


def task_id(block):
    return re.search(r"^    id: (\S+)", block, re.M).group(1)


def sub1(pattern, repl, s, flags=0):
    out, n = re.subn(pattern, repl, s, count=1, flags=flags)
    assert n == 1, pattern
    return out


def chain(block, item, over, zips):
    tid = task_id(block)
    block = sub1(r"^    over: \{input_id: (\w+), as: (\w+)\}\n",
                 lambda m: (assert_list(m, item)
                            + f"    over: {{input_id: {over}, as: {item}}}\n    chain: true\n"
                            + (f"    zip: [{', '.join(f'{{input_id: {z}, as: {z}_item}}' for z in zips)}]\n" if zips else "")),
                 block, re.M)
    # the item list input goes; the over map takes its place if not read yet
    lead = "" if f"*a_{over}," in block or f"*a_{over}]" in block else f"*a_{over}, "
    block = sub1(r"inputs: \[\*a_(?:trim_pass|libraries|replicates), ", f"inputs: [{lead}", block)
    inputs = re.search(r"inputs: \[([^\]]*)\]", block).group(1)
    for x in (over, *zips):
        assert f"*a_{x}," in inputs + ",", (tid, x)
    block = sub1(rf"id=\$\$\(basename \$\{{{item}\}}\)(?:; \. \$\{{{item}\}})?", f". ${{{item}}}/meta.env", block)
    block = sub1(rf"(rm -rf \$\{{{tid}\}} && mkdir -p \$\{{{tid}\}} && cd \$\{{{tid}\}})\n",
                 rf"\1 && cp ${{{item}}}/meta.env .\n", block)
    block = block.replace(f"${{{over}}}/*/", f"${{{item}}}/").replace(f"${{{over}}}", f"${{{item}}}")
    for z in zips:
        block = block.replace(f"${{{z}}}/*/", f"${{{z}_item}}/").replace(f"${{{z}}}", f"${{{z}_item}}")
    block = block.replace("$$src/*/", "$$src/")
    body = block.split("command: |", 1)[1]
    assert "/*/" not in body and f". ${{{item}}}\n" not in body, tid
    return block


def assert_list(m, item):
    assert m.group(1) in SPACE_LISTS and m.group(2) == item, m.group(0)
    return ""


def head(block, item):
    tid = task_id(block)
    return sub1(rf"(rm -rf \$\{{{tid}\}} && mkdir -p \$\{{{tid}\}} && cd \$\{{{tid}\}}\n)",
                rf"\1        {{ echo id=$$id; cat ${{{item}}}; }} > meta.env\n", block)


def edges(text):
    """One edge per task input: from the task that outputs it, else the root artifact."""
    tasks = yaml.safe_load(text)["tasks"]
    producer = {o["id"]: t["id"] for t in tasks for o in t.get("outputs", [])}
    return "".join(
        f"  - {{source: {producer.get(i['id'], 'artifact-' + i['id'])}, source_output: {i['id']}, "
        f"target: {t['id']}, target_input: {i['id']}}}\n"
        for t in tasks for i in t.get("inputs", []))


def generate(src):
    pre, rest = src.split("\ntasks:\n", 1)
    tasks, post = rest.split("\nedges:\n", 1)
    old_edges, tail = post.split("\n\norchestrator_target:", 1)
    assert edges(src) == old_edges + "\n", "edges of workflow.yaml are not one per task input"

    pre = sub1(r"^name: nf-core atacseq\n", "name: nf-core atacseq chained\n", pre, re.M)
    pre = sub1(HEADER_OLD, HEADER_NEW, pre)
    pre = sub1(r"^  - &a_trim_pass .*\n",
               "  - &a_filter_trimmed {id: filter_trimmed, name: Runs passing trimming, kind: folder, path: work/filter_trimmed/}\n",
               pre, re.M)

    out = []
    for b in blocks(tasks):
        tid = task_id(b)
        if tid == "decide_trimmed":
            b = NEW_MAPS
        elif tid in HEADS:
            b = head(b, HEADS[tid])
        elif tid in CHAIN:
            item = re.search(r"over: \{input_id: \w+, as: (\w+)\}", b).group(1)
            b = chain(b, item, *CHAIN[tid])
        out.append(b)
    first = tasks[: tasks.index(blocks(tasks)[0])]
    text = f"{pre}\ntasks:\n{first}{''.join(out)}\nedges:\n\n\norchestrator_target:{tail}"
    text = text.replace("\nedges:\n\n\n", "\nedges:\n" + edges(text) + "\n", 1)
    assert "trim_pass" not in text and set(CHAIN) | set(HEADS) <= {t["id"] for t in yaml.safe_load(text)["tasks"]}
    return text


def main():
    here = Path(__file__).resolve().parent.parent
    if sys.argv[1:] == ["--check"]:
        want = generate((here / "workflow.yaml").read_text())
        ok = (here / "workflow.chained.yaml").read_text() == want
        print("workflow.chained.yaml is " + ("up to date" if ok else "STALE: run scripts/gen_chained.py"))
        return 0 if ok else 1
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else here / "workflow.yaml"
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else here / "workflow.chained.yaml"
    dst.write_text(generate(src.read_text()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
