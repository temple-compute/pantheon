#!/usr/bin/env python3
"""
Stage the nf-core/viralrecon inputs: reference files and per-sample reads.

``reference`` downloads the genome fasta and GFF, the primer BED, the
Kraken2 database and the Nextclade dataset (or copies them from a local
mirror) into one folder and writes ``refs.env`` with their file names.

``samples`` splits the samplesheet as the pipeline does: rows sharing a
``sample`` are runs of one sample and must all be single-end or all
paired-end. It writes

- ``reads/<id>/``: the reads under their original names, plus ``reads.txt``
  (row order, R1 then R2 per row);
- ``samples/<id>``: a bash-sourceable meta file (``single_end``).

Sources are URLs (``curl -fL`` to ``<name>.part``, then renamed) or paths
relative to the samplesheet (copied). An absolute local path is symlinked, as
Nextflow stages it. With ``--mirror DIR``, a file whose name exists anywhere
under DIR is copied from there instead of downloaded.

stdlib only.

Usage:
    stage_inputs.py reference --fasta URL --gff URL --primer_bed URL --kraken2_db URL --nextclade_dataset URL --out reference/
    stage_inputs.py samples --samplesheet sheet.csv --reads reads/ --samples samples/
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
REFERENCE = ("fasta", "gff", "primer_bed", "kraken2_db", "nextclade_dataset")


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
    for key in REFERENCE:
        src = getattr(args, key)
        name = Path(src).name
        fetch(src, Path.cwd(), out / name, args.mirror)
        env[f"ref_{key}"] = name
    (out / "refs.env").write_text("".join(f"{k}={v}\n" for k, v in env.items()))


def group_rows(rows: list[dict[str, str]]) -> dict[str, dict]:
    """Merge runs per sample; all runs of a sample must share endedness."""
    samples: dict[str, dict] = {}
    for row in rows:
        sid = (row.get("sample") or "").strip()
        if not ID_RE.fullmatch(sid):
            raise ValueError(f"invalid sample name {sid!r}: use letters, digits, '.', '_' or '-'")
        if not (row.get("fastq_1") or "").strip():
            raise ValueError(f"{sid}: fastq_1 is required")
        reads = [r.strip() for r in (row.get("fastq_1") or "", row.get("fastq_2") or "") if r.strip()]
        s = samples.setdefault(sid, {"reads": [], "single_end": len(reads) == 1})
        if s["single_end"] != (len(reads) == 1):
            raise ValueError(f"Multiple runs of a sample must be of the same datatype i.e. single-end or paired-end: {sid}")
        s["reads"].extend(reads)
    return samples


def stage_samples(args: argparse.Namespace) -> None:
    sheet = Path(args.samplesheet)
    with open(sheet, newline="") as fh:
        samples = group_rows(list(csv.DictReader(fh)))
    reads_dir, samples_dir = Path(args.reads), Path(args.samples)
    for d in (reads_dir, samples_dir):
        d.mkdir(parents=True, exist_ok=True)
    for sid, s in samples.items():
        sdir = reads_dir / sid
        sdir.mkdir(exist_ok=True)
        names = [Path(r).name for r in s["reads"]]
        if len(set(names)) != len(names):
            raise ValueError(f"{sid}: two reads share a file name")
        for src, name in zip(s["reads"], names):
            fetch(src, sheet.parent, sdir / name, args.mirror)
        (sdir / "reads.txt").write_text("\n".join(names) + "\n")
        (samples_dir / sid).write_text(f"single_end={'true' if s['single_end'] else 'false'}\n")


def selftest() -> None:
    rows = [
        {"sample": "A", "fastq_1": "a1.fq.gz", "fastq_2": "a2.fq.gz"},
        {"sample": "B", "fastq_1": "b1.fq.gz", "fastq_2": ""},
        {"sample": "B", "fastq_1": "b2.fq.gz", "fastq_2": ""},
    ]
    g = group_rows(rows)
    assert g["A"] == {"reads": ["a1.fq.gz", "a2.fq.gz"], "single_end": False}
    assert g["B"] == {"reads": ["b1.fq.gz", "b2.fq.gz"], "single_end": True}
    for bad in ([{"sample": "B", "fastq_1": "x.fq.gz", "fastq_2": "y.fq.gz"}], [{"sample": "a b", "fastq_1": "x", "fastq_2": ""}]):
        try:
            group_rows(rows + bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad}")
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        for name in ("a1.fq.gz", "a2.fq.gz", "b1.fq.gz", "b2.fq.gz"):
            (t / name).write_text(name)
        sheet = t / "sheet.csv"
        with open(sheet, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        stage_samples(argparse.Namespace(samplesheet=sheet, reads=t / "r", samples=t / "s", mirror=""))
        assert (t / "r/B/reads.txt").read_text() == "b1.fq.gz\nb2.fq.gz\n"
        assert (t / "s/A").read_text() == "single_end=false\n"
        fetch(str(t / "a1.fq.gz"), t, t / "abs.fq.gz", "")
        assert (t / "abs.fq.gz").is_symlink()
        (t / "m").mkdir()
        (t / "m/ref.fa.gz").write_text("mirror")
        fetch("https://example.invalid/x/ref.fa.gz", t, t / "ref.fa.gz", str(t / "m"))
        assert (t / "ref.fa.gz").read_text() == "mirror"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("reference")
    for key in REFERENCE:
        r.add_argument(f"--{key}", required=True)
    r.add_argument("--mirror", default="")
    r.add_argument("--out", required=True)
    s = sub.add_parser("samples")
    s.add_argument("--samplesheet", required=True)
    s.add_argument("--reads", required=True)
    s.add_argument("--samples", required=True)
    s.add_argument("--mirror", default="")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return 0
    if args.cmd == "reference":
        stage_reference(args)
    elif args.cmd == "samples":
        stage_samples(args)
    else:
        ap.error("pick reference, samples or --selftest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
