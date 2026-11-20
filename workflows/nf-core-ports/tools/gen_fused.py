#!/usr/bin/env python3
"""
workflow.chained.yaml -> workflow.fused.yaml: tiny per-sample steps in one map.

Each group in PORTS lists chained maps of one item space that use the same
image. They become one map that runs their command bodies in order, each still
its own `bash <flags>` script with its own cpus/memory values, and each
writing into <group slot>/<stage id>/ instead of <stage slot>/. The fused map
requests the largest cpus/memory/walltime of its stages. Images and command
lines stay the same; only paths that name a fused output change:

  inside the group   ${<stage out>}        -> ${<group>}/<stage>
                     ${<item of a stage>}  -> ${<group>}/<stage>
  chained readers    over/zip a stage       -> over/zip the group, ${x} -> ${x}/<stage>
  whole-folder reads ${<stage out>}/*/     -> ${<group>}/*/<stage>/

A bare ${<stage out>} elsewhere fails the build unless the port lists it in
`bare` (its reader searches the folder recursively) or rewrites it in
`patches` first. Edges are rebuilt from the task inputs and checked acyclic.

Usage: gen_fused.py [PORT ...]          write <PORT>/workflow.fused.yaml
       gen_fused.py --check [PORT ...]  the committed files are what this writes
       gen_fused.py --selftest
"""

from __future__ import annotations

import copy
import re
import sys
from graphlib import TopologicalSorter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

# group id -> (name, output path, stages); stages run in this order
PORTS = {
    "w10-viralrecon": {
        "groups": {
            "sort_chain": ("SAMTOOLS sort, index and stats", "results/variants/bowtie2/sort_chain/",
                           ["sort", "sort_index", "sort_stats", "sort_flagstat", "sort_idxstats"]),
            "trim_chain": ("SAMTOOLS sort, index and stats of the iVar trimmed BAM",
                           "results/variants/bowtie2/trim_chain/",
                           ["trim_sort", "trim_index", "trim_stats", "trim_flagstat", "trim_idxstats"]),
            "mosdepth": ("MOSDEPTH genome and amplicon", "results/variants/bowtie2/mosdepth/fused/",
                         ["mosdepth_genome", "mosdepth_amplicon"]),
        },
        # decide.py mapped finds <id>.sorted.bam.flagstat with **/ under the folder
        "bare": {("decide_mapped", "sort_flagstat")},
        "patches": {},
    },
    "w05-atacseq": {
        "groups": {
            "lb_chain": ("Library BAM sort, index and stats", "work/bwa/library/lb_chain/",
                         ["lb_sort", "lb_index", "lb_stats", "lb_flagstat", "lb_idxstats"]),
            "mlb_md_chain": ("Merged library MarkDuplicates index and stats",
                             "results/bwa/merged_library/md_chain/",
                             ["mlb_md_index", "mlb_md_stats", "mlb_md_flagstat", "mlb_md_idxstats"]),
            "mlb_clean_chain": ("Merged library clean BAM sort, index and stats",
                                "results/bwa/merged_library/clean_chain/",
                                ["mlb_clean_sort", "mlb_clean_index", "mlb_stats", "mlb_flagstat", "mlb_idxstats"]),
            "mrp_chain": ("Merged replicate BAM index and stats", "results/bwa/merged_replicate/mrp_chain/",
                          ["mrp_index", "mrp_stats", "mrp_flagstat", "mrp_idxstats"]),
        },
        "bare": set(),
        # $$src picks a whole map folder; name the slot glob in src instead
        "patches": {
            "mrp_merge": [
                ("then src=${mlb_filter}; else src=${mlb_clean_sort}; fi",
                 "then src=${mlb_filter}/*; else src=${mlb_clean_sort}/*; fi"),
                ("ln -s $$src/*/$$b $$b", "ln -s $$src/$$b $$b"),
            ],
        },
    },
    "w06-chipseq": {
        "groups": {
            "lib_chain": ("Library BAM sort, index and stats", "work/bwa/library/lib_chain/",
                          ["lib_sort", "lib_index", "lib_stats", "lib_flagstat", "lib_idxstats"]),
            "md_chain": ("Merged library MarkDuplicates index and stats", "work/bwa/merged_library/md_chain/",
                         ["md_index", "md_stats", "md_flagstat", "md_idxstats"]),
            "clean_chain": ("Filtered BAM sort, index and stats", "results/bwa/merged_library/clean_chain/",
                            ["filter_sort", "filter_index", "filter_stats", "filter_flagstat", "filter_idxstats"]),
            "deeptools_profile": ("deepTools computeMatrix, plotProfile and plotHeatmap",
                                  "results/bwa/merged_library/deepTools/plotProfile/fused/",
                                  ["computematrix", "plotprofile", "plotheatmap"]),
        },
        "bare": set(),
        "patches": {},
    },
}

