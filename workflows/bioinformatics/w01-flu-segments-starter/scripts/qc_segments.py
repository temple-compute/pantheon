"""Per-segment sequence QC for influenza segments.

Conceptually the input-validation step that precedes translation in an
influenza genotyping pipeline (e.g. FluTyper). Flags, per segment:
  * length outside the approximate expected range for that segment
  * fraction of N / ambiguous bases above --max-n-frac
  * length not a multiple of 3 for single-ORF coding segments

The length table is approximate (segment CDS up to full segment incl. UTRs,
influenza A) and meant to be edited. MP and NS are spliced and often carry
UTRs, so the multiple-of-3 check is skipped for them.

Usage:
    qc_segments.py --samples-dir samples/ --out qc.csv [--max-n-frac 0.01] [--len-tolerance 0.0]
    qc_segments.py --selftest

Output qc.csv: sample,segment,length,n_frac,status,reason (sorted).
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# segment: (min_len, max_len, check_mod3) -- approximate influenza A values
RANGES = {
    "PB2": (2250, 2350, True), "PB1": (2250, 2350, True), "PA": (2100, 2250, True),
    "HA": (1650, 1780, True), "NP": (1480, 1570, True), "NA": (1350, 1470, True),
    "MP": (900, 1030, False), "NS": (800, 900, False),
}


def read_fasta(path: Path):
    header, seq = None, []
    for line in path.read_text().splitlines():
        if line.startswith(">"):
            if header is not None:
                yield header, "".join(seq)
            header, seq = line[1:].strip(), []
        elif line.strip():
            seq.append(line.strip())
    if header is not None:
        yield header, "".join(seq)


def qc(segment: str, seq: str, max_n_frac: float, tol: float):
    seq = seq.upper()
    lo, hi, mod3 = RANGES[segment]
    lo, hi = lo * (1 - tol), hi * (1 + tol)
    n_frac = sum(c not in "ACGT" for c in seq) / len(seq) if seq else 1.0
    reasons = []
    if not lo <= len(seq) <= hi:
        reasons.append(f"length {len(seq)} outside {int(lo)}-{int(hi)}")
    if n_frac > max_n_frac:
        reasons.append(f"N/ambiguous fraction {n_frac:.3f} > {max_n_frac}")
    if mod3 and len(seq) % 3:
        reasons.append("length not multiple of 3")
    return len(seq), n_frac, ("FAIL" if reasons else "PASS"), "; ".join(reasons)


def run(samples_dir: Path, max_n_frac: float, tol: float):
    rows = []
    for fa in sorted(samples_dir.glob("*.fasta")):
        for header, seq in read_fasta(fa):
            sample, segment = header.split("|")
            rows.append((sample, segment, *qc(segment, seq, max_n_frac, tol)))
    return sorted(rows)


def selftest():
    good = "ATG" + "A" * 1698
    assert qc("HA", good, 0.01, 0)[2] == "PASS"
    assert "N/ambiguous" in qc("HA", "N" * 50 + good[50:], 0.01, 0)[3]
    assert "outside" in qc("NA", "ATG" * 100, 0.01, 0)[3]
    assert qc("HA", good + "A", 0.01, 0)[3].endswith("multiple of 3")
    assert qc("NS", "A" * 839, 0.01, 0)[2] == "PASS"  # mod3 not checked for NS
    assert qc("NA", "ATG" * 100, 0.01, 0.8)[2] == "PASS"  # tolerance widens the range
    print("qc_segments selftest OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--samples-dir", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--max-n-frac", type=float, default=0.01)
    ap.add_argument("--len-tolerance", type=float, default=0.0,
                    help="widen each length range by this fraction")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not (a.samples_dir and a.out):
        ap.error("--samples-dir and --out are required")
    rows = run(a.samples_dir, a.max_n_frac, a.len_tolerance)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["sample", "segment", "length", "n_frac", "status", "reason"])
        w.writerows((s, g, n, f"{f:.4f}", st, r) for s, g, n, f, st, r in rows)
    print(f"{sum(r[4] == 'PASS' for r in rows)}/{len(rows)} segments PASS")


if __name__ == "__main__":
    sys.exit(main())
