"""Merge segments, QC and proteins into one plain-HTML report.

Conceptually the reporting stage (index.html / final results tables) of an
influenza genotyping pipeline (e.g. FluTyper). Builds a sample x segment grid
coloured PASS/FAIL with protein lengths, an error count, and -- if a metadata
CSV with an ID column is supplied and exists -- merges it by sample ID
(MetadataMerge-like). A missing/absent metadata file is skipped silently.

Usage:
    summary_report.py --segments segments.csv --qc qc.csv --proteins proteins.csv \
        --errors errors.log --out report.html [--metadata metadata.csv]
    summary_report.py --selftest
"""
from __future__ import annotations

import argparse
import csv
import sys
from html import escape
from pathlib import Path

ORDER = ["PB2", "PB1", "PA", "HA", "NP", "NA", "MP", "NS"]
COLOR = {"PASS": "#cfe8cf", "FAIL": "#f4c7c3"}


def read_csv(path: Path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def render(segments, qc, proteins, n_errors, metadata=None):
    qc_by = {(r["sample"], r["segment"]): r for r in qc}
    aa_by = {(r["sample"], r["segment"]): r["aa_length"] for r in proteins}
    meta_by = {r.get("ID", ""): r for r in metadata or []}
    meta_cols = [c for c in (metadata[0] if metadata else {}) if c != "ID"]
    samples = sorted({r["sample"] for r in segments})
    head = "".join(f"<th>{escape(c)}</th>" for c in ["Sample", *meta_cols, *ORDER])
    body = []
    for s in samples:
        cells = [f"<td>{escape(s)}</td>"]
        cells += [f"<td>{escape(meta_by.get(s, {}).get(c, ''))}</td>" for c in meta_cols]
        for seg in ORDER:
            r = qc_by.get((s, seg))
            if r is None:
                cells.append("<td></td>")
                continue
            aa = aa_by.get((s, seg))
            txt = f"{r['status']}<br>{r['length']} nt" + (f" / {aa} aa" if aa else "")
            tip = escape(r["reason"])
            cells.append(f'<td style="background:{COLOR[r["status"]]}" title="{tip}">{txt}</td>')
        body.append(f"<tr>{''.join(cells)}</tr>")
    n_fail = sum(r["status"] == "FAIL" for r in qc)
    return (
        "<!doctype html><meta charset='utf-8'><title>Influenza segment QC</title>"
        "<style>body{font:14px sans-serif;margin:2em}table{border-collapse:collapse}"
        "td,th{border:1px solid #999;padding:4px 8px;text-align:center}</style>"
        f"<h1>Influenza segment QC</h1><p>{len(samples)} samples, {len(qc)} segments, "
        f"{n_fail} FAIL, {n_errors} header errors (see errors.log)</p>"
        f"<table><tr>{head}</tr>{''.join(body)}</table>\n"
    )


def selftest():
    seg = [{"sample": "S1"}, {"sample": "S2"}]
    qc = [{"sample": "S1", "segment": "HA", "length": "1701", "status": "PASS", "reason": ""},
          {"sample": "S2", "segment": "HA", "length": "9", "status": "FAIL", "reason": "length 9 <b>"}]
    prot = [{"sample": "S1", "segment": "HA", "aa_length": "566"}]
    html = render(seg, qc, prot, 2, [{"ID": "S1", "DATE": "2024-01-01"}])
    assert "PASS<br>1701 nt / 566 aa" in html and "1 FAIL, 2 header errors" in html
    assert "<th>DATE</th>" in html and "2024-01-01" in html and "&lt;b&gt;" in html
    assert "<th>DATE</th>" not in render(seg, qc, prot, 0)
    print("summary_report selftest OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for k in ("segments", "qc", "proteins", "errors", "out", "metadata"):
        ap.add_argument(f"--{k}", type=Path)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not all((a.segments, a.qc, a.proteins, a.errors, a.out)):
        ap.error("--segments, --qc, --proteins, --errors and --out are required")
    meta = read_csv(a.metadata) if a.metadata and a.metadata.is_file() else None
    n_err = len([l for l in a.errors.read_text().splitlines() if l.strip()])
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(render(read_csv(a.segments), read_csv(a.qc), read_csv(a.proteins), n_err, meta))
    print(f"wrote {a.out}")


if __name__ == "__main__":
    sys.exit(main())