BODY = re.compile(r"cat > /tmp/\.command\.sh <<'NF'\n(.*)\nNF\nexec (bash [^\n]*) /tmp/\.command\.sh\n\Z", re.S)
TOKEN = re.compile(r"(?<!\$)\$\{(\w+)\}(/\*/|/\*(?![\w/*]))?")
STAGE_KEYS = {"kind", "id", "name", "description", "over", "chain", "zip", "max_concurrency",
              "inputs", "outputs", "resources", "executor", "runtime", "target"}


def derive_edges(tasks: list[dict]) -> list[dict]:
    producer = {o["id"]: t["id"] for t in tasks for o in t.get("outputs", [])}
    return [{"source": producer[i["id"]] if i["id"] in producer else f"artifact-{i['id']}",
             "source_output": i["id"], "target": t["id"], "target_input": i["id"]}
            for t in tasks for i in t.get("inputs", [])]


def edge_set(edges):
    return {(e["source"], e["source_output"], e["target"], e["target_input"]) for e in edges}


def dedupe(items: list[dict], key: str) -> list[dict]:
    seen, out = set(), []
    for x in items:
        if x[key] not in seen:
            seen.add(x[key])
            out.append(x)
    return out


def walltime(w: str) -> int:
    h, m, s = (int(x) for x in w.split(":"))
    return h * 3600 + m * 60 + s


