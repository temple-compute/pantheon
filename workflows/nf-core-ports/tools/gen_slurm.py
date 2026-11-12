#!/usr/bin/env python3
"""
Generate the Slurm (AWS ParallelCluster) variant of an nf-core port: the route

    nextflow run nf-core/<p> -profile singularity -c slurm.config -params-file params.yaml

takes on the bench cluster (tc-os scripts/bench/nfcore/slurm-nfcore). The generic
form of w02-rnaseq/scripts/gen_real.py, without its rnaseq-specific surgery:

- every container task is a Slurm job (`kind: slurm`, `inner: local`) in Apptainer,
  with the .sif file Nextflow's singularity cache holds for the module's image
  (SingularityCache.simpleName of the module's singularity URL) in /fsx/sif;
- cpus / memory / walltime are the nf-core ones: the process's labels and withName
  settings in conf/base.config and the configs nextflow.config includes, capped to
  the node of its queue. The queue is <p>-compute (m7i.4xlarge), or <p>-highmem
  (r7i.2xlarge) when the process asks for more memory than a compute node has or
  matches --highmem. The highmem process list is printed for slurm.config;
- shell tasks (the glue Nextflow runs as Groovy) stay on the head node (kind: local);
- --link-reference replaces a build task with a head-node task that symlinks a
  prebuilt index or reference from /fsx/data/<p>/ into its outputs;
- no capacity block, max_concurrency on the workflow and every map, cache: fast.

Labels come from the pipeline source (--nf, a checkout of the release the port
follows, e.g. ~/.nextflow/assets/.repos/nf-core/<p>/clones/<sha>). Each container
task maps to a process by its `name` (the last NAME token, aliases resolved), else
by its image. The resolved values capped at conf/test.config's resourceLimits are
checked against the port's own resources (the test-profile trace values).

usage: gen_slurm.py SRC.yaml --nf DIR [-o DST.yaml] [--queue-prefix P-] [--highmem REGEX]
                    [--link-reference TASK:OUTPUT[/NAME]=PATH ...] [--set ARTIFACT=VALUE ...]
                    [--label TASK=LABEL[,LABEL] ...] [--max-concurrency N] [--cache fast|deep]
       gen_slurm.py --selftest
Needs PyYAML.
"""

from __future__ import annotations

import argparse
import re
import shlex
import sys
import tempfile
from pathlib import Path
from typing import ClassVar

import yaml

SIF_DIR = "/fsx/sif"
SLURM_DIR = "@SLURM_DIR@"  # replaced by the driver (slurm-nfcore/matrix.sh)
# Slurm node per queue kind: vCPUs and the memory cap slurm.config uses (95% of
# 64 GiB is 60.8 GiB RealMemory; nf-core resourceLimits 58 GB), and a 24 h time cap.
NODE = {"compute": (16, 58), "highmem": (8, 58)}
TIME_CAP_H = 24
MAX_CONCURRENCY = 200  # Nextflow's queueSize in slurm.config
KEYS = ("kind", "id", "name", "description", "over", "chain", "zip", "drop_exit_codes", "max_concurrency",
        "inputs", "outputs", "resources", "executor", "runtime", "target")


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


def docker_norm(image: str, registry: str = "quay.io") -> str:
    """The image with nf-core's docker/singularity.registry prepended when it names no registry."""
    first = image.split("/", 1)[0]
    return image if "/" in image and ("." in first or ":" in first or first == "localhost") else f"{registry}/{image}"


# ---------------------------------------------------------------- pipeline source

