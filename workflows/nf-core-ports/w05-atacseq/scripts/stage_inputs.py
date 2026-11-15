#!/usr/bin/env python3
"""
Stage the nf-core/atacseq inputs: reference files and per-run reads.

``reference`` downloads the genome fasta and GTF (or copies them from a local
mirror) into one folder and writes ``refs.env`` with their file names.

``reads`` reads the samplesheet that SAMPLESHEET_CHECK wrote
(``samplesheet.valid.csv``: one row per run, ids ``<sample>_REP<n>_T<n>``)
and writes

- ``reads/<id>/``: the run's reads under their original names, plus
  ``reads.txt`` (R1 then R2);
- ``runs/<id>``: a bash-sourceable meta file (``single_end``, ``control``).

Sources are URLs (``curl -fL`` to ``<name>.part``, then renamed) or paths
relative to the samplesheet (copied). An absolute local path is symlinked, as
Nextflow stages it. With ``--mirror DIR``, a file whose name exists anywhere
under DIR is copied from there instead of downloaded.

stdlib only.

Usage:
    stage_inputs.py reference --fasta URL --gtf URL --out reference/
    stage_inputs.py reads --valid samplesheet.valid.csv --samplesheet sheet.csv --reads reads/ --runs runs/
    stage_inputs.py --selftest
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ID_RE = re.compile(r"[A-Za-z0-9._-]+")


def find_in_mirror(mirror: str, name: str) -> Path | None:
    if not mirror:
        return None
    for root, _dirs, files in os.walk(mirror):
        if name in files:
            return Path(root) / name
    return None


def fetch(src: str, base: Path, dest: Path, mirror: str) -> None:
    """Copy *src* (URL or path) to *dest* through ``dest.part``; link an absolute path."""
    part = dest.with_name(dest.name + ".part")
    local = find_in_mirror(mirror, Path(src).name) if "://" in src else base / src
    if "://" not in src and Path(src).is_absolute():
        # Nextflow stages local inputs as symlinks; a copy would move every byte.
        local.stat()  # a missing input fails here, as the copy would
        part.unlink(missing_ok=True)
        part.symlink_to(local)
    elif local is not None:
        shutil.copyfile(local, part)
    else:
        subprocess.run(["curl", "-fsSL", "--retry", "3", "-o", str(part), src], check=True)
    os.replace(part, dest)


def stage_reference(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    env = {}
    for key in ("fasta", "gtf"):
        name = Path(getattr(args, key)).name
        fetch(getattr(args, key), Path.cwd(), out / name, args.mirror)
        env[f"ref_{key}"] = name
    (out / "refs.env").write_text("".join(f"{k}={v}\n" for k, v in env.items()))


def stage_reads(args: argparse.Namespace) -> None:
    reads_dir, runs_dir = Path(args.reads), Path(args.runs)
    reads_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)
    with open(args.valid, newline="") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        rid = row["sample"]
        if not ID_RE.fullmatch(rid):
            raise ValueError(f"invalid sample name {rid!r}: use letters, digits, '.', '_' or '-'")
        srcs = [row["fastq_1"]] + ([row["fastq_2"]] if row["single_end"] == "0" else [])
        names = [Path(s).name for s in srcs]
        if len(set(names)) != len(names):
            raise ValueError(f"{rid}: R1 and R2 share a file name")
        (reads_dir / rid).mkdir(exist_ok=True)
        for src, name in zip(srcs, names):
            fetch(src, Path(args.samplesheet).parent, reads_dir / rid / name, args.mirror)
        (reads_dir / rid / "reads.txt").write_text("\n".join(names) + "\n")
        single_end = "true" if row["single_end"] == "1" else "false"
        (runs_dir / rid).write_text(f"single_end={single_end}\ncontrol={row.get('control', '')}\n")


def selftest() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        for n in ("a_1.fastq.gz", "a_2.fastq.gz", "b_1.fastq.gz"):
            (t / n).write_text(n)
        valid = t / "samplesheet.valid.csv"
        valid.write_text(
            "sample,fastq_1,fastq_2,replicate,single_end,control\n"
            "A_REP1_T1,a_1.fastq.gz,a_2.fastq.gz,1,0,\n"
            "B_REP1_T1,b_1.fastq.gz,,1,1,\n"
        )
        ns = argparse.Namespace(valid=valid, samplesheet=t / "sheet.csv", reads=t / "r", runs=t / "m", mirror="")
        stage_reads(ns)
        assert (t / "r/A_REP1_T1/reads.txt").read_text() == "a_1.fastq.gz\na_2.fastq.gz\n"
        assert (t / "r/B_REP1_T1/reads.txt").read_text() == "b_1.fastq.gz\n"
        assert (t / "m/B_REP1_T1").read_text() == "single_end=true\ncontrol=\n"
        assert (t / "m/A_REP1_T1").read_text().startswith("single_end=false")
        fetch(str(t / "a_1.fastq.gz"), t, t / "abs.fq.gz", "")
        assert (t / "abs.fq.gz").is_symlink()
        mirror = t / "mirror"
        mirror.mkdir()
        (mirror / "genome.fa").write_text(">1\nACGT\n")
        fetch("https://example.invalid/genome.fa", t, t / "g.fa", str(mirror))
        assert (t / "g.fa").read_text() == ">1\nACGT\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("reference")
    r.add_argument("--fasta", required=True)
    r.add_argument("--gtf", required=True)
    r.add_argument("--mirror", default="")
    r.add_argument("--out", required=True)
    s = sub.add_parser("reads")
    s.add_argument("--valid", required=True)
    s.add_argument("--samplesheet", required=True, help="the input samplesheet; relative read paths resolve against its folder")
    s.add_argument("--reads", required=True)
    s.add_argument("--runs", required=True)
    s.add_argument("--mirror", default="")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return 0
    if args.cmd == "reference":
        stage_reference(args)
    elif args.cmd == "reads":
        stage_reads(args)
    else:
        ap.error("pick reference, reads or --selftest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
