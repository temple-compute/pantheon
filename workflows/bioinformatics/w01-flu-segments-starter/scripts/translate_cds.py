"""Find the longest ORF of each QC-passing segment and translate it.

Conceptually the GetCDS + TranslateToProtein stages of an influenza genotyping
pipeline (e.g. FluTyper). Forward strand only, 3 frames; an ORF starts at ATG
and runs to the next stop codon (or the end of the sequence, then the stop
codon is reported as absent). Needs Biopython (installed by the uv env executor).

Usage:
    translate_cds.py --samples-dir samples/ --qc qc.csv --faa proteins.faa --csv proteins.csv
    translate_cds.py --selftest

Output proteins.csv: sample,segment,aa_length,start,stop_codon (start = 1-based nt).
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from Bio.Seq import Seq


def longest_orf(seq: str):
    """Return (protein, start_nt_1based, stop_present) of the longest ATG..stop ORF."""
    best = ("", 0, False)
    for frame in range(3):
        prot = str(Seq(seq[frame:len(seq) - (len(seq) - frame) % 3]).translate())
        pos = 0
        for chunk in prot.split("*"):
            stop = pos + len(chunk) < len(prot)
            m = chunk.find("M")
            if m >= 0 and len(chunk) - m > len(best[0]):
                best = (chunk[m:], frame + 3 * (pos + m) + 1, stop)
            pos += len(chunk) + 1
    return best


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


def run(samples_dir: Path, qc_csv: Path):
    with open(qc_csv, newline="") as fh:
        passed = {(r["sample"], r["segment"]) for r in csv.DictReader(fh) if r["status"] == "PASS"}
    out = []
    for fa in sorted(samples_dir.glob("*.fasta")):
        for header, seq in read_fasta(fa):
            sample, segment = header.split("|")
            if (sample, segment) in passed:
                out.append((sample, segment, *longest_orf(seq.upper())))
    return sorted(out)


def selftest():
    prot, start, stop = longest_orf("CC" + "ATGAAATTTGGG" + "TAA" + "ATGAAA")
    assert (prot, start, stop) == ("MKFG", 3, True), (prot, start, stop)
    prot, start, stop = longest_orf("ATGAAATTT")
    assert (prot, stop) == ("MKF", False)
    print("translate_cds selftest OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--samples-dir", type=Path)
    ap.add_argument("--qc", type=Path)
    ap.add_argument("--faa", type=Path)
    ap.add_argument("--csv", type=Path)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not (a.samples_dir and a.qc and a.faa and a.csv):
        ap.error("--samples-dir, --qc, --faa and --csv are required")
    rows = run(a.samples_dir, a.qc)
    a.faa.parent.mkdir(parents=True, exist_ok=True)
    a.csv.parent.mkdir(parents=True, exist_ok=True)
    with open(a.faa, "w") as fh:
        for s, g, prot, *_ in rows:
            fh.write(f">{s}|{g}\n{prot}\n")
    with open(a.csv, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["sample", "segment", "aa_length", "start", "stop_codon"])
        w.writerows((s, g, len(p), st, "yes" if sp else "no") for s, g, p, st, sp in rows)
    print(f"translated {len(rows)} segments")


if __name__ == "__main__":
    sys.exit(main())
