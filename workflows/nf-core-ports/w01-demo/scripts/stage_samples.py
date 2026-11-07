#!/usr/bin/env python3
"""
Split an nf-core/demo samplesheet into one folder per sample.

Rows with the same ``sample`` are runs of one sample and are merged, as the
pipeline's samplesheet check does: their reads go into one folder, in row
order, and they must all be single-end or all paired-end. Each folder holds
the reads under their original file names plus ``reads.txt``, the read order.
``fastq_1``/``fastq_2`` may be URLs (downloaded) or paths relative to the
samplesheet.

stdlib only.

Usage:
    stage_samples.py --samplesheet samplesheet.csv --out samples/
    stage_samples.py --selftest
"""

from __future__ import annotations

import argparse
import csv
import os
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path


def group_rows(rows: list[dict[str, str]]) -> dict[str, list[str]]:
    """Map each sample to its reads in order, checking endedness per sample."""
    samples: dict[str, list[str]] = {}
    ends: dict[str, bool] = {}
    for row in rows:
        sample = row["sample"].strip()
        if not sample or any(c.isspace() for c in sample):
            raise ValueError(f"invalid sample name: {sample!r}")
        reads = [r.strip() for r in (row["fastq_1"], row.get("fastq_2") or "") if r.strip()]
        if not reads:
            raise ValueError(f"{sample}: fastq_1 is required")
        single = len(reads) == 1
        if ends.setdefault(sample, single) != single:
            raise ValueError(f"{sample}: runs mix single-end and paired-end reads")
        samples.setdefault(sample, []).extend(reads)
    return samples


def fetch(src: str, base: Path, dest: Path) -> None:
    """Download a URL or copy a local path to *dest*, atomically."""
    part = dest.with_name(dest.name + ".part")
    if "://" in src:
        with urllib.request.urlopen(src) as resp, open(part, "wb") as fh:
            shutil.copyfileobj(resp, fh)
    else:
        shutil.copyfile(base / src, part)
    os.replace(part, dest)


def stage(samplesheet: Path, out: Path) -> None:
    with open(samplesheet, newline="") as fh:
        samples = group_rows(list(csv.DictReader(fh)))
    out.mkdir(parents=True, exist_ok=True)
    fetched: dict[str, Path] = {}
    for sample, reads in samples.items():
        sdir = out / sample
        sdir.mkdir(exist_ok=True)
        names = [Path(r).name for r in reads]
        if len(set(names)) != len(names):
            raise ValueError(f"{sample}: two reads share a file name")
        for src, name in zip(reads, names):
            dest = sdir / name
            if src in fetched:
                shutil.copyfile(fetched[src], dest)
            else:
                fetch(src, samplesheet.parent, dest)
                fetched[src] = dest
        (sdir / "reads.txt").write_text("\n".join(names) + "\n")


def selftest() -> None:
    rows = [
        {"sample": "A", "fastq_1": "a1.fq.gz", "fastq_2": "a2.fq.gz"},
        {"sample": "B", "fastq_1": "b1.fq.gz", "fastq_2": ""},
        {"sample": "B", "fastq_1": "b2.fq.gz", "fastq_2": ""},
    ]
    assert group_rows(rows) == {"A": ["a1.fq.gz", "a2.fq.gz"], "B": ["b1.fq.gz", "b2.fq.gz"]}
    try:
        group_rows(rows + [{"sample": "B", "fastq_1": "x", "fastq_2": "y"}])
    except ValueError:
        pass
    else:
        raise AssertionError("mixed endedness accepted")
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        for name in ("a1.fq.gz", "a2.fq.gz", "b1.fq.gz", "b2.fq.gz"):
            (t / name).write_text(name)
        sheet = t / "sheet.csv"
        with open(sheet, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["sample", "fastq_1", "fastq_2"])
            w.writeheader()
            w.writerows(rows)
        stage(sheet, t / "out")
        assert (t / "out/B/reads.txt").read_text() == "b1.fq.gz\nb2.fq.gz\n"
        assert (t / "out/A/a2.fq.gz").read_text() == "a2.fq.gz"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--samplesheet", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return 0
    if not args.samplesheet or not args.out:
        ap.error("--samplesheet and --out are required")
    stage(args.samplesheet, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