def processes(nf: Path) -> tuple[dict[str, list[dict]], dict[str, set[str]]]:
    """process name -> [{labels, docker, sif}] over every .nf file, and alias -> process names."""
    procs: dict[str, list[dict]] = {}
    alias: dict[str, set[str]] = {}
    for f in sorted(nf.rglob("*.nf")):
        text = f.read_text(errors="replace")
        for m in re.finditer(r"include\s*\{([^}]*)\}", text):
            for a in re.finditer(r"(\w+)\s+as\s+(\w+)", m.group(1)):
                alias.setdefault(a.group(2), set()).add(a.group(1))
        starts = list(re.finditer(r"^\s*process\s+(\w+)\s*\{", text, re.MULTILINE))
        for i, m in enumerate(starts):
            body = text[m.end():starts[i + 1].start() if i + 1 < len(starts) else len(text)]
            labels = re.findall(r"^\s*label\s+['\"]([^'\"]+)['\"]", body, re.MULTILINE)
            docker = sif = None
            c = re.search(r"^\s*container\s+(\"\$\{.*?\}\"|'[^']*'|\"[^\"]*\")", body, re.MULTILINE | re.DOTALL)
            if c:
                lits = [s for s in re.findall(r"'([^']+)'", c.group(1)) if s not in ("singularity", "apptainer")]
                if not lits:  # container "image"
                    lits = [c.group(1).strip("'\"")]
                docker = docker_norm(lits[-1])
                # the singularity URL; a GPU image ahead of it (ext.use_gpu ? 'x' : ...) has no scheme
                sif = next((s for s in lits[:-1] if "://" in s), f"docker://{docker}")
            # the module's own cpus / memory / time directives (config selectors override them)
            head = re.split(r"^\s*(?:input|output|when|script|shell|exec|stub)\s*:", body, maxsplit=1, flags=re.MULTILINE)[0]
            own = dict(re.findall(r"^\s*(cpus|memory|time)\s+(\S.*?)\s*$", head, re.MULTILINE))
            procs.setdefault(m.group(1), []).append({"name": m.group(1), "labels": labels, "docker": docker,
                                                     "sif": sif, "own": own, "file": str(f)})
    return procs, alias


UNIT = {"B": 1 / 1024**3, "KB": 1 / 1024**2, "MB": 1 / 1024, "GB": 1, "TB": 1024,
        "ms": 1 / 3600e3, "s": 1 / 3600, "min": 1 / 60, "m": 1 / 60, "h": 1, "d": 24}


def value(s: str) -> float | None:
    """A config value like `{ 6.GB * task.attempt }` on the first attempt, in cpus, GB or hours; None unless arithmetic."""
    s = s.split("//")[0].strip()
    s = re.sub(r"^\{\s*(.*?)\s*\}$", r"\1", s)
    s = re.sub(r"check_max\(\s*(.*?)\s*,\s*'\w+'\s*\)", r"\1", s)
    s = s.replace("task.attempt", "1").strip().strip("'\"")
    s = re.sub(r"(\d+(?:\.\d+)?)\s*\.?\s*(KB|MB|GB|TB|B|ms|min|s|m|h|d)\b", lambda m: f"({m.group(1)}*{UNIT[m.group(2)]})", s)
    if not re.fullmatch(r"[\d.\s+\-*/()e]+", s):
        return None
    try:
        return float(eval(s, {"__builtins__": {}}))  # digits and operators only, checked above
    except (SyntaxError, ZeroDivisionError):
        return None


def selectors(text: str):
    """(kind, pattern, {cpus|memory|time: raw}) for every withLabel / withName block, and the settings outside them."""
    out, spans = [], []
    for m in re.finditer(r"(withLabel|withName)\s*:\s*(?:'([^']*)'|\"([^\"]*)\"|([\w.*|:!^$-]+))\s*\{", text):
        depth, i = 1, m.end()
        while depth and i < len(text):
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        body = text[m.end():i - 1]
        out.append((m.group(1), m.group(2) or m.group(3) or m.group(4), settings(body)))
        spans.append((m.start(), i))
    rest = "".join(text[a:b] for a, b in zip([0] + [e for _s, e in spans], [s for s, _e in spans] + [len(text)]))
    return out, settings(rest)


def settings(body: str) -> dict[str, str]:
    return {k: v for k, v in re.findall(r"^\s*(cpus|memory|time)\s*=\s*(.+?)\s*$", body, re.MULTILINE)}


def configs(nf: Path) -> list[Path]:
    """conf/base.config, then the configs nextflow.config includes unconditionally, in order."""
    main = (nf / "nextflow.config").read_text()
    inc = [nf / p for p in re.findall(r"^includeConfig\s+['\"](conf/[^'\"]+)['\"]", main, re.MULTILINE)]
    base = nf / "conf" / "base.config"
    return [base] + [p for p in inc if p != base and "igenomes" not in p.name and p.exists()]


def qualified(task: dict) -> str:
    """A stand-in for the qualified process name: 'WF:' + the task name's NAME tokens."""
    name = re.sub(r"\s*\(.*\)$", "", task.get("name") or "").strip()
    return "WF:" + ":".join(re.split(r"[\s:]+", name))