def fuse(doc: dict, groups: dict, bare: set = frozenset(), patches: dict | None = None) -> dict:
    tasks = {t["id"]: t for t in doc["tasks"]}
    member = {s: g for g, (_n, _p, steps) in groups.items() for s in steps}  # task id -> group
    where = {tasks[s]["outputs"][0]["id"]: (g, s) for s, g in member.items()}  # output id -> (group, stage)
    taken = {a["id"] for a in doc["artifacts"]} | {o["id"] for t in doc["tasks"] for o in t.get("outputs", [])}
    for g in groups:
        assert g not in taken and f"{g}_item" not in taken, f"group id {g} is taken"

    def group_art(g):
        return {"id": g, "name": groups[g][0], "kind": "folder", "path": groups[g][1]}

    def streams(t: dict, own: str | None, over: dict | None = None):
        """
        New over/zip entries of *t* and the ${var} -> text bindings they imply.
        *over* is the new over of the map *t* ends up in, once known.
        """
        bind, entries = {}, []
        for e in [t["over"], *t.get("zip", [])]:
            src, alias = e["input_id"], e["as"]
            if src in where:
                g, s = where[src]
                if g == own:
                    bind[alias] = f"${{{g}}}/{s}"
                    continue
                src, path = g, f"/{s}"
            else:
                path = ""
            if over is None:
                over = {"input_id": src, "as": alias}  # the first entry is the over
            if src == over["input_id"]:
                alias = over["as"]
            elif path:
                alias = f"{src}_item"
            if path or alias != e["as"]:
                bind[e["as"]] = f"${{{alias}}}{path}"
            entries.append({"input_id": src, "as": alias})
        return entries, bind

    def rewrite(text: str, tid: str, own: str | None, bind: dict) -> str:
        for old, new in (patches or {}).get(tid, []):
            assert text.count(old) == 1, (tid, old)
            text = text.replace(old, new)

        def sub(m):
            name, glob = m.group(1), m.group(2) or ""
            if name in bind:
                assert not glob, (tid, m.group(0))
                return bind[name]
            if name not in where:
                return m.group(0)
            g, s = where[name]
            if g == own:
                assert name == tasks[tid]["outputs"][0]["id"] and not glob, (tid, m.group(0))
                return f"${{{g}}}/{s}"
            if glob == "/*/":
                return f"${{{g}}}/*/{s}/"
            if glob == "/*":
                return f"${{{g}}}/*/{s}"
            assert (tid, name) in bare, f"{tid}: bare ${{{name}}}; list it in bare or patches"
            return f"${{{g}}}"

        return TOKEN.sub(sub, text)

    def inputs_of(parts: list[dict], own: str | None) -> list[dict]:
        out = []
        for p in parts:
            for i in p.get("inputs", []):
                if i["id"] in where:
                    g = where[i["id"]][0]
                    if g == own:
                        continue
                    i = group_art(g)
                out.append(i)
        return dedupe(out, "id")

    out_tasks = []
    for t in doc["tasks"]:
        g = member.get(t["id"])
        if g is None:
            t = copy.deepcopy(t)
            bind = {}
            if "over" in t:
                entries, bind = streams(t, None)
                t["over"] = entries[0]
                zips = dedupe(entries[1:], "input_id")
                zips = [z for z in zips if z["input_id"] != t["over"]["input_id"]]
                if zips:
                    t["zip"] = zips
                else:
                    t.pop("zip", None)
            for key in ("command", "args"):
                if key in t["runtime"]:
                    t["runtime"][key] = rewrite(t["runtime"][key], t["id"], None, bind)
            if "inputs" in t:
                t["inputs"] = inputs_of([t], None)
            out_tasks.append(t)
            continue
        name, _path, steps = groups[g]
        if t["id"] != steps[0]:
            continue  # emitted with the first stage of its group
        parts = [tasks[s] for s in steps]
        for p in parts:
            assert p["kind"] == "horus_map" and set(p) <= STAGE_KEYS, (g, p["id"], set(p) - STAGE_KEYS)
        for key in ("executor", "target", "chain", "max_concurrency"):
            assert all(p.get(key) == parts[0].get(key) for p in parts), (g, key)
        assert where.get(parts[0]["over"]["input_id"], ("",))[0] != g, (g, "first stage reads the group")
        over = streams(parts[0], g)[0][0]
        zips, scripts, runs = [], [], []
        for k, p in enumerate(parts, 1):
            entries, bind = streams(p, g, over)
            if where.get(p["over"]["input_id"], ("",))[0] != g:
                assert entries[0] == over, (g, p["id"], "over differs")
            zips += entries
            m = BODY.match(p["runtime"]["command"])
            assert m, (g, p["id"], "command is not a /tmp/.command.sh heredoc")
            body = m.group(1)
            body = body.replace("${task.resources.cpus}", str(p["resources"]["cpus"]))
            body = body.replace("${task.resources.memory_gb}", str(p["resources"]["memory_gb"]))
            assert "${task." not in body, (g, p["id"])
            body = f"# {p['name']}\n" + rewrite(body, p["id"], g, bind)
            scripts.append(f"cat > /tmp/.command{k}.sh <<'NF'\n{body}\nNF\n")
            runs.append(f"{m.group(2)} /tmp/.command{k}.sh")
        zips = [z for z in dedupe(zips, "input_id") if z["input_id"] != over["input_id"]]
        aliases = {}
        for z in zips:
            assert aliases.setdefault(z["input_id"], z["as"]) == z["as"], (g, z)
        res = {k: max(p["resources"][k] for p in parts) for k in ("cpus", "memory_gb")}
        res["walltime"] = max((p["resources"]["walltime"] for p in parts), key=walltime)
        fused = {"kind": "horus_map", "id": g, "name": name,
                 "description": "Runs " + ", ".join(p["name"] for p in parts) + " in turn (same image, same commands).",
                 "over": over}
        if "chain" in parts[0]:
            fused["chain"] = parts[0]["chain"]
        if zips:
            fused["zip"] = zips
        fused.update({
            "max_concurrency": parts[0]["max_concurrency"],
            "inputs": inputs_of(parts, g), "outputs": [group_art(g)], "resources": res,
            "executor": parts[0]["executor"],
            "runtime": {"kind": "command",
                        "command": "".join(scripts) + f"mkdir -p ${{{g}}}\n" + " && ".join(runs) + "\n"},
            "target": parts[0]["target"],
        })
        out_tasks.append(fused)

    new = {k: v for k, v in doc.items() if not k.startswith("_")}
    new["name"] = doc["name"] + " fused"
    new["tasks"] = out_tasks
    new["edges"] = derive_edges(out_tasks)
    deps = {t["id"]: set() for t in out_tasks}
    for e in new["edges"]:
        if not e["source"].startswith("artifact-"):
            deps[e["target"]].add(e["source"])
    tuple(TopologicalSorter(deps).static_order())  # raises CycleError
    check_names(new)
    return new


