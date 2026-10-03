#!/usr/bin/env python3
# Turns Lacuna's pocket_report.json into a self-contained report.html (renders
# live in the Horus UI iframe: one file, only absolute CDN refs, here Mol*) and a
# flat pockets.csv (renders as a table). Stdlib only.

import argparse
import csv
import html
import json
import re
from pathlib import Path

COLUMNS = [
    "rank", "x", "y", "z", "volume_A3", "volume_min_A3", "volume_max_A3",
    "apo_volume_A3", "druggability", "max_druggability", "persistence",
    "cryptic", "crypticity", "appears_in_conformers", "lining_residues",
]

CSS = """
body{font:14px system-ui,sans-serif;margin:0;padding:24px;color:#111827;background:#fff}
h1{font-size:20px;margin:0 0 16px}
h2{font-size:15px;margin:24px 0 8px}
.stats{display:flex;gap:12px}
.stat{border:1px solid #e5e7eb;border-radius:8px;padding:10px 16px;min-width:110px}
.stat b{display:block;font-size:22px}
.stat span{color:#6b7280;font-size:12px}
#mol{position:relative;height:460px;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden}
#status{min-height:18px;margin-top:4px;font-size:12px;color:#b91c1c}
.bar{background:#e5e7eb;border-radius:3px;width:48px;height:8px;display:inline-block;margin-right:6px}
.bar i{display:block;height:8px;border-radius:3px;background:#3b82f6}
.view{font:inherit;font-size:12px;background:#3b82f6;color:#fff;border:0;border-radius:6px;padding:0 12px;height:26px;line-height:24px;cursor:pointer}
.view:hover{background:#2563eb}
"""

AGGRID = "https://cdn.jsdelivr.net/npm/ag-grid-community@33/dist/ag-grid-community.min.js"
MOLSTAR = "https://cdn.jsdelivr.net/npm/molstar@5/build/viewer"

# Loads the receptor once; a row's View button selects that pocket's lining
# residues and flies the camera to them (a pocket is a handful of pseudoatoms in
# a whole protein, so swapping a marker structure changes the picture too little
# to notice). Row clicks are bound first and independent of Mol*, so they always
# respond and any failure is shown under the viewer.
VIEWER_JS = """
const D = JSON.parse(document.getElementById('data').textContent);
const status = document.getElementById('status');
let viewer;
async function show(i) {
  if (!viewer) { status.textContent = 'Viewer is still loading…'; return; }
  try {
    status.textContent = '';
    viewer.structureInteractivity({
      action: ['select', 'focus'], applyGranularity: true,
      elements: {items: D.rows[i].sel}, focusOptions: {extraRadius: 6, durationMs: 400},
    });
  } catch (e) { status.textContent = 'Could not show pocket: ' + e; }
}
const bar = p => `<span class="bar"><i style="width:${Math.max(0, Math.min(1, p.value)) * 100}%"></i></span>${p.value.toFixed(2)}`;
const num = {filter: 'agNumberColumnFilter', cellRenderer: bar, minWidth: 140};
if (typeof agGrid === 'undefined') {
  document.getElementById('grid').textContent = 'Table could not be loaded (needs access to cdn.jsdelivr.net).';
} else {
  agGrid.createGrid(document.getElementById('grid'), {
    theme: agGrid.themeQuartz, domLayout: 'autoHeight', autoSizeStrategy: {type: 'fitGridWidth'}, rowData: D.rows,
    defaultColDef: {sortable: true, resizable: true, filter: true},
    columnDefs: [
      {colId: 'view', headerName: '', width: 80, minWidth: 80, maxWidth: 80, cellStyle: {display: 'flex', alignItems: 'center'}, sortable: false, filter: false, resizable: false, pinned: 'left',
       cellRenderer: p => { const b = document.createElement('button'); b.className = 'view'; b.textContent = 'View'; b.onclick = e => { e.stopPropagation(); show(p.data.i); }; return b; }},
      {field: 'rank', headerName: 'Rank', filter: 'agNumberColumnFilter', minWidth: 105, sort: 'asc'},
      {field: 'druggability', headerName: 'Druggability', ...num},
      {field: 'persistence', headerName: 'Persistence', ...num},
      {field: 'crypticity', headerName: 'Crypticity', ...num},
      {field: 'cryptic', headerName: 'Cryptic', minWidth: 100, valueFormatter: p => p.value ? 'yes' : 'no'},
      {field: 'apo_volume', headerName: 'Apo (\\u00c5\\u00b3)', filter: 'agNumberColumnFilter', minWidth: 115, valueFormatter: p => p.value.toFixed(0)},
      {field: 'max_volume', headerName: 'Max (\\u00c5\\u00b3)', filter: 'agNumberColumnFilter', minWidth: 115, valueFormatter: p => p.value.toFixed(0)},
      {field: 'residues', headerName: 'Residues', minWidth: 160, tooltipField: 'residues'},
    ],
    rowSelection: {mode: 'singleRow', checkboxes: false, enableClickSelection: true},
  });
}
if (typeof molstar === 'undefined') {
  status.textContent = 'Mol* could not be loaded (needs access to cdn.jsdelivr.net).';
} else {
  molstar.Viewer.create('mol', {layoutIsExpanded: false, layoutShowControls: false,
    layoutShowRemoteState: false, layoutShowSequence: false, layoutShowLog: false,
    viewportShowExpand: false})
    .then(async v => { await v.loadStructureFromData(D.receptor, 'pdb', {dataLabel: 'Receptor'}); viewer = v; })
    .catch(e => { status.textContent = 'Mol* failed to start: ' + e; });
}
"""