class Resolver:
    def __init__(self, nf: Path):
        self.procs, self.alias = processes(nf)
        self.default: dict[str, str] = {}
        self.label_sel, self.name_sel = [], []
        for i, f in enumerate(configs(nf)):
            sel, rest = selectors(f.read_text())
            if i == 0:
                self.default = rest
            for kind, pat, s in sel:
                (self.label_sel if kind == "withLabel" else self.name_sel).append((pat, s))
        test = nf / "conf" / "test.config"
        lim = re.search(r"resourceLimits\s*=\s*\[(.*?)\]", test.read_text(), re.DOTALL) if test.exists() else None
        self.test_cap = None
        if lim:
            c = re.search(r"cpus\s*:\s*(\d+)", lim.group(1))
            m = re.search(r"memory\s*:\s*['\"]([^'\"]+)['\"]", lim.group(1))
            self.test_cap = (int(c.group(1)), value(m.group(1))) if c and m else None
        env = re.search(r"^env\s*\{(.*?)^\}", (nf / "nextflow.config").read_text(), re.MULTILINE | re.DOTALL)
        self.env = {k: v.strip("'\"") for k, v in re.findall(r"^\s*(\w+)\s*=\s*(\S+)", env.group(1), re.MULTILINE)} if env else {}
        self.sif = {p["docker"]: p["sif"] for ps in self.procs.values() for p in ps if p["docker"]}

    def process(self, task: dict, image: str) -> tuple[str, dict] | None:
        """(invoked name, process) for a container task."""
        for tok in reversed(qualified(task).split(":")[1:]):
            cands = [p for b in self.alias.get(tok, set()) | {tok} for p in self.procs.get(b, [])]
            if cands:
                return tok, next((p for p in cands if p["docker"] == image), cands[0])
        same = [(n, p) for n, ps in self.procs.items() for p in ps if p["docker"] == image]
        if same and len({tuple(p["labels"]) for _n, p in same}) == 1:
            return same[0]
        return None

    @staticmethod
    def _match(pat: str, names: list[str]) -> bool:
        """Nextflow matches withName on the process name, its alias and the qualified name. That last one
        is not known here: the task name stands in for it, and a qualified pattern also counts when its
        last part matches."""
        neg = pat.startswith("!")
        pat = pat.lstrip("!")
        # shortcut: '.*:SUBWF:NAME' then also hits NAME under other subworkflows; the test-profile
        # check in build() catches a wrong pick that changes resources.
        last, depth = 0, 0
        for i, ch in enumerate(pat):
            depth += {"(": 1, ")": -1}.get(ch, 0)
            if ch == ":" and depth == 0:
                last = i + 1
        try:
            hit = any(re.fullmatch(pat, n) or (last and re.fullmatch(pat[last:], n)) for n in names)
        except re.error:
            return False
        return bool(hit) != neg

    def resources(self, proc: dict, invoked: str, qualified: str) -> tuple[dict[str, float], list[tuple[str, str]]]:
        """{cpus, memory, time} as Nextflow resolves them on the first attempt, and the (key, raw) values
        that are not constants."""
        raw = {**self.default, **proc.get("own", {})}
        for pat, s in self.label_sel:
            if self._match(pat, proc["labels"]):
                raw.update(s)
        for pat, s in self.name_sel:
            if self._match(pat, [proc["name"], invoked, qualified]):
                raw.update(s)
        vals, odd = {"cpus": 1.0, "memory": 6.0, "time": 4.0}, []
        for k, v in raw.items():
            x = value(v)
            if x is None:
                odd.append((k, v))
            else:
                vals[k] = x
        return vals, odd


# ---------------------------------------------------------------- build

def hms(h: float) -> str:
    m = round(h * 60)
    return f"{m // 60:02d}:{m % 60:02d}:00"


def num(x: float):
    return int(x) if float(x).is_integer() else round(x, 2)


def link_command(task: dict, links: list[tuple[str, str | None, str]]) -> str:
    outs = {a["id"]: a for a in task["outputs"]}
    lines = ["set -eu"]
    for out, _n, src in links:
        assert out in outs, f"--link-reference {task['id']}:{out}: {task['id']} has no output {out}"
        lines.append(f"test -e {shlex.quote(src)}")
    for out in dict.fromkeys(o for o, _n, _s in links):
        lines.append(f'rm -rf ${{{out}}} && mkdir -p "$$(dirname ${{{out}}})"' if outs[out]["kind"] == "file"
                     else f"rm -rf ${{{out}}} && mkdir -p ${{{out}}}")
    for out, name, src in links:
        dst = f"${{{out}}}" if outs[out]["kind"] == "file" else f"${{{out}}}/{name or Path(src).name}"
        lines.append(f"ln -s {shlex.quote(src)} {dst}")
    missing = set(outs) - {o for o, _n, _s in links}
    assert not missing, f"--link-reference {task['id']}: outputs {sorted(missing)} get no link"
    return "\n".join(lines) + "\n"