def check_names(doc: dict) -> None:
    """Every ${name} a task reads is one of its inputs, outputs or item variables."""
    for t in doc["tasks"]:
        known = {a["id"] for a in (*t.get("inputs", []), *t.get("outputs", []))}
        known |= {e["as"] for e in [t["over"], *t.get("zip", [])]} if "over" in t else set()
        text = t["runtime"].get("command", "") + str(t["runtime"].get("args", ""))
        unknown = {m.group(1) for m in TOKEN.finditer(text)} - known
        assert not unknown, (t["id"], sorted(unknown))


class Dumper(yaml.SafeDumper):
    pass


Dumper.add_representer(str, lambda d, s: d.represent_scalar("tag:yaml.org,2002:str", s, style="|" if "\n" in s else None))
Dumper.ignore_aliases = lambda *_: True


def generate(port: str) -> str:
    cfg = PORTS[port]
    doc = yaml.safe_load((ROOT / port / "workflow.chained.yaml").read_text())
    assert edge_set(derive_edges(doc["tasks"])) == edge_set(doc["edges"]), f"{port}: chained edges differ from inputs"
    new = fuse(doc, cfg["groups"], cfg["bare"], cfg["patches"])
    fused = sum(len(s) for _n, _p, s in cfg["groups"].values())
    head = (f"# Generated by tools/gen_fused.py from workflow.chained.yaml; do not edit by hand.\n"
            f"# Same images and commands; {fused} same-image per-item steps run as {len(cfg['groups'])} maps:\n"
            f"# {len(new['tasks'])} tasks instead of {len(doc['tasks'])}.\n")
    return head + yaml.dump(new, Dumper=Dumper, sort_keys=False, width=4096, allow_unicode=True)