def row(p: dict) -> dict:
    x, y, z = p["centroid"]
    lo, hi = p["volume_range_A3"]
    return {
        "rank": p["rank"], "x": x, "y": y, "z": z, "volume_A3": p["volume_A3"],
        "volume_min_A3": lo, "volume_max_A3": hi, "apo_volume_A3": p["apo_volume_A3"],
        "druggability": p["druggability"], "max_druggability": p["max_druggability"],
        "persistence": p["persistence"], "cryptic": p["cryptic"],
        "crypticity": p["crypticity"],
        "appears_in_conformers": p["appears_in_conformers"],
        "lining_residues": ";".join(p["lining_residues"]),
    }


def lining(residues: list[str]) -> list[dict]:
    # 'ALA11:A' (resname, number, chain) -> a Mol* structure-element selector
    out = []
    for r in residues:
        m = re.fullmatch(r"[A-Za-z0-9]+?(-?\d+):(\S+)", r)
        if m:
            out.append({"auth_seq_id": int(m[1]), "auth_asym_id": m[2]})
    return out


def render(report: dict, receptor: str) -> str:
    rows = [
        {
            "i": i, "rank": p["rank"], "druggability": p["druggability"],
            "persistence": p["persistence"], "crypticity": p["crypticity"],
            "cryptic": p["cryptic"], "apo_volume": p["apo_volume_A3"],
            "max_volume": p["volume_range_A3"][1],
            "residues": ", ".join(p["lining_residues"]),
            "sel": lining(p["lining_residues"]),
        }
        for i, p in enumerate(report["pockets"])
    ]
    stats = [
        ("Conformers", report["n_conformers"]),
        ("Pockets found", report["n_pockets_found"]),
        ("Cryptic pockets", report["n_cryptic_pockets"]),
    ]
    # '</' would end the <script> early; JSON allows the escaped form.
    data = json.dumps({"receptor": receptor, "rows": rows}).replace("</", "<\\/")
    cards = "".join(f"<div class=stat><b>{v}</b><span>{k}</span></div>" for k, v in stats)
    return (
        "<!doctype html><html><head><meta charset=utf-8>"
        f"<title>Lacuna report</title><style>{CSS}</style>"
        f"<link rel=stylesheet href={MOLSTAR}/molstar.css></head><body>"
        "<h1>Cryptic pocket report</h1>"
        f"<div class=stats>{cards}</div>"
        "<h2>Structure</h2><div id=mol></div><div id=status></div>"
        "<h2>Pockets</h2><div id=grid></div>"
        f"<script id=data type=application/json>{data}</script>"
        f"<script src={MOLSTAR}/molstar.js></script><script src={AGGRID}></script>"
        f"<script>{VIEWER_JS}</script></body></html>"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pockets", type=Path, required=True)
    ap.add_argument("--receptor", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--table", type=Path, required=True)
    a = ap.parse_args()

    report = json.loads((a.pockets / "pocket_report.json").read_text())
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(render(report, a.receptor.read_text()))
    with a.table.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(row(p) for p in report["pockets"])


if __name__ == "__main__":
    main()