def build(doc: dict, rv: Resolver, prefix: str, highmem: str | None = None, links=None, sets=None,
          labels=None, mc: int = MAX_CONCURRENCY, cache: str = "fast") -> tuple[dict, dict]:
    links, sets, labels = links or {}, sets or {}, labels or {}
    targets = {"local": {"kind": "local"}}
    for q in NODE:
        targets[q] = {"kind": "slurm", "partition": f"{prefix}{q}", "working_directory": SLURM_DIR,
                      "inner": {"kind": "local"}}
    res: dict[tuple, dict] = {}
    img: dict[str, dict] = {}
    info = {"highmem": set(), "odd": [], "test_mismatch": [], "docker_sif": [], "unresolved": []}

    out = []
    for t in doc["tasks"]:
        tid = t["id"]
        if tid in links:
            assert t["kind"] == "horus_task", f"--link-reference {tid}: a map cannot be linked"
            out.append({"kind": "horus_task", "id": tid, "name": f"Link {t.get('name', tid)}",
                        "description": "Links the prebuilt files instead of building them.",
                        "inputs": [], "outputs": t["outputs"], "executor": {"kind": "shell"},
                        "runtime": {"kind": "command", "command": link_command(t, links[tid])},
                        "target": targets["local"]})
            continue
        rt = t["runtime"]
        if "command" in rt:  # Apptainer shares the host's /tmp: several jobs on one node need their own file
            rt["command"] = rt["command"].replace("/tmp/.command.sh", "/tmp/.command.$$$$.sh")
        ex = t["executor"]
        if ex["kind"] == "shell":
            t["target"] = targets["local"]
        else:
            image = ex["image"]
            if tid in labels:
                invoked, proc = t.get("name", tid), {"name": t.get("name", tid), "labels": labels[tid], "docker": image}
            else:
                hit = rv.process(t, image)
                if hit is None:
                    info["unresolved"].append(f"{tid} ({t.get('name')})")
                    continue
                invoked, proc = hit
            want, odd = rv.resources(proc, invoked, qualified(t))
            got = (t["resources"]["cpus"], t["resources"]["memory_gb"]) if "resources" in t else None
            for k, raw in odd:
                # Under the test profile's cap the port's value is the uncapped one (for test's params).
                i = {"cpus": 0, "memory": 1}.get(k)
                use = i is not None and got and rv.test_cap and got[i] < rv.test_cap[i]
                if use:
                    want[k] = got[i]
                info["odd"].append(f"{tid} ({invoked}): {k} {raw} -> {num(want[k])}{' (test profile)' if use else ''}")
            if rv.test_cap and got:
                tc, tm = rv.test_cap
                exp = (min(int(want["cpus"]), tc), min(want["memory"], tm))
                if (exp[0], round(exp[1], 1)) != (got[0], round(float(got[1]), 1)):
                    info["test_mismatch"].append(f"{tid} ({invoked} {','.join(proc['labels'])}): test {got}, "
                                                 f"config capped {exp[0]}/{num(exp[1])}")
            hm = want["memory"] > NODE["compute"][1] or bool(highmem and re.fullmatch(highmem, invoked))
            q = "highmem" if hm else "compute"
            if hm:
                info["highmem"].add(invoked)
            ncpu, nmem = NODE[q]
            key = (min(int(want["cpus"]), ncpu), num(min(want["memory"], nmem)), hms(min(want["time"], TIME_CAP_H)))
            t["resources"] = res.setdefault(key, {"cpus": key[0], "memory_gb": key[1], "walltime": key[2]})
            src = proc["sif"] if proc.get("docker") == image and proc.get("sif") else rv.sif.get(image)
            if not src:
                src = f"docker://{image}"
                info["docker_sif"].append(image)
            if image not in img:
                img[image] = {"kind": "apptainer", "image": f"{SIF_DIR}/{sif_name(src)}", "binds": {"/fsx": "/fsx"},
                              "env": {**rv.env, **ex.get("env", {})}, "extra_args": ["--cleanenv", "--no-home"],
                              "_src": src}
            t["executor"] = img[image]
            t["target"] = targets[q]
        if t["kind"] == "horus_map":
            t["max_concurrency"] = mc
        out.append({k: t[k] for k in KEYS if k in t})
    assert not info["unresolved"], "no nf-core process for " + ", ".join(info["unresolved"]) + " (use --label)"
    assert set(links) <= {t["id"] for t in out}, f"--link-reference: no task {set(links) - {t['id'] for t in out}}"

    roots = doc["artifacts"]
    for aid, v in sets.items():
        a = next((a for a in roots if a["id"] == aid), None)
        assert a is not None, f"--set {aid}: no root artifact {aid}"
        a["value"] = v
    linked = set(links)
    edges = [e for e in doc["edges"] if e["target"] not in linked]
    sif, inames = {}, {}
    for image, e in img.items():
        sif[e["image"].rsplit("/", 1)[1]] = Q(e.pop("_src"))
        base = re.sub(r"\W", "_", image.rsplit("/", 1)[-1].split(":")[0])
        inames[f"{base}_{sum(k.startswith(base) for k in inames)}" if base in inames else base] = e
    arts = {id(a): a for t in out for a in (*t.get("inputs", []), *t.get("outputs", []))}
    new = {
        "kind": doc["kind"], "name": doc["name"] + " slurm", "max_concurrency": mc, "cache": cache,
        "_sif": dict(sorted(sif.items())),  # .sif file -> what to pull; rnaseq-real/pull_sifs.sh reads the quoted URLs
        "_targets": targets, "_res": {f"r{c}_{m}_{h[:2]}h": v for (c, m, h), v in sorted(res.items())},
        "_img": inames, "_art": list(arts.values()),
        "artifacts": roots, "tasks": out, "edges": edges,
        "orchestrator_target": doc["orchestrator_target"],
    }
    return new, info


