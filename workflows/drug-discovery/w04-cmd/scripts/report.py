#!/usr/bin/env python3
"""
Combines every replica's analysis (scripts/analyze.py output) into:
  report.html  self-contained page (renders in the Horus UI iframe; only
               absolute CDN refs, here Mol*): system summary, per-replica
               RMSD/RMSF/Rg/H-bond/ligand plots, energies, clusters with
               representative structures, top H-bonds and ligand contacts
  summary.csv  one row per replica
  clusters/    cpptraj k-means over all replicas' dry trajectories
               (representative PDBs, per-frame assignment)
Clustering needs cpptraj (the tools conda environment); everything else is stdlib.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import shutil
import subprocess
from pathlib import Path

COLORS = ["#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c", "#0891b2", "#ca8a04", "#db2777"]
MOLSTAR = "https://cdn.jsdelivr.net/npm/molstar@5/build/viewer"
CSS = """
body{font:14px system-ui,sans-serif;margin:0;padding:24px;color:#111827;background:#fff;max-width:1200px}
h1{font-size:20px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 8px}h3{font-size:13px;margin:12px 0 4px;color:#374151}
.sub{color:#6b7280;margin-bottom:16px}
.stats{display:flex;flex-wrap:wrap;gap:12px}
.stat{border:1px solid #e5e7eb;border-radius:8px;padding:10px 16px;min-width:110px}
.stat b{display:block;font-size:20px}.stat span{color:#6b7280;font-size:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:16px}
.card{border:1px solid #e5e7eb;border-radius:8px;padding:8px 12px}
table{border-collapse:collapse;font-size:13px}td,th{border-bottom:1px solid #e5e7eb;padding:4px 10px;text-align:left}
th{color:#6b7280;font-weight:600}
.warn{background:#fffbeb;border:1px solid #fcd34d;border-radius:8px;padding:8px 12px;margin:8px 0}
#mol{position:relative;height:440px;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden}
#status{min-height:18px;font-size:12px;color:#b91c1c}
.reps button{font:inherit;font-size:12px;margin:0 6px 6px 0;background:#e5e7eb;border:0;border-radius:6px;padding:4px 10px;cursor:pointer}
.reps button.on{background:#2563eb;color:#fff}
svg text{font:11px system-ui,sans-serif;fill:#374151}
"""
VIEWER_JS = """
const D = JSON.parse(document.getElementById('data').textContent);
const status = document.getElementById('status');
let viewer;
async function show(i) {
  document.querySelectorAll('.reps button').forEach((b, j) => b.classList.toggle('on', i === j));
  if (!viewer) { status.textContent = 'Viewer is still loading...'; return; }
  try { await viewer.plugin.clear(); await viewer.loadStructureFromData(D.reps[i].pdb, 'pdb', {dataLabel: D.reps[i].label}); status.textContent = ''; }
  catch (e) { status.textContent = 'Could not load structure: ' + e; }
}
if (D.reps.length) {
  if (typeof molstar === 'undefined') { status.textContent = 'Mol* could not be loaded (needs access to cdn.jsdelivr.net).'; }
  else {
    molstar.Viewer.create('mol', {layoutIsExpanded: false, layoutShowControls: false, layoutShowRemoteState: false,
      layoutShowSequence: false, layoutShowLog: false, viewportShowExpand: false})
      .then(v => { viewer = v; show(0); }).catch(e => { status.textContent = 'Mol* failed to start: ' + e; });
  }
}
"""


# --- data readers --------------------------------------------------------------

def read_dat(path: Path) -> list[list[float]]:
    """Numeric rows of a cpptraj .dat file ('#' header skipped)."""
    rows = []
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                try:
                    rows.append([float(x) for x in line.split()])
                except ValueError:
                    continue
    return rows


def read_table(path: Path) -> list[list[str]]:
    """Whitespace-split rows of a cpptraj text table ('#' header skipped)."""
    if not path.exists():
        return []
    return [line.split() for line in path.read_text().splitlines() if line.strip() and not line.startswith("#")]


ENERGY_RE = {
    "time_ps": re.compile(r"TIME\(PS\)\s*=\s*(-?[\d.]+)"),
    "temp_K": re.compile(r"TEMP\(K\)\s*=\s*(-?[\d.]+)"),
    "eptot": re.compile(r"EPtot\s*=\s*(-?[\d.]+)"),
    "density": re.compile(r"Density\s*=\s*(-?[\d.]+)"),
}


def mdout_energies(text: str) -> list[dict]:
    """Per-print MD records of an mdout, stopping at the AVERAGES block."""
    text = text.split("A V E R A G E S")[0]
    records = []
    for block in text.split(" NSTEP =")[1:]:
        rec = {}
        for key, rx in ENERGY_RE.items():
            m = rx.search(block)
            if m:
                rec[key] = float(m.group(1))
        if "time_ps" in rec:
            records.append(rec)
    return records


def residue_labels(prmtop_text: str) -> list[str]:
    """Residue names from a prmtop's %FLAG RESIDUE_LABEL (20a4)."""
    labels, inside = [], False
    for line in prmtop_text.splitlines():
        if line.startswith("%FLAG"):
            inside = line.split()[1] == "RESIDUE_LABEL"
        elif inside and not line.startswith("%"):
            labels += [line[i:i + 4].strip() for i in range(0, len(line), 4)]
    return [x for x in labels if x]


def load_replica(d: Path) -> dict:
    d = d.resolve()  # cpptraj runs from the clusters folder
    info = json.loads((d / "info.json").read_text())
    dt_ns = info["frame_ps"] / 1000
    series = lambda name, col=1: [(r[0] * dt_ns, r[col]) for r in read_dat(d / name)]
    energies = []
    for f in sorted((d / "mdout").glob("prod_*.mdout"), key=lambda p: int(re.findall(r"\d+", p.stem)[-1])):
        energies += mdout_energies(f.read_text(errors="replace"))
    return {
        "dir": d, "info": info, "name": f"replica {info['replica']}",
        "rmsd_first": series("rmsd_first.dat"), "rmsd_start": series("rmsd_start.dat"),
        "rg": series("rg.dat"), "hbonds": series("hbond_count.dat"),
        "lig_rmsd": series("lig_rmsd.dat"), "lig_contacts": series("lig_contacts.dat"),
        "rmsf": [(r[0], r[1]) for r in read_dat(d / "rmsf.dat")],
        "hbond_avg": read_table(d / "hbond_avg.dat"),
        "lig_res": read_table(d / "lig_contact_res.dat"),
        "energies": energies,
    }


# --- clustering ----------------------------------------------------------------

def cluster(replicas: list[dict], k: int, out: Path) -> dict | None:
    """cpptraj k-means on all dry trajectories; None when unavailable."""
    frames = [r["info"]["frames"] for r in replicas]
    if not shutil.which("cpptraj") or sum(frames) < max(k, 2) * 2:
        return None
    out.mkdir(parents=True, exist_ok=True)
    last = replicas[0]["info"]["last_solute_residue"]
    mask = f"(:1-{last})&@CA,C,N"
    lines = [f"parm {replicas[0]['dir'] / 'dry.prmtop'}"]
    lines += [f"trajin {r['dir'] / 'dry.nc'}" for r in replicas]
    lines += [f"rms first {mask}",
              f"cluster C kmeans clusters {k} rms {mask} out cnumvtime.dat summary summary.dat "
              f"repout rep repfmt pdb", "run", "quit", ""]
    (out / "cluster.in").write_text("\n".join(lines))
    proc = subprocess.run(["cpptraj", "-i", "cluster.in"], cwd=out, capture_output=True, text=True)
    (out / "cluster.log").write_text(proc.stdout + proc.stderr)
    if proc.returncode != 0:
        print("clustering failed; see clusters/cluster.log")
        return None
    assign = [int(r[1]) for r in read_dat(out / "cnumvtime.dat")]
    per_replica, start = [], 0
    for n in frames:
        per_replica.append(assign[start:start + n])
        start += n
    summary = [r for r in read_dat(out / "summary.dat")]
    clusters = []
    for row in summary:
        cid = int(row[0])
        rep = next(iter(sorted(out.glob(f"rep.c{cid}.*"))), None)
        clusters.append({
            "id": cid, "frames": int(row[1]), "fraction": row[2],
            "by_replica": [sum(1 for a in pr if a == cid) / len(pr) if pr else 0 for pr in per_replica],
            "pdb": rep.read_text() if rep else "",
        })
    return {"k": k, "clusters": clusters}


# --- rendering -------------------------------------------------------------------

def line_chart(series: list[tuple[str, list[tuple[float, float]]]], xlabel: str, ylabel: str,
               w: int = 520, h: int = 220) -> str:
    """Inline SVG line chart, one polyline per (label, points) series."""
    series = [(label, pts) for label, pts in series if pts]
    if not series:
        return "<p class=sub>No data.</p>"
    xs = [x for _, pts in series for x, _ in pts]
    ys = [y for _, pts in series for _, y in pts]
    x0, x1 = min(xs), max(xs) or 1
    y0, y1 = min(ys), max(ys)
    if x1 == x0:
        x1 = x0 + 1
    if y1 == y0:
        y0, y1 = y0 - 1, y1 + 1
    L, R, T, B = 56, 12, 10, 34
    px = lambda x: L + (x - x0) / (x1 - x0) * (w - L - R)
    py = lambda y: T + (1 - (y - y0) / (y1 - y0)) * (h - T - B)
    parts = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="{html.escape(ylabel)}">',
             f'<line x1="{L}" y1="{h - B}" x2="{w - R}" y2="{h - B}" stroke="#9ca3af"/>',
             f'<line x1="{L}" y1="{T}" x2="{L}" y2="{h - B}" stroke="#9ca3af"/>']
    for i in range(5):
        yv = y0 + (y1 - y0) * i / 4
        xv = x0 + (x1 - x0) * i / 4
        parts.append(f'<text x="{L - 6}" y="{py(yv) + 4:.1f}" text-anchor="end">{yv:.3g}</text>')
        parts.append(f'<text x="{px(xv):.1f}" y="{h - B + 14}" text-anchor="middle">{xv:.3g}</text>')
    parts.append(f'<text x="{(L + w - R) / 2}" y="{h - 4}" text-anchor="middle">{html.escape(xlabel)}</text>')
    parts.append(f'<text transform="translate(12 {(T + h - B) / 2}) rotate(-90)" text-anchor="middle">{html.escape(ylabel)}</text>')
    step = lambda pts: pts[:: max(1, len(pts) // 1500)]
    for i, (label, pts) in enumerate(series):
        c = COLORS[i % len(COLORS)]
        coords = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y in step(pts))
        parts.append(f'<polyline fill="none" stroke="{c}" stroke-width="1.3" points="{coords}"/>')
        parts.append(f'<text x="{w - R - 4}" y="{T + 12 + 13 * i}" text-anchor="end" fill="{c}">{html.escape(label)}</text>')
    return "".join(parts) + "</svg>"


def table(header: list[str], rows: list[list]) -> str:
    head = "".join(f"<th>{html.escape(str(h))}</th>" for h in header)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(fmt(c))}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def fmt(v) -> str:
    return f"{v:.3g}" if isinstance(v, float) else str(v)


def mean(pts: list[tuple[float, float]]) -> float | None:
    return sum(y for _, y in pts) / len(pts) if pts else None


def summary_rows(replicas: list[dict]) -> list[dict]:
    rows = []
    for r in replicas:
        i = r["info"]
        rows.append({
            "replica": i["replica"], "chunks_completed": i["chunks_completed"],
            "chunks_planned": i["chunks_planned"], "simulated_ns": i["simulated_ns"],
            "frames_analyzed": i["frames"], "trajectory_bytes": i["trajectory_bytes"],
            "rmsd_backbone_mean_A": mean(r["rmsd_first"]),
            "rmsd_backbone_final_A": r["rmsd_first"][-1][1] if r["rmsd_first"] else None,
            "rmsd_vs_start_mean_A": mean(r["rmsd_start"]), "rg_mean_A": mean(r["rg"]),
            "hbonds_mean": mean(r["hbonds"]), "ligand_rmsd_mean_A": mean(r["lig_rmsd"]),
        })
    return rows


def top_hbonds(replicas: list[dict], n: int = 15) -> list[list]:
    """H-bonds by mean occupancy across replicas (hbond avgout: Acceptor DonorH Donor Frames Frac ...)."""
    occ: dict[tuple, list[float]] = {}
    for r in replicas:
        for row in r["hbond_avg"]:
            if len(row) >= 5:
                occ.setdefault((row[0], row[2]), []).append(float(row[4]))
    ranked = sorted(occ.items(), key=lambda kv: -sum(kv[1]) / len(replicas))[:n]
    return [[d, a, sum(v) / len(replicas)] for (a, d), v in ranked]


def top_contacts(replicas: list[dict], n: int = 15) -> list[list]:
    """Ligand-protein residue pairs by contact score (nativecontacts resout
    TotalFrac: atom-pair contact fractions summed per residue pair), averaged
    over replicas, with residue names from the dry topology."""
    prmtop = replicas[0]["dir"] / "dry.prmtop"
    labels = residue_labels(prmtop.read_text()) if prmtop.exists() else []
    name = lambda r: f"{labels[int(r) - 1]}{r}" if r.isdigit() and 0 < int(r) <= len(labels) else r
    occ: dict[tuple, float] = {}
    for r in replicas:
        for row in r["lig_res"]:
            if len(row) >= 3:
                try:
                    occ[(row[0], row[1])] = occ.get((row[0], row[1]), 0) + float(row[2]) / len(replicas)
                except ValueError:
                    continue
    return [[name(a), name(b), f] for (a, b), f in sorted(occ.items(), key=lambda kv: -kv[1])[:n]]


def render(replicas: list[dict], clusters: dict | None) -> str:
    proto = replicas[0]["info"]["protocol"]
    system = replicas[0]["info"].get("system", {})
    ligands = replicas[0]["info"].get("ligands", [])
    names = [r["name"] for r in replicas]
    stat = lambda k, v: f"<div class=stat><b>{html.escape(fmt(v))}</b><span>{html.escape(k)}</span></div>"
    cards = "".join([
        stat("Replicas", len(replicas)),
        stat("Total simulated (ns)", sum(r["info"]["simulated_ns"] for r in replicas)),
        stat("Atoms", system.get("atoms", "?")),
        stat("Temperature (K)", proto["temperature"]),
        stat("Timestep (fs)", proto["timestep_fs"]),
        stat("Ensemble", proto["prod_ensemble"]),
    ])
    warn = ""
    incomplete = [r["name"] for r in replicas if r["info"]["chunks_completed"] < r["info"]["chunks_planned"]]
    if incomplete:
        warn += f"<div class=warn>Incomplete production: {html.escape(', '.join(incomplete))}</div>"
    system_rows = [[k, json.dumps(v) if isinstance(v, (dict, list)) else v] for k, v in system.items()]
    system_rows.append(["ligands", ", ".join(ligands) or "none"])
    proto_rows = [[k, v] for k, v in proto.items() if k not in ("replica",)]

    s = lambda key: [(n, r[key]) for n, r in zip(names, replicas)]
    plots = [
        ("Backbone RMSD vs first frame", line_chart(s("rmsd_first"), "time (ns)", "RMSD (Å)")),
        ("Backbone RMSD vs built structure", line_chart(s("rmsd_start"), "time (ns)", "RMSD (Å)")),
        ("Radius of gyration", line_chart(s("rg"), "time (ns)", "Rg (Å)")),
        ("CA RMSF", line_chart(s("rmsf"), "residue", "RMSF (Å)")),
        ("Solute H-bonds", line_chart(s("hbonds"), "time (ns)", "count")),
    ]
    if any(r["lig_rmsd"] for r in replicas):
        plots += [("Ligand RMSD (protein frame)", line_chart(s("lig_rmsd"), "time (ns)", "RMSD (Å)")),
                  ("Ligand-protein native contacts", line_chart(s("lig_contacts"), "time (ns)", "contacts"))]
    energy = lambda key: [(n, [(e["time_ps"] / 1000, e[key]) for e in r["energies"] if key in e]) for n, r in zip(names, replicas)]
    plots += [("Potential energy", line_chart(energy("eptot"), "time (ns)", "EPtot (kcal/mol)")),
              ("Temperature", line_chart(energy("temp_K"), "time (ns)", "T (K)"))]
    if proto["prod_ensemble"] == "NPT":
        plots.append(("Density", line_chart(energy("density"), "time (ns)", "g/cm³")))
    plot_html = "".join(f"<div class=card><h3>{html.escape(t)}</h3>{svg}</div>" for t, svg in plots)

    rows = summary_rows(replicas)
    summary = table(list(rows[0]), [[v if v is not None else "" for v in r.values()] for r in rows])

    reps, cl_html = [], "<p class=sub>Clustering skipped (needs cpptraj and enough frames).</p>"
    if clusters:
        cl_rows = [[c["id"], c["frames"], c["fraction"], *c["by_replica"]] for c in clusters["clusters"]]
        cl_html = table(["cluster", "frames", "fraction", *[f"frac {n}" for n in names]], cl_rows)
        reps = [{"label": f"cluster {c['id']} ({c['fraction']:.0%})", "pdb": c["pdb"]}
                for c in clusters["clusters"] if c["pdb"]]
        buttons = "".join(f"<button onclick='show({i})'>{html.escape(r['label'])}</button>" for i, r in enumerate(reps))
        cl_html += f"<h3>Representative structures</h3><div class=reps>{buttons}</div><div id=mol></div><div id=status></div>"

    hb = top_hbonds(replicas)
    hb_html = table(["donor", "acceptor", "mean occupancy"], hb) if hb else "<p class=sub>None.</p>"
    ct = top_contacts(replicas)
    ct_html = f"<h2>Ligand contacts</h2>{table(['ligand', 'protein residue', 'contact score'], ct)}<p class=sub>Contact score: atom-pair contact fractions (4.5 Å) summed per residue pair, mean over replicas.</p>" if ct else ""

    data = json.dumps({"reps": reps}).replace("</", "<\\/")
    title = "cMD report" + (f": {', '.join(ligands)} complex" if ligands else "")
    return (
        "<!doctype html><html><head><meta charset=utf-8>"
        f"<title>{html.escape(title)}</title><style>{CSS}</style>"
        f"<link rel=stylesheet href={MOLSTAR}/molstar.css></head><body>"
        f"<h1>{html.escape(title)}</h1><div class=sub>{len(replicas)} replica(s), "
        f"{html.escape(str(system.get('atoms', '?')))} atoms, {proto['temperature']} K</div>"
        f"<div class=stats>{cards}</div>{warn}"
        f"<h2>Replicas</h2>{summary}"
        f"<h2>Trajectory analysis</h2><div class=grid>{plot_html}</div>"
        f"<h2>Clusters (k-means, backbone)</h2>{cl_html}"
        f"<h2>Top hydrogen bonds</h2>{hb_html}{ct_html}"
        f"<h2>System</h2>{table(['property', 'value'], system_rows)}"
        f"<h2>MD protocol</h2>{table(['setting', 'value'], proto_rows)}"
        f"<script id=data type=application/json>{data}</script>"
        f"<script src={MOLSTAR}/molstar.js></script><script>{VIEWER_JS}</script></body></html>"
    )


def whole(text: str) -> int:
    """argparse type: UI number inputs may arrive as '3.0'."""
    return int(float(text))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--analyses", type=Path, required=True, help="folder of per-replica analyze.py outputs")
    ap.add_argument("--n-clusters", type=whole, default=5)
    ap.add_argument("--out", type=Path, required=True, help="output folder")
    a = ap.parse_args()

    dirs = sorted((d for d in a.analyses.iterdir() if (d / "info.json").exists()), key=lambda d: d.name)
    if not dirs:
        raise SystemExit(f"No replica analyses (info.json) under {a.analyses}.")
    replicas = [load_replica(d) for d in dirs]
    (a.out / "clusters").mkdir(parents=True, exist_ok=True)  # declared output, even when skipped
    clusters = cluster(replicas, a.n_clusters, a.out / "clusters") if a.n_clusters > 0 else None
    (a.out / "report.html").write_text(render(replicas, clusters))
    rows = summary_rows(replicas)
    with (a.out / "summary.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {a.out / 'report.html'} and summary.csv for {len(replicas)} replica(s)")


def demo() -> None:
    """Self-check: synthetic analyses -> report.html + summary.csv (no cpptraj)."""
    import math
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for rep in (0, 1):
            d = tmp / "an" / str(rep)
            (d / "mdout").mkdir(parents=True)
            proto = {"temperature": 300.0, "timestep_fs": 2.0, "prod_ensemble": "NVT", "chunks": 2,
                     "chunk_ns": 10.0, "save_every_ps": 10.0, "replica": rep}
            (d / "info.json").write_text(json.dumps({
                "replica": rep, "chunks_planned": 2, "chunks_completed": 2 - rep, "simulated_ns": 20.0 - 10 * rep,
                "frames": 50, "frame_ps": 10.0, "trajectory_bytes": 1000, "last_solute_residue": 130,
                "ligands": ["JZ4130"], "protocol": proto,
                "system": {"atoms": 38218, "residues": 9000, "solute_residues": 130, "waters": 8800,
                           "ions": {"Na+": 21, "Cl-": 28}}}))
            dat = lambda name, f: (d / name).write_text("#Frame X\n" + "".join(f"{i:8d} {f(i):10.4f}\n" for i in range(1, 51)))
            dat("rmsd_first.dat", lambda i: 1 + math.sin(i / 5) + rep)
            dat("rmsd_start.dat", lambda i: 2 + i / 50)
            dat("rg.dat", lambda i: 14 + 0.1 * math.cos(i))
            dat("hbond_count.dat", lambda i: 90 + i % 7)
            dat("lig_rmsd.dat", lambda i: 0.5 + i / 100)
            dat("lig_contacts.dat", lambda i: 30 - i % 4)
            dat("rmsf.dat", lambda i: 0.5 + (i % 9) / 10)
            (d / "hbond_avg.dat").write_text("#Acceptor DonorH Donor Frames Frac AvgDist AvgAng\n"
                                             "ASP52@OD1 ASN46@HD21 ASN46@ND2 40 0.8000 2.9 160\n"
                                             "GLU35@OE1 TRP108@HE1 TRP108@NE1 10 0.2000 2.9 155\n")
            (d / "dry.prmtop").write_text("%FLAG RESIDUE_LABEL\n%FORMAT(20a4)\n" + "LEU " * 129 + "JZ4 \n%FLAG X\n")
            (d / "lig_contact_res.dat").write_text("#Res1 #Res2 TotalFrac Contacts\n130 84 0.95 3\n")
            (d / "mdout" / "prod_1.mdout").write_text(
                "".join(f" NSTEP = {s}   TIME(PS) = {s / 500:.3f}  TEMP(K) = 300.{s % 9}  PRESS = 0.0\n"
                        f" Etot = -1  EKtot = 1  EPtot = {-5000 - s / 1000:.1f}\n Density = 1.01\n" for s in range(500, 5001, 500))
                + "      A V E R A G E S   O V E R\n NSTEP = 5000 TIME(PS) = 999 TEMP(K) = 1 EPtot = 0\n")
        out = tmp / "report"
        import sys
        old, sys.argv = sys.argv, ["report.py", "--analyses", str(tmp / "an"),
                                   "--n-clusters", "0", "--out", str(out)]
        try:
            main()
        finally:
            sys.argv = old
        page = (out / "report.html").read_text()
        assert page.count("<svg") == 9, page.count("<svg")  # 5 core + 2 ligand + 2 energy (NVT: no density)
        assert "Incomplete production: replica 1" in page and "38218" in page and "JZ4130 complex" in page
        assert "ASN46@ND2" in page and "LEU84" in page and "Clustering skipped" in page
        assert "A V E R A G E S" not in page
        rows = list(csv.DictReader((out / "summary.csv").open()))
        assert [r["chunks_completed"] for r in rows] == ["2", "1"] and float(rows[1]["rmsd_backbone_mean_A"]) > 1.5
        assert len(mdout_energies((tmp / "an/0/mdout/prod_1.mdout").read_text())) == 10
        assert top_hbonds([load_replica(tmp / "an/0")])[0][2] == 0.8
    print("report.py: self-check OK")


if __name__ == "__main__":
    import sys

    if "--self-test" in sys.argv:
        demo()
    else:
        main()
