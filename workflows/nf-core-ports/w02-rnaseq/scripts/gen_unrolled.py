#!/usr/bin/env python3
"""
Generate workflow.unrolled.yaml from workflow.chained.yaml: a plain DAG with
no maps, for timing chaining's dataflow on a runtime without `chain`.

Each map becomes one horus_task per slot for the samples in the default
samplesheet (slot i = i-th sample id, sorted, as the map would number it).
A slot task reads and writes that slot's folder (<map path>/<slot>/), so the
layout matches the chained run. `${<over as>}` and the zip aliases become the
upstream slot folders; the head map's item becomes `${samples}/<id>`.
Gathers get all slot folders as inputs and glob their parent:
`${x}` -> `$$(dirname ${x_0})`, which works because every task runs on one node
and docker mounts each input's parent folder.

usage: gen_unrolled.py [workflow.chained.yaml] [workflow.unrolled.yaml]   (needs PyYAML)
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import yaml
from gen_tuned import Dumper, derive_edges, edge_set

HERE = Path(__file__).resolve().parent.parent
DROP = ("kind", "over", "chain", "zip", "max_concurrency", "drop_exit_codes")


def sub(text: str, old: str, new: str) -> str:
    """Replace the template `${old}`, not a bash `$${old}`."""
    return re.sub(r"(?<!\$)\$\{" + re.escape(old) + r"\}", lambda _: new, text)


def runtime(t: dict, pairs: list[tuple[str, str]]) -> dict:
    rt = dict(t["runtime"])
    for key in ("command", "args"):
        if key in rt:
            for old, new in pairs:
                rt[key] = sub(rt[key], old, new)
    return rt


def unroll(doc: dict, samples: list[str]) -> dict:
    maps = {t["id"]: t for t in doc["tasks"] if t["kind"] == "horus_map"}
    width = max(1, len(str(len(samples) - 1)))
    slots = [f"{i:0{width}d}" for i in range(len(samples))]

    def slot_art(m: str, slot: str) -> dict:
        out = maps[m]["outputs"][0]
        return {**out, "id": f"{m}_{slot}", "path": out["path"].rstrip("/") + f"/{slot}/"}

    tasks = []
    for t in doc["tasks"]:
        if t["id"] not in maps:
            # Gather (or plain task): every slot folder in, glob their parent.
            reads = [i["id"] for i in t.get("inputs", []) if i["id"] in maps]
            if reads:
                assert t["runtime"]["kind"] == "command", t["id"]
            inputs = []
            for i in t.get("inputs", []):
                inputs += [slot_art(i["id"], s) for s in slots] if i["id"] in maps else [i]
            pairs = [(m, f"$$(dirname ${{{m}_{slots[0]}}})") for m in reads]
            tasks.append({**t, "inputs": inputs, "runtime": runtime(t, pairs)})
            continue
        over = t["over"]
        zips = {z["input_id"]: z["as"] for z in t.get("zip") or []}
        head = over["input_id"] not in maps
        assert head != bool(t.get("chain")), t["id"]
        for slot, sample in zip(slots, samples, strict=True):
            inputs, pairs = [], [(t["id"], f"${{{t['id']}_{slot}}}")]
            for i in t["inputs"]:
                src = i["id"]
                if src in maps:
                    assert src == over["input_id"] or src in zips, f"{t['id']} reads map {src} unpaired"
                    inputs.append(slot_art(src, slot))
                    pairs.append((zips.get(src, over["as"]), f"${{{src}_{slot}}}"))
                else:
                    inputs.append(i)
            if head:
                pairs.append((over["as"], f"${{{over['input_id']}}}/{sample}"))
            new = {k: v for k, v in t.items() if k not in DROP}
            new.update(id=f"{t['id']}_{slot}", name=f"{t['name']}[{slot}]", inputs=inputs,
                       outputs=[slot_art(t["id"], slot)], runtime=runtime(t, pairs))
            tasks.append({"kind": "horus_task", **new})

    names = {t["over"]["as"] for t in maps.values()} | {z["as"] for t in maps.values() for z in t.get("zip") or []}
    for t in tasks:
        text = yaml.safe_dump(t["runtime"])
        left = [n for n in names | set(maps) if re.search(r"(?<!\$)\$\{" + n + r"\}", text)]
        assert not left, f"{t['id']} still names {left}"
    assert len({t["id"] for t in tasks}) == len(tasks), "duplicate task ids"

    new = {k: v for k, v in doc.items() if not k.startswith("_")}
    new["name"] = doc["name"].replace(" chained", "") + " unrolled"
    new["max_concurrency"] = 64  # about 263 tasks: the outer pool must not be the limit
    new["tasks"] = tasks
    new["edges"] = derive_edges(new)
    return new


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "workflow.chained.yaml"
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "workflow.unrolled.yaml"
    doc = yaml.safe_load(src.read_text())
    assert edge_set(derive_edges(doc)) == edge_set(doc["edges"]), f"{src.name} edges differ from its input ids"
    sheet = next(a for a in doc["artifacts"] if a["id"] == "samplesheet")["path"]
    with (src.parent / sheet).open() as f:
        samples = sorted({r["sample"] for r in csv.DictReader(f)})
    new = unroll(doc, samples)
    head = (f"# Generated by scripts/gen_unrolled.py from {src.name}; do not edit by hand.\n"
            f"# Every map unrolled into one task per slot for the {len(samples)} samples of {sheet}"
            f" ({', '.join(samples)}): {len(new['tasks'])} tasks, no maps.\n")
    dst.write_text(head + yaml.dump(new, Dumper=Dumper, sort_keys=False, width=4096, allow_unicode=True))
    print(f"wrote {dst}: {len(new['tasks'])} tasks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