def check(doc: dict, prefix: str) -> None:
    ids = {t["id"] for t in doc["tasks"]}
    roots = {f"artifact-{a['id']}" for a in doc["artifacts"]}
    for e in doc["edges"]:
        assert e["target"] in ids and (e["source"] in ids or e["source"] in roots), e
    assert "capacity" not in doc and doc["cache"] in ("fast", "deep")
    for t in doc["tasks"]:
        tid, tg, ex = t["id"], t["target"], t["executor"]
        cmd = t["runtime"].get("command", "")
        assert "/tmp/.command.sh" not in cmd, tid
        if t["kind"] == "horus_map":
            assert t["max_concurrency"] == doc["max_concurrency"], tid
        if ex["kind"] == "shell":
            assert tg == {"kind": "local"}, tid
            continue
        assert ex["kind"] == "apptainer" and ex["image"].startswith(SIF_DIR + "/"), tid
        assert tg["kind"] == "slurm" and tg["inner"] == {"kind": "local"} and tg["working_directory"] == SLURM_DIR, tid
        q = tg["partition"].removeprefix(prefix)
        r = t["resources"]
        assert q in NODE and r["cpus"] <= NODE[q][0] and r["memory_gb"] <= NODE[q][1], (tid, q, r)


# ---------------------------------------------------------------- dump

class Q(str):
    """A string dumped double-quoted."""


class Dumper(yaml.SafeDumper):
    names: ClassVar[dict[int, str]] = {}

    def generate_anchor(self, node):
        for key, n in self.represented_objects.items():
            if n is node and key in self.names:
                return self.names[key]
        return super().generate_anchor(node)


def _scalar(v) -> bool:
    return isinstance(v, (str, int, float, bool)) and "\n" not in str(v)


def _dict(d, data):
    node = d.represent_mapping("tag:yaml.org,2002:map", data)
    node.flow_style = all(_scalar(v) for v in data.values()) and len(str(data)) < 200
    return node


def _list(d, data):
    node = d.represent_sequence("tag:yaml.org,2002:seq", data)
    node.flow_style = all(_scalar(v) for v in data)
    return node


Dumper.add_representer(str, lambda d, s: d.represent_scalar("tag:yaml.org,2002:str", s, style="|" if "\n" in s else None))
Dumper.add_representer(Q, lambda d, s: d.represent_scalar("tag:yaml.org,2002:str", str(s), style='"'))
Dumper.add_representer(dict, _dict)
Dumper.add_representer(list, _list)


def dump(doc: dict) -> str:
    names = {id(v): f"t_{k}" for k, v in doc["_targets"].items()}
    names |= {id(v): f"res_{k}" for k, v in doc["_res"].items()}
    names |= {id(v): f"img_{k}" for k, v in doc["_img"].items()}
    seen = set()
    for a in doc["_art"]:  # the first object per id gets the readable name, any other one a generated anchor
        if a["id"] not in seen:
            seen.add(a["id"])
            names[id(a)] = f"a_{a['id']}"
    Dumper.names = names
    return yaml.dump(doc, Dumper=Dumper, sort_keys=False, width=4096, allow_unicode=True)


