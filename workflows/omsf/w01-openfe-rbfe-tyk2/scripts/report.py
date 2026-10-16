#!/usr/bin/env python3
# Turns the `openfe gather` tables and the ligand network into one
# self-contained report.html (renders live in the Horus UI iframe: one file,
# only absolute CDN refs, here Mol*). Stdlib only.

import argparse
import csv
import html
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

GRAPHML = "{http://graphml.graphdrawing.org/xmlns}"
MOLSTAR = "https://cdn.jsdelivr.net/npm/molstar@5/build/viewer"

CSS = """
body{font:14px system-ui,sans-serif;margin:0;padding:24px;color:#111827;background:#fff}
h1{font-size:20px;margin:0 0 16px}
h2{font-size:15px;margin:24px 0 8px}
p.note{color:#6b7280;font-size:12px;max-width:760px}
table{border-collapse:collapse}
th,td{border:1px solid #e5e7eb;padding:4px 10px;text-align:left}
th{background:#f9fafb}
#mol{position:relative;height:460px;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden}
#status{min-height:18px;margin-top:4px;font-size:12px;color:#b91c1c}
"""

# Protein as cartoon plus each ligand as its own structure (Mol* reads only
# the first record of a multi-record SDF).
VIEWER_JS = """
const D = JSON.parse(document.getElementById('data').textContent);
const status = document.getElementById('status');
if (typeof molstar === 'undefined') {
  status.textContent = 'Mol* could not be loaded (needs access to cdn.jsdelivr.net).';
} else {
  molstar.Viewer.create('mol', {layoutIsExpanded: false, layoutShowControls: false,
    layoutShowRemoteState: false, layoutShowSequence: false, layoutShowLog: false,
    viewportShowExpand: false})
    .then(async v => {
      await v.loadStructureFromData(D.protein, 'pdb', {dataLabel: 'TYK2'});
      for (const l of D.ligands) await v.loadStructureFromData(l.sdf, 'sdf', {dataLabel: l.name});
    })
    .catch(e => { status.textContent = 'Mol* failed to start: ' + e; });
}
"""


def read_tsv(path: Path) -> list[list[str]]:
    with path.open(newline="") as f:
        return [r for r in csv.reader(f, delimiter="\t") if r]


def edges(graphml: str) -> list[tuple[str, str, int]]:
    """(ligand A, ligand B, mapped atoms) per network edge."""
    root = ET.fromstring(graphml)
    keys = {k.get("id"): k.get("attr.name") for k in root.iter(f"{GRAPHML}key")}
    names = {}
    for node in root.iter(f"{GRAPHML}node"):
        for d in node.iter(f"{GRAPHML}data"):
            if keys[d.get("key")] == "moldict":
                names[node.get("id")] = json.loads(d.text)["molprops"]["ofe-name"]
    out = []
    for e in root.iter(f"{GRAPHML}edge"):
        mapping = next(
            (json.loads(d.text) for d in e.iter(f"{GRAPHML}data") if keys[d.get("key")] == "mapping"),
            [],
        )
        out.append((names[e.get("source")], names[e.get("target")], len(mapping)))
    return out


def records(text: str) -> list[str]:
    """Split an SDF into records, each ending with its '$$$$' line.

    A last record without '$$$$' is kept and terminated.
    """
    out, buf = [], []
    for line in text.splitlines(keepends=True):
        buf.append(line)
        if line.strip() == "$$$$":
            out.append("".join(buf))
            buf = []
    tail = "".join(buf)
    if tail.strip():
        out.append(tail + ("" if tail.endswith("\n") else "\n") + "$$$$\n")
    return out


def sdf_records(text: str) -> list[dict]:
    return [{"name": r.splitlines()[0].strip(), "sdf": r} for r in records(text)]


def table(rows: list[list[str]]) -> str:
    if not rows:
        return "<p>No rows.</p>"
    head = "".join(f"<th>{html.escape(c)}</th>" for c in rows[0])
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in r) + "</tr>" for r in rows[1:]
    )
    return f"<table><tr>{head}</tr>{body}</table>"


def render(ddg, dg, raw, net, protein: str, ligands: list[dict]) -> str:
    edge_rows = [["ligand A", "ligand B", "mapped atoms"]] + [[a, b, str(n)] for a, b, n in net]
    # '</' would end the <script> early; JSON allows the escaped form.
    data = json.dumps({"protein": protein, "ligands": ligands}).replace("</", "<\\/")
    return (
        "<!doctype html><html><head><meta charset=utf-8>"
        f"<title>OpenFE RBFE report</title><style>{CSS}</style>"
        f"<link rel=stylesheet href={MOLSTAR}/molstar.css></head><body>"
        "<h1>OpenFE relative binding free energies: TYK2</h1>"
        "<p class=note>dG values are MLE estimates centred on 0.</p>"
        f"<h2>ddG per edge (kcal/mol)</h2>{table(ddg)}"
        f"<h2>dG per ligand (kcal/mol)</h2>{table(dg)}"
        f"<h2>dG per leg and repeat (kcal/mol)</h2>{table(raw)}"
        f"<h2>Ligand network ({len(net)} edges)</h2>{table(edge_rows)}"
        "<h2>Structure</h2><div id=mol></div><div id=status></div>"
        f"<script id=data type=application/json>{data}</script>"
        f"<script src={MOLSTAR}/molstar.js></script>"
        f"<script>{VIEWER_JS}</script></body></html>"
    )


def selftest() -> None:
    g = (
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">'
        '<key id="d1" for="edge" attr.name="mapping"/><key id="d0" for="node" attr.name="moldict"/>'
        "<graph>"
        '<node id="mol0"><data key="d0">{"molprops": {"ofe-name": "a"}}</data></node>'
        '<node id="mol1"><data key="d0">{"molprops": {"ofe-name": "b"}}</data></node>'
        '<edge source="mol0" target="mol1"><data key="d1">[[0, 0], [1, 2]]</data></edge>'
        "</graph></graphml>"
    )
    assert edges(g) == [("a", "b", 2)]
    recs = sdf_records("a\n x\nM  END\n$$$$\nb\n y\nM  END\n$$$$\n")
    assert [r["name"] for r in recs] == ["a", "b"] and recs[1]["sdf"].endswith("$$$$\n")
    # An empty title line must survive, or the molfile header shifts up.
    recs = sdf_records("a\nM  END\n$$$$\n\n  RDKit  3D\nM  END\n$$$$\n")
    assert recs[1] == {"name": "", "sdf": "\n  RDKit  3D\nM  END\n$$$$\n"}
    page = render([["ligand_i", "ligand_j"], ["a", "b<"]], [["ligand"], ["a"]],
                  [["leg"], ["complex"]], edges(g), "ATOM</script>", recs)
    assert "b&lt;" in page and "ATOM<\\/script>" in page and "<td>complex</td>" in page
    print("selftest ok")


def main() -> None:
    if "--selftest" in sys.argv:
        return selftest()
    ap = argparse.ArgumentParser()
    ap.add_argument("--ddg", type=Path, required=True)
    ap.add_argument("--dg", type=Path, required=True)
    ap.add_argument("--raw", type=Path, required=True)
    ap.add_argument("--network", type=Path, required=True)
    ap.add_argument("--protein", type=Path, required=True)
    ap.add_argument("--ligands", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(render(
        read_tsv(a.ddg), read_tsv(a.dg), read_tsv(a.raw), edges(a.network.read_text()),
        a.protein.read_text(), sdf_records(a.ligands.read_text()),
    ))


if __name__ == "__main__":
    main()
