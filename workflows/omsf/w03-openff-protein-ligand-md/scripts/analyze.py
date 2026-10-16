#!/usr/bin/env python3
# Per replica: protein C-alpha RMSD and ligand heavy-atom RMSD (after aligning
# on the protein C-alphas) against the starting structure. Writes rmsd.csv
# (renders as a table), final_frame.pdb (protein + ligand, last frame of the
# first replica) and a self-contained report.html with a Mol* view of it.

import argparse
import os
import csv
import html
import json
import sys
from pathlib import Path

# Shared host: cap BLAS/torch threads unless the caller set them.
os.environ.setdefault("OMP_NUM_THREADS", "2")

LIGAND = "resname UNK and not element H"  # Interchange names the ligand UNK
COLUMNS = ["replica", "frame", "time_ps", "protein_ca_rmsd_A", "ligand_rmsd_A"]
MOLSTAR = "https://cdn.jsdelivr.net/npm/molstar@5/build/viewer"

CSS = """
body{font:14px system-ui,sans-serif;margin:0;padding:24px;color:#111827;background:#fff}
h1{font-size:20px;margin:0 0 16px}
h2{font-size:15px;margin:24px 0 8px}
.stats{display:flex;gap:12px;flex-wrap:wrap}
.stat{border:1px solid #e5e7eb;border-radius:8px;padding:10px 16px;min-width:110px}
.stat b{display:block;font-size:22px}
.stat span{color:#6b7280;font-size:12px}
#mol{position:relative;height:460px;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden}
#status{min-height:18px;margin-top:4px;font-size:12px;color:#b91c1c}
table{border-collapse:collapse}
td,th{border-bottom:1px solid #e5e7eb;padding:6px 12px;text-align:right}
"""

VIEWER_JS = """
const D = JSON.parse(document.getElementById('data').textContent);
const status = document.getElementById('status');
if (typeof molstar === 'undefined') {
  status.textContent = 'Mol* could not be loaded (needs access to cdn.jsdelivr.net).';
} else {
  molstar.Viewer.create('mol', {layoutIsExpanded: false, layoutShowControls: false,
    layoutShowRemoteState: false, layoutShowSequence: false, layoutShowLog: false,
    viewportShowExpand: false})
    .then(v => v.loadStructureFromData(D.pdb, 'pdb', {dataLabel: 'Final frame'}))
    .catch(e => { status.textContent = 'Mol* failed to start: ' + e; });
}
"""


def frame_times(log_csv: str) -> list[float]:
    """Time (ps) column of the StateDataReporter log, written at the DCD interval."""
    rows = list(csv.reader(log_csv.splitlines()))
    col = rows[0].index("Time (ps)")
    return [float(r[col]) for r in rows[1:] if r]


def summarize(rows: list[dict]) -> list[dict]:
    """One line per replica: final and mean RMSDs."""
    out = []
    for rep in sorted({r["replica"] for r in rows}):
        rs = [r for r in rows if r["replica"] == rep]
        out.append({
            "replica": rep, "frames": len(rs), "time_ps": rs[-1]["time_ps"],
            "final_protein": rs[-1]["protein_ca_rmsd_A"],
            "final_ligand": rs[-1]["ligand_rmsd_A"],
            "mean_ligand": round(sum(r["ligand_rmsd_A"] for r in rs) / len(rs), 3),
        })
    return out