HEAD = """\
# Generated by tools/gen_slurm.py from {src}; do not edit by hand.
#   {argv}
# Slurm variant for the bench ParallelCluster (tc-os scripts/bench/nfcore/slurm-nfcore):
# container tasks are Slurm jobs on {prefix}compute / {prefix}highmem in Apptainer
# ({sif_dir}, _sif lists the source of each file), with nf-core's cpus / memory / time
# for their process capped to the node; shell tasks run on the head node; max_concurrency
# {mc}, cache: {cache}, no capacity block. Slurm working_directory {slurm} is replaced by the driver.
# Highmem processes (slurm.config): {highmem}
{notes}#
# {n} tasks ({maps} maps).
"""


def generate(src: Path, dst: Path, nf: Path, argv: str, **kw) -> dict:
    doc = yaml.safe_load(src.read_text())
    rv = Resolver(nf)
    new, info = build(doc, rv, **kw)
    check(new, kw.get("prefix", ""))
    text = dump(new)
    check(yaml.safe_load(text), kw.get("prefix", ""))  # the dumped file reads back the same
    notes = "".join(f"# {k}: {v}\n" for k, v in (
        ("Linked instead of built", ", ".join(kw.get("links") or {}) or None),
        ("Not constant in the config (default kept)", "; ".join(info["odd"]) or None),
        ("Test-profile values that differ from the config", "; ".join(info["test_mismatch"]) or None),
        ("No singularity URL in the pipeline (docker:// pulled)", ", ".join(sorted(set(info["docker_sif"]))) or None),
    ) if v)
    maps = sum(t["kind"] == "horus_map" for t in new["tasks"])
    dst.write_text(HEAD.format(src=src.name, argv=argv, prefix=kw.get("prefix", ""), sif_dir=SIF_DIR,
                               mc=new["max_concurrency"], cache=new["cache"], slurm=SLURM_DIR,
                               highmem="|".join(sorted(info["highmem"])) or "-", notes=notes,
                               n=len(new["tasks"]), maps=maps) + text)
    return {"tasks": len(new["tasks"]), "maps": maps, **info}


# ---------------------------------------------------------------- self-test

