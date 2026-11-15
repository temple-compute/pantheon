#!/usr/bin/env python3
"""
Split an nf-core/scrnaseq samplesheet into one folder per sample.

Rows with the same ``sample`` are runs of one sample and are merged, as the
pipeline's samplesheet check does: their reads go into one folder, in row
order (R1, R2 per row), and they must all be single-end or all paired-end.
Each folder holds the reads under their original file names, ``reads.txt``
(the read order) and ``meta.env``, the first row's meta as bash-sourceable
lines (``expected_cells``, ``seq_center``), as ``groupTuple`` keeps
``metas[0]``. ``fastq_1``/``fastq_2`` may be URLs (downloaded) or paths
relative to the samplesheet.

stdlib only.

Usage:
    stage_samples.py --samplesheet samplesheet.csv --out samples/
    stage_samples.py --selftest
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import shlex
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

ID_RE = re.compile(r"[^\s]+")


def group_rows(rows: list[dict[str, str]]) -> dict[str, dict]:
    """Map each sample to its reads in order plus the first row's meta."""
    samples: dict[str, dict] = {}
    for row in rows:
        sample = (row.get("sample") or "").strip()
        if not ID_RE.fullmatch(sample):
            raise ValueError(f"invalid sample name: {sample!r}")
        reads = [r.strip() for r in (row.get("fastq_1") or "", row.get("fastq_2") or "") if r.strip()]
        if not (row.get("fastq_1") or "").strip():
            raise ValueError(f"{sample}: fastq_1 is required")
        single = len(reads) == 1
        meta = {
            "expected_cells": (row.get("expected_cells") or "").strip(),
            "seq_center": (row.get("seq_center") or "").strip(),
        }
        if meta["expected_cells"] and not meta["expected_cells"].isdigit():
            raise ValueError(f"{sample}: expected_cells must be an integer")
        s = samples.setdefault(sample, {"single_end": single, "reads": [], "meta": meta})
        if s["single_end"] != single:
            raise ValueError(
                "Please check input samplesheet -> Multiple runs of a sample must be of the "
                f"same datatype i.e. single-end or paired-end: {sample}"
            )
        s["reads"].extend(reads)
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
    for sample, s in samples.items():
        sdir = out / sample
        sdir.mkdir(exist_ok=True)
        names = [Path(r).name for r in s["reads"]]
        if len(set(names)) != len(names):
            raise ValueError(f"{sample}: two reads share a file name")
        for src, name in zip(s["reads"], names):
            fetch(src, samplesheet.parent, sdir / name)
        (sdir / "reads.txt").write_text("\n".join(names) + "\n")
        (sdir / "meta.env").write_text("".join(f"{k}={shlex.quote(v)}\n" for k, v in s["meta"].items()))


def selftest() -> None:
    rows = [
        {"sample": "A", "fastq_1": "a1.fq.gz", "fastq_2": "a2.fq.gz", "expected_cells": "5000", "seq_center": "Broad Institute"},
        {"sample": "B", "fastq_1": "b1.fq.gz", "fastq_2": "b2.fq.gz", "expected_cells": "", "seq_center": "CRG"},
        {"sample": "B", "fastq_1": "b3.fq.gz", "fastq_2": "b4.fq.gz", "expected_cells": "9", "seq_center": "X"},
    ]
    g = group_rows(rows)
    assert g["B"]["reads"] == ["b1.fq.gz", "b2.fq.gz", "b3.fq.gz", "b4.fq.gz"]
    assert g["B"]["meta"] == {"expected_cells": "", "seq_center": "CRG"}
    for bad in ({"sample": "B", "fastq_1": "x", "fastq_2": ""}, {"sample": "C", "fastq_1": "x", "expected_cells": "1e3"}):
        try:
            group_rows(rows + [bad])
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad}")
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        for r in rows:
            for k in ("fastq_1", "fastq_2"):
                (t / r[k]).write_text(r[k])
        sheet = t / "sheet.csv"
        with open(sheet, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        stage(sheet, t / "out")
        assert (t / "out/B/reads.txt").read_text() == "b1.fq.gz\nb2.fq.gz\nb3.fq.gz\nb4.fq.gz\n"
        assert (t / "out/A/meta.env").read_text() == "expected_cells=5000\nseq_center='Broad Institute'\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
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
