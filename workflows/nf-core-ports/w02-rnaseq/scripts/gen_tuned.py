#!/usr/bin/env python3
"""
Generate workflow.tuned.yaml from workflow.yaml: same commands, fewer maps.

Per-sample stages that use the same image and iterate the same sample list
are chained in one map task (samtools sort + index + stats, the markdup
samtools steps, the seven RSeQC modules, the stranded coverage / clip /
bigWig pairs). Each stage keeps its exact command, including its own
cpus/memory values, runs with `bash -C -e -u -o pipefail` as before, and
writes into <fused slot>/<stage id>/, so the outputs are the same files.
The fused task requests the largest cpus/memory of its stages.

Edges are rebuilt from the input ids (every input id names the output it
reads); the script checks that this reproduces workflow.yaml's own edges.

usage: gen_tuned.py [workflow.yaml] [workflow.tuned.yaml]   (needs PyYAML)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent.parent

FUSIONS = {
    "sort_chain": ("SAMTOOLS sort, index and stats", "results/star_salmon/samtools_sort/",
                   ["sort", "sort_index", "sort_flagstat", "sort_idxstats", "sort_stats"]),
    "markdup_chain": ("SAMTOOLS markdup index, stats and name sort", "results/star_salmon/samtools_markdup/",
                      ["md_index", "md_flagstat", "md_idxstats", "md_stats", "qualimap_sort"]),
    "rseqc": ("RSeQC modules", "results/star_salmon/rseqc/",
              ["rseqc_bamstat", "rseqc_infer", "rseqc_innerdist", "rseqc_junc_annot", "rseqc_junc_sat",
               "rseqc_readdist", "rseqc_readdup"]),
    "cov_stranded": ("BEDTOOLS_GENOMECOV forward and reverse", "work/bedgraph/stranded/", ["cov_fw", "cov_rev"]),
    "clip_stranded": ("UCSC_BEDCLIP forward and reverse", "work/bedgraph/clip_stranded/", ["clip_fw", "clip_rev"]),
    "bigwig_stranded": ("UCSC_BEDGRAPHTOBIGWIG forward and reverse", "results/star_salmon/bigwig/stranded/",
                        ["bigwig_fw", "bigwig_rev"]),
}
BODY = re.compile(r"cat > /tmp/\.command\.sh <<'NF'\n(.*)\nNF\nexec bash -C -e -u -o pipefail /tmp/\.command\.sh\n\Z", re.S)


def derive_edges(doc: dict) -> list[dict]:
    roots = {a["id"] for a in doc["artifacts"]}
    producer = {o["id"]: t["id"] for t in doc["tasks"] for o in t.get("outputs", [])}
    edges = []
    for t in doc["tasks"]:
        for i in t.get("inputs", []):
            src = f"artifact-{i['id']}" if i["id"] in roots else producer[i["id"]]
            edges.append({"source": src, "source_output": i["id"], "target": t["id"], "target_input": i["id"]})
    return edges


def edge_set(edges):
    return {(e["source"], e["source_output"], e["target"], e["target_input"]) for e in edges}


def group_artifact(f: str) -> dict:
    return {"id": f, "name": FUSIONS[f][0], "kind": "folder", "path": FUSIONS[f][1]}


def fuse(doc: dict) -> dict:
    tasks = {t["id"]: t for t in doc["tasks"]}
    owner = {s: f for f, (_n, _p, steps) in FUSIONS.items() for s in steps}

    def rewrite(text: str, inside: str | None) -> str:
        for s, f in owner.items():
            if f == inside:
                text = text.replace(f"${{{s}}}/*/", f"${{{f}}}/{s}/").replace(f"${{{s}}}", f"${{{f}}}/{s}")
            else:
                text = text.replace(f"${{{s}}}/*/", f"${{{f}}}/*/{s}/").replace(f"${{{s}}}", f"${{{f}}}")
        return text

    out_tasks = []
    for t in doc["tasks"]:
        if t["id"] in owner:
            if t["id"] != FUSIONS[owner[t["id"]]][2][0]:
                continue  # emitted with the first stage of its group
            f = owner[t["id"]]
            name, path, steps = FUSIONS[f]
            parts = [tasks[s] for s in steps]
            assert len({p["executor"]["image"] for p in parts}) == 1, f
            assert len({p["over"]["input_id"] for p in parts}) == 1, f
            art = group_artifact(f)
            inputs, seen = [], set(steps)
            for p in parts:
                for i in p["inputs"]:
                    if i["id"] in owner and owner[i["id"]] != f:
                        i = group_artifact(owner[i["id"]])
                    if i["id"] not in seen:
                        seen.add(i["id"])
                        inputs.append(i)
            scripts, runs = [], []
            for k, p in enumerate(parts, 1):
                body = BODY.match(p["runtime"]["command"]).group(1)
                body = body.replace("${task.resources.cpus}", str(p["resources"]["cpus"]))
                body = body.replace("${task.resources.memory_gb}", str(p["resources"]["memory_gb"]))
                body = f"# {p['name']}\n" + rewrite(body, f)
                scripts.append(f"cat > /tmp/.command{k}.sh <<'NF'\n{body}\nNF\n")
                runs.append(f"bash -C -e -u -o pipefail /tmp/.command{k}.sh")
            res = {k: max(p["resources"][k] for p in parts) for k in ("cpus", "memory_gb")}
            res["walltime"] = parts[0]["resources"]["walltime"]
            out_tasks.append({
                "kind": "horus_map", "id": f, "name": name,
                "description": "Chains " + ", ".join(p["name"] for p in parts) + " (same image, same commands).",
                "over": parts[0]["over"], "max_concurrency": parts[0]["max_concurrency"],
                "inputs": inputs, "outputs": [art], "resources": res, "executor": parts[0]["executor"],
                "runtime": {"kind": "command", "command": "".join(scripts) + f"mkdir -p ${{{f}}}\n" + " && ".join(runs) + "\n"},
                "target": parts[0]["target"],
            })
            continue
        t = dict(t)
        rt = dict(t["runtime"])
        for key in ("command", "args"):
            if key in rt:
                rt[key] = rewrite(rt[key], None)
        t["runtime"] = rt
        inputs, seen = [], set()
        for i in t.get("inputs", []):
            if i["id"] in owner:
                i = group_artifact(owner[i["id"]])
            if i["id"] not in seen:
                seen.add(i["id"])
                inputs.append(i)
        t["inputs"] = inputs
        out_tasks.append(t)
    new = {k: v for k, v in doc.items() if not k.startswith("_")}
    new["name"] = doc["name"] + " tuned"
    new["tasks"] = out_tasks
    new["edges"] = derive_edges(new)
    return new


class Dumper(yaml.SafeDumper):
    pass


Dumper.add_representer(str, lambda d, s: d.represent_scalar("tag:yaml.org,2002:str", s, style="|" if "\n" in s else None))
Dumper.ignore_aliases = lambda *_: True


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "workflow.yaml"
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "workflow.tuned.yaml"
    doc = yaml.safe_load(src.read_text())
    assert edge_set(derive_edges(doc)) == edge_set(doc["edges"]), "workflow.yaml edges differ from its input ids"
    new = fuse(doc)
    maps = sum(t["kind"] == "horus_map" for t in new["tasks"])
    head = (f"# Generated by scripts/gen_tuned.py from {src.name}; do not edit by hand.\n"
            f"# Same images and commands as {src.name}, with same-image per-sample stages chained:\n"
            f"# {len(new['tasks'])} tasks ({maps} maps) instead of {len(doc['tasks'])}"
            f" ({sum(t['kind'] == 'horus_map' for t in doc['tasks'])} maps).\n")
    dst.write_text(head + yaml.dump(new, Dumper=Dumper, sort_keys=False, width=4096, allow_unicode=True))
    print(f"wrote {dst}: {len(new['tasks'])} tasks, {maps} maps")
    return 0


if __name__ == "__main__":
    sys.exit(main())