def selftest() -> None:
    assert sif_name("https://depot.galaxyproject.org/singularity/fastqc:0.12.1--hdfd78af_0") == \
        "depot.galaxyproject.org-singularity-fastqc-0.12.1--hdfd78af_0.img"
    assert sif_name("docker://quay.io/biocontainers/fq:0.12.0--h9ee0642_0") == "quay.io-biocontainers-fq-0.12.0--h9ee0642_0.img"
    assert sif_name("oras://x.io/a/b.sif:1") == "x.io-a-b-1.sif"
    assert docker_norm("biocontainers/fastqc:1") == "quay.io/biocontainers/fastqc:1"
    assert docker_norm("community.wave.seqera.io/library/x:1") == "community.wave.seqera.io/library/x:1"
    assert value("{ 36.GB * task.attempt }") == 36 and value("{ check_max( 6 * task.attempt, 'cpus' ) }") == 6
    assert value("'15.GB'") == 15 and value("{ 20.h * task.attempt }") == 20 and value("{ 1 }") == 1
    assert value("{ 72.GB * (2 ** (task.attempt - 1)) }") == 72 and value("512.MB") == 0.5
    assert value("{ params.x ? 30.GB : 18.GB }") is None and value("{ 7.B * fasta.size() }") is None
    with tempfile.TemporaryDirectory() as d:
        nf = Path(d)
        (nf / "conf").mkdir()
        (nf / "modules/a").mkdir(parents=True)
        (nf / "nextflow.config").write_text("env {\n    PYTHONNOUSERSITE = 1\n}\nincludeConfig 'conf/base.config'\n"
                                            "includeConfig 'conf/modules.config'\n")
        (nf / "conf/base.config").write_text(
            "process {\n  cpus = { 1 * task.attempt }\n  memory = { 6.GB * task.attempt }\n  time = { 4.h * task.attempt }\n"
            "  withLabel:process_medium { cpus = { 6 * task.attempt }\n memory = { 36.GB * task.attempt }\n }\n"
            "  withLabel:process_high { cpus = { 12 * task.attempt }\n memory = { 72.GB * task.attempt }\n"
            "    time = { 16.h * task.attempt }\n  }\n}\n")
        (nf / "conf/modules.config").write_text("process {\n withName: '.*:SUB:TOOL_B' {\n  cpus = 8\n ext.args = { [\n '-x'\n ].join(' ') }\n }\n}\n")
        (nf / "conf/test.config").write_text("process {\n resourceLimits = [ cpus: 4, memory: '15.GB', time: '1.h' ]\n}\n")
        (nf / "modules/a/main.nf").write_text(
            "process TOOL_A {\n    label 'process_high'\n    container \"${ workflow.containerEngine == 'singularity' ?\n"
            "        'https://depot.galaxyproject.org/singularity/a:1--0' :\n        'biocontainers/a:1--0' }\"\n}\n"
            "process TOOL_B {\n    label 'process_medium'\n    container 'biocontainers/b:2'\n}\n"
            "process TOOL_G {\n    container \"${ task.ext.use_gpu ? 'us.gcr.io/g:1' :\n"
            "        workflow.containerEngine in ['singularity', 'apptainer'] ? 'https://x.io/g/data' : 'c.io/g:1' }\"\n}\n")
        (nf / "main.nf").write_text("include { TOOL_A as TOOL_A_RAW } from './modules/a'\n")
        rv = Resolver(nf)
        assert rv.test_cap == (4, 15) and rv.env == {"PYTHONNOUSERSITE": "1"}
        assert rv.procs["TOOL_G"][0]["sif"] == "https://x.io/g/data" and rv.procs["TOOL_G"][0]["docker"] == "c.io/g:1"
        sh = {"kind": "horus_task", "id": "stage", "inputs": [], "outputs": [{"id": "ref", "kind": "folder", "path": "w/ref/"}],
              "executor": {"kind": "shell"}, "runtime": {"kind": "command", "command": "true"}, "target": {"kind": "local"}}
        idx = {"kind": "horus_task", "id": "idx", "name": "BUILD", "inputs": sh["outputs"],
               "outputs": [{"id": "index", "kind": "folder", "path": "w/index/"}],
               "executor": {"kind": "docker", "image": "quay.io/biocontainers/b:2"}, "resources": {"cpus": 4, "memory_gb": 15},
               "runtime": {"kind": "command", "command": "x"}, "target": {"kind": "local"}}
        a = {"kind": "horus_map", "id": "a", "name": "WF TOOL_A_RAW", "over": {"input_id": "ref", "as": "s"},
             "inputs": [*sh["outputs"], *idx["outputs"]], "outputs": [{"id": "out", "kind": "folder", "path": "w/out/"}],
             "executor": {"kind": "docker", "image": "quay.io/biocontainers/a:1--0", "env": {"X": "1"}},
             "resources": {"cpus": 4, "memory_gb": 15}, "max_concurrency": 16,
             "runtime": {"kind": "command", "command": "cat > /tmp/.command.sh\nbash /tmp/.command.sh"}, "target": {"kind": "local"}}
        b = {**a, "id": "b", "name": "TOOL_B (merged)", "kind": "horus_task", "executor": {"kind": "docker", "image": "quay.io/biocontainers/b:2"},
             "inputs": a["outputs"], "outputs": [{"id": "bo", "kind": "file", "path": "w/b.txt"}]}
        del b["over"], b["max_concurrency"]
        doc = {"kind": "horus_workflow", "name": "t", "capacity": {}, "artifacts": [{"id": "x", "kind": "string", "path": "p/x.txt", "value": ""}],
               "tasks": [sh, idx, a, b], "orchestrator_target": {"kind": "local"},
               "edges": [{"source": "stage", "source_output": "ref", "target": "idx", "target_input": "ref"},
                         {"source": "stage", "source_output": "ref", "target": "a", "target_input": "ref"},
                         {"source": "idx", "source_output": "index", "target": "a", "target_input": "index"},
                         {"source": "a", "source_output": "out", "target": "b", "target_input": "out"}]}
        pristine = yaml.safe_dump(doc)
        new, info = build(yaml.safe_load(pristine), rv, "demo-", links={"idx": [("index", "bt2", "/fsx/data/demo/index")]}, sets={"x": "/fsx/x"})
        check(new, "demo-")
        t = {t["id"]: t for t in new["tasks"]}
        assert t["a"]["target"]["partition"] == "demo-highmem" and t["a"]["resources"] == {"cpus": 8, "memory_gb": 58, "walltime": "16:00:00"}
        assert t["b"]["target"]["partition"] == "demo-compute" and t["b"]["resources"]["cpus"] == 8  # withName beats the label
        assert t["a"]["executor"]["image"] == "/fsx/sif/depot.galaxyproject.org-singularity-a-1--0.img"
        assert t["a"]["executor"]["env"] == {"PYTHONNOUSERSITE": "1", "X": "1"} and t["a"]["max_concurrency"] == 200
        assert t["b"]["executor"]["image"] == "/fsx/sif/quay.io-biocontainers-b-2.img"
        assert "/tmp/.command.$$$$.sh" in t["a"]["runtime"]["command"]
        assert t["idx"]["executor"] == {"kind": "shell"} and "ln -s /fsx/data/demo/index ${index}/bt2" in t["idx"]["runtime"]["command"]
        assert all(e["target"] != "idx" for e in new["edges"]) and new["artifacts"][0]["value"] == "/fsx/x"
        assert info["highmem"] == {"TOOL_A_RAW"} and info["test_mismatch"] == [] and "capacity" not in new
        assert new["_sif"]["quay.io-biocontainers-b-2.img"] == "docker://quay.io/biocontainers/b:2"
        assert '"https://depot.galaxyproject.org/singularity/a:1--0"' in dump(new)
        _, info = build(yaml.safe_load(pristine), rv, "demo-", highmem="TOOL_B")
        assert info["highmem"] == {"TOOL_A_RAW", "TOOL_B"}
    print("selftest ok")


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate the Slurm variant of an nf-core port.")
    ap.add_argument("src", nargs="?", type=Path, help="the port's workflow YAML (faithful or chained)")
    ap.add_argument("-o", "--out", type=Path, help="default: workflow.slurm.yaml next to SRC")
    ap.add_argument("--nf", type=Path, help="nf-core pipeline checkout of the release the port follows")
    ap.add_argument("--queue-prefix", help="queue name prefix (default '<p>-' from the port dir wNN-<p>; '' for rnaseq-real)")
    ap.add_argument("--highmem", help="regex of process names that also go to the highmem queue")
    ap.add_argument("--link-reference", action="append", default=[], metavar="TASK:OUTPUT[/NAME]=PATH",
                    help="replace TASK with a head-node task linking PATH into OUTPUT (as NAME, default PATH's name)")
    ap.add_argument("--set", action="append", default=[], metavar="ARTIFACT=VALUE", help="root artifact value")
    ap.add_argument("--label", action="append", default=[], metavar="TASK=LABEL[,LABEL]",
                    help="labels for a task whose process is not found")
    ap.add_argument("--max-concurrency", type=int, default=MAX_CONCURRENCY)
    ap.add_argument("--cache", choices=("fast", "deep"), default="fast")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return 0
    if not a.src or not a.nf:
        ap.error("SRC and --nf are required")
    links: dict[str, list] = {}
    for spec in a.link_reference:
        m = re.fullmatch(r"(\w+):(\w+)(?:/([^=]+))?=(/.+)", spec)
        if not m:
            ap.error(f"--link-reference {spec}: want TASK:OUTPUT[/NAME]=/ABS/PATH")
        links.setdefault(m.group(1), []).append((m.group(2), m.group(3), m.group(4)))
    prefix = a.queue_prefix
    if prefix is None:
        m = re.fullmatch(r"w\d+-([a-z][a-z0-9]*)", a.src.resolve().parent.name)
        if not m:
            ap.error("--queue-prefix: cannot tell <p> from the port dir")
        prefix = m.group(1) + "-"
    dst = a.out or a.src.with_name("workflow.slurm.yaml")
    argv = " ".join(shlex.quote(x) for x in ["gen_slurm.py", *sys.argv[1:]])
    r = generate(a.src, dst, a.nf, argv, prefix=prefix, highmem=a.highmem, links=links,
                 sets=dict(s.split("=", 1) for s in a.set),
                 labels={k: v.split(",") for k, v in (s.split("=", 1) for s in a.label)},
                 mc=a.max_concurrency, cache=a.cache)
    print(f"wrote {dst}: {r['tasks']} tasks, {r['maps']} maps; highmem: {'|'.join(sorted(r['highmem'])) or '-'}; "
          f"{len(r['test_mismatch'])} test-profile mismatches, {len(r['odd'])} non-constant settings, "
          f"{len(set(r['docker_sif']))} docker:// images")
    for k in ("test_mismatch", "odd"):
        for x in r[k]:
            print(f"  {k}: {x}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