def selftest() -> int:
    def m(tid, over, zips=(), cmd="true", img="i", ins=(), cpus=1):
        t = {"kind": "horus_map", "id": tid, "name": tid.upper(), "over": {"input_id": over, "as": "s"},
             "chain": True, "max_concurrency": 4,
             "inputs": [{"id": x, "name": x, "kind": "folder", "path": f"w/{x}/"} for x in (over, *zips, *ins)],
             "outputs": [{"id": tid, "name": tid, "kind": "folder", "path": f"w/{tid}/"}],
             "resources": {"cpus": cpus, "memory_gb": 2, "walltime": "01:00:00"},
             "executor": {"kind": "docker", "image": img},
             "runtime": {"kind": "command",
                         "command": f"cat > /tmp/.command.sh <<'NF'\n{cmd}\nNF\nexec bash -euo pipefail /tmp/.command.sh\n"},
             "target": {"kind": "local"}}
        if zips:
            t["zip"] = [{"input_id": z, "as": f"{z}_item"} for z in zips]
        return t

    doc = {"kind": "horus_workflow", "name": "t", "_img": "x",
           "artifacts": [{"id": "items", "name": "items", "kind": "folder", "path": "w/items/"}],
           "tasks": [
               m("srt", "items", cmd="cd ${srt} && sort -@ ${task.resources.cpus} ${s}/a > b", cpus=4),
               m("idx", "srt", ["items"], cmd="index ${s}/b ${items_item}/a > ${idx}/b.bai"),
               m("st", "idx", ["srt"], cmd="stats ${srt_item}/b ${s}/b.bai > ${st}/b.stats"),
               m("down", "st", ["srt", "idx"], img="j", cmd=". ${s}/meta.env; use ${srt_item}/b ${idx_item}/b.bai ${s}/b.stats"),
               m("side", "items", ["idx"], img="j", cmd="use ${idx_item}/b.bai"),
               {"kind": "horus_task", "id": "mqc", "name": "MQC",
                "inputs": [{"id": "st", "name": "st", "kind": "folder", "path": "w/st/"}],
                "outputs": [{"id": "mqc", "name": "mqc", "kind": "folder", "path": "w/mqc/"}],
                "runtime": {"kind": "command", "command": "ln -s ${st}/*/*.stats .; ls ${st}/*"},
                "executor": {"kind": "shell"}, "target": {"kind": "local"}},
           ]}
    doc["edges"] = derive_edges(doc["tasks"])
    groups = {"chain": ("Chain", "w/chain/", ["srt", "idx", "st"])}
    new = fuse(doc, groups)
    t = {x["id"]: x for x in new["tasks"]}
    assert list(t) == ["chain", "down", "side", "mqc"], list(t)
    c = t["chain"]
    assert c["over"] == {"input_id": "items", "as": "s"} and "zip" not in c, c
    assert c["resources"]["cpus"] == 4 and [i["id"] for i in c["inputs"]] == ["items"], c
    cmd = c["runtime"]["command"]
    for want in ("cd ${chain}/srt && sort -@ 4 ${s}/a > b", "index ${chain}/srt/b ${s}/a > ${chain}/idx/b.bai",
                 "stats ${chain}/srt/b ${chain}/idx/b.bai > ${chain}/st/b.stats",
                 "mkdir -p ${chain}\nbash -euo pipefail /tmp/.command1.sh && bash -euo pipefail /tmp/.command2.sh"):
        assert want in cmd, (want, cmd)
    d = t["down"]
    assert d["over"] == {"input_id": "chain", "as": "s"} and "zip" not in d, d
    assert ". ${s}/st/meta.env; use ${s}/srt/b ${s}/idx/b.bai ${s}/st/b.stats" in d["runtime"]["command"], d
    s = t["side"]
    assert s["zip"] == [{"input_id": "chain", "as": "chain_item"}] and "use ${chain_item}/idx/b.bai" in s["runtime"]["command"], s
    assert t["mqc"]["runtime"]["command"] == "ln -s ${chain}/*/st/*.stats .; ls ${chain}/*/st", t["mqc"]
    assert edge_set(new["edges"]) >= {("chain", "chain", "down", "chain"), ("artifact-items", "items", "chain", "items")}
    assert "_img" not in new and yaml.safe_load(yaml.dump(new, Dumper=Dumper)) == new
    # a bare read of a fused output is refused
    bad = copy.deepcopy(doc)
    bad["tasks"][-1]["runtime"]["command"] = "ls ${st}"
    try:
        fuse(bad, groups)
    except AssertionError as e:
        assert "bare" in str(e), e
    else:
        raise AssertionError("bare read accepted")
    # different images do not fuse
    try:
        fuse(doc, {"chain": ("Chain", "w/chain/", ["st", "down"])})
    except AssertionError as e:
        assert "executor" in str(e), e
    else:
        raise AssertionError("mixed images accepted")
    print("selftest ok")
    return 0


def main(argv: list[str]) -> int:
    if argv == ["--selftest"]:
        return selftest()
    check = argv[:1] == ["--check"]
    ports = (argv[1:] if check else argv) or list(PORTS)
    bad = 0
    for port in ports:
        text, dst = generate(port), ROOT / port / "workflow.fused.yaml"
        if check:
            ok = dst.is_file() and dst.read_text() == text
            bad += not ok
            print(f"{port}/workflow.fused.yaml is " + ("up to date" if ok else "STALE: run tools/gen_fused.py"))
        else:
            dst.write_text(text)
            print(f"wrote {dst.relative_to(ROOT)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