def render(summary: list[dict], pdb: str) -> str:
    cells = ("replica", "frames", "time_ps", "final_protein", "final_ligand", "mean_ligand")
    head = ("Replica", "Frames", "Time (ps)", "Protein Cα RMSD, final (Å)",
            "Ligand RMSD, final (Å)", "Ligand RMSD, mean (Å)")
    rows = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(s[c]))}</td>" for c in cells) + "</tr>"
        for s in summary)
    stats = [("Replicas", len(summary)),
             ("Simulated per replica (ps)", summary[0]["time_ps"] if summary else 0),
             ("Max final ligand RMSD (Å)",
              max((s["final_ligand"] for s in summary), default=0))]
    cards = "".join(f"<div class=stat><b>{v}</b><span>{k}</span></div>" for k, v in stats)
    # '</' would end the <script> early; JSON allows the escaped form.
    data = json.dumps({"pdb": pdb}).replace("</", "<\\/")
    return (
        "<!doctype html><html><head><meta charset=utf-8>"
        f"<title>OpenFF protein-ligand MD</title><style>{CSS}</style>"
        f"<link rel=stylesheet href={MOLSTAR}/molstar.css></head><body>"
        "<h1>PT2385 / HIF-2α (5TBM): Sage 2.3.0 + ff14SB MD</h1>"
        f"<div class=stats>{cards}</div>"
        "<h2>Final frame (replica 0, protein + ligand)</h2><div id=mol></div><div id=status></div>"
        "<h2>Replicas</h2><table><tr>"
        + "".join(f"<th>{h}</th>" for h in head) + f"</tr>{rows}</table>"
        f"<script id=data type=application/json>{data}</script>"
        f"<script src={MOLSTAR}/molstar.js></script><script>{VIEWER_JS}</script></body></html>"
    )


def analyze(trajectories: Path, final_frame: Path) -> list[dict]:
    import mdtraj as md

    rows = []
    for rep in sorted((p for p in trajectories.iterdir() if p.is_dir()), key=lambda p: int(p.name)):
        ref = md.load(str(rep / "complex.pdb"))
        traj = md.load(str(rep / "trajectory.dcd"), top=ref.topology)
        ca, lig = ref.topology.select("protein and name CA"), ref.topology.select(LIGAND)
        assert len(lig), f"no ligand atoms in {rep}"
        traj.superpose(ref, atom_indices=ca)
        prot = md.rmsd(traj, ref, atom_indices=ca, precentered=False) * 10
        # rmsd() would re-align on the ligand; we want drift in the pocket frame
        diff = traj.xyz[:, lig] - ref.xyz[0, lig]
        ligr = ((diff ** 2).sum(-1).mean(-1) ** 0.5) * 10
        times = frame_times((rep / "log.csv").read_text())
        assert len(times) == traj.n_frames, (len(times), traj.n_frames)
        for i, (t, p, l) in enumerate(zip(times, prot, ligr)):
            rows.append({"replica": int(rep.name), "frame": i, "time_ps": round(float(t), 2),
                         "protein_ca_rmsd_A": round(float(p), 3),
                         "ligand_rmsd_A": round(float(l), 3)})
        if not final_frame.exists():
            traj[-1].atom_slice(ref.topology.select("protein or resname UNK")).save_pdb(str(final_frame))
        print(f"replica {rep.name}: {traj.n_frames} frames, final ligand RMSD "
              f"{ligr[-1]:.2f} A", flush=True)
    return rows


def selftest() -> None:
    rows = [{"replica": r, "frame": f, "time_ps": 2.0 * (f + 1),
             "protein_ca_rmsd_A": 0.5 * f, "ligand_rmsd_A": 1.0 * f}
            for r in (0, 1) for f in range(3)]
    s = summarize(rows)
    assert [x["replica"] for x in s] == [0, 1]
    assert s[0]["frames"] == 3 and s[0]["final_ligand"] == 2.0 and s[0]["mean_ligand"] == 1.0
    log = '#"Step","Time (ps)","Temperature (K)"\n250,0.5000000000000003,240\n500,1.0,260\n'
    assert frame_times(log) == [0.5000000000000003, 1.0]
    page = render(s, "ATOM </script>\nEND\n")
    assert "</script>\\nEND" not in page and "<\\/script>" in page
    assert page.count("<tr>") == 3 and "molstar.js" in page
    print("selftest ok")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trajectories", type=Path)
    ap.add_argument("--table", type=Path)
    ap.add_argument("--final-frame", type=Path)
    ap.add_argument("--report", type=Path)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not (a.trajectories and a.table and a.final_frame and a.report):
        sys.exit("--trajectories, --table, --final-frame and --report are required")
    for p in (a.table, a.final_frame, a.report):
        p.parent.mkdir(parents=True, exist_ok=True)
    a.final_frame.unlink(missing_ok=True)
    rows = analyze(a.trajectories, a.final_frame)
    with a.table.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    a.report.write_text(render(summarize(rows), a.final_frame.read_text()))


if __name__ == "__main__":
    main()
