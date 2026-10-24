#!/usr/bin/env python3
"""
Stage 3 (report): one HTML page for a UMA MD run.

Reads the md task's ``thermo.csv`` and ``md_summary.json`` and writes a
self-contained ``report.html``: a summary table (inference mode, speed in
ns/day, system size) and inline SVG plots of temperature and energy over time.

stdlib only.

Usage:
    report.py --thermo thermo.csv --summary md_summary.json --out report.html
    report.py --selftest
"""

import argparse
import csv
import html
import json
import sys
import tempfile
from pathlib import Path

W, H, PAD = 640, 220, 48


def chart(title: str, unit: str, xs: list[float], series: dict[str, list[float]]) -> str:
    """A line chart of one or more series sharing the y axis."""
    allys = [y for ys in series.values() for y in ys]
    lo, hi = min(allys), max(allys)
    span_y = (hi - lo) or 1.0
    span_x = (max(xs) - min(xs)) or 1.0
    colors = ["var(--accent)", "var(--muted)"]
    lines = []
    for (name, ys), color in zip(series.items(), colors, strict=False):
        pts = " ".join(
            f"{PAD + (x - min(xs)) / span_x * (W - 2 * PAD):.1f},"
            f"{H - PAD - (y - lo) / span_y * (H - 2 * PAD):.1f}"
            for x, y in zip(xs, ys, strict=True)
        )
        lines.append(f'<polyline fill="none" stroke="{color}" stroke-width="1.5" points="{pts}"><title>{html.escape(name)}</title></polyline>')
    legend = " · ".join(
        f'<span style="color:{c}">■</span> {html.escape(n)}'
        for n, c in zip(series, colors, strict=False)
    )
    return f"""<figure><figcaption>{html.escape(title)} <small>({legend})</small></figcaption>
<svg viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(title)}">
<line x1="{PAD}" y1="{H - PAD}" x2="{W - PAD}" y2="{H - PAD}" stroke="var(--grid)"/>
<line x1="{PAD}" y1="{PAD}" x2="{PAD}" y2="{H - PAD}" stroke="var(--grid)"/>
<text x="{PAD - 6}" y="{PAD + 4}" text-anchor="end">{hi:.4g}</text>
<text x="{PAD - 6}" y="{H - PAD}" text-anchor="end">{lo:.4g}</text>
<text x="{PAD - 6}" y="{PAD - 14}" text-anchor="start">{html.escape(unit)}</text>
<text x="{PAD}" y="{H - PAD + 16}" text-anchor="middle">{min(xs):.3g}</text>
<text x="{W - PAD}" y="{H - PAD + 16}" text-anchor="middle">{max(xs):.3g} ps</text>
{''.join(lines)}
</svg></figure>"""


def build(thermo: Path, summary: Path, out: Path) -> int:
    """Write the report; returns the number of thermo rows plotted."""
    rows = list(csv.DictReader(thermo.open()))
    if not rows:
        raise ValueError(f"{thermo} has no rows")
    info = json.loads(summary.read_text())
    col = lambda k: [float(r[k]) for r in rows]  # noqa: E731
    t = col("time_ps")
    temps = col("temperature_K")
    table = "".join(
        f"<tr><th>{html.escape(k.replace('_', ' '))}</th><td>{html.escape(str(v))}</td></tr>"
        for k, v in info.items()
    )
    mean_t = sum(temps) / len(temps)
    # Absolute energies (~1e5 eV) lose every visible digit on the axis.
    e0 = float(rows[0]["epot_eV"])
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>UMA MD report</title>
<style>
:root {{ --bg:#faf9f6; --fg:#0f1419; --accent:#b07d48; --muted:#1a2332; --grid:#c9c4b8; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#0f1419; --fg:#faf9f6; --accent:#d4a574; --muted:#8fa3bf; --grid:#3a4556; }} }}
body {{ background:var(--bg); color:var(--fg); font:15px/1.5 system-ui,sans-serif; max-width:720px; margin:2rem auto; padding:0 16px; }}
table {{ border-collapse:collapse; width:100%; }} th,td {{ text-align:left; padding:4px 8px; border-bottom:1px solid var(--grid); }}
th {{ font-weight:500; width:40%; }} svg {{ width:100%; height:auto; }} svg text {{ fill:var(--fg); font-size:11px; }}
figure {{ margin:1.5rem 0; }} figcaption {{ font-weight:500; }} .big {{ font-size:1.6rem; font-weight:600; }}
</style></head><body>
<h1>UMA molecular dynamics</h1>
<p><span class="big">{float(info.get("ns_per_day", 0)):.3g} ns/day</span> in <b>{html.escape(str(info.get("inference_mode")))}</b> mode
on {html.escape(str(info.get("device")))}, {info.get("atoms")} atoms. Mean T {mean_t:.1f} K over {len(rows)} frames.</p>
<table>{table}</table>
{chart("Temperature", "K", t, {"T": temps})}
{chart("Energy relative to the first frame's E potential", "eV", t, {"E total": [e - e0 for e in col("etot_eV")], "E potential": [e - e0 for e in col("epot_eV")]})}
</body></html>"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)
    return len(rows)


def _selftest() -> None:
    """Build a report from a tiny fixture and check what it shows."""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "thermo.csv").write_text(
            "step,time_ps,epot_eV,ekin_eV,etot_eV,temperature_K\n"
            "0,0.0,-10.0,1.0,-9.0,290.0\n10,0.005,-10.2,1.1,-9.1,310.0\n"
        )
        (d / "s.json").write_text(json.dumps({"inference_mode": "nitro", "ns_per_day": 1.5, "atoms": 192, "device": "NVIDIA L4"}))
        n = build(d / "thermo.csv", d / "s.json", d / "r.html")
        page = (d / "r.html").read_text()
        assert n == 2, n
        assert "<b>nitro</b>" in page and "1.5 ns/day" in page and "Mean T 300.0 K" in page, page
        assert page.count("<polyline") == 3, page.count("<polyline")
        assert ">1<" in page and ">-0.2<" in page, "energy axis is relative to frame 0"
    print("report.py selftest: OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the UMA MD report.")
    parser.add_argument("--thermo", type=Path)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        _selftest()
        return 0
    if not (args.thermo and args.summary and args.out):
        parser.error("--thermo, --summary and --out are required")
    n = build(args.thermo, args.summary, args.out)
    print(f"report.py: plotted {n} frames to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
