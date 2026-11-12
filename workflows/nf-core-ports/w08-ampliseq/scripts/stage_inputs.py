#!/usr/bin/env python3
"""
Stage the nf-core/ampliseq inputs: reads, metadata and reference databases.

Reads the samplesheet (``sample``, ``fastq_1``, ``fastq_2`` and the optional
``run``, ``control``, ``quant_reading`` columns, tab or comma separated) and
writes

- ``reads/<id>/<id>_1.fastq.gz``, ``<id>_2.fastq.gz``: the reads under the
  names RENAME_RAW_DATA_FILES gives them;
- ``samples/<id>``: a bash-sourceable meta file (``id``, ``run``);
- ``runs/<run>``: one meta file per sequencing run (``run``, ``samples``),
  the DADA2 error model and denoising unit;
- ``directions/FW``, ``directions/RV``: the read directions DADA2_QUALITY1
  and TRUNCLEN run over;
- ``reference/``: the metadata file, ``decontam_metadata.tsv`` (built as the
  pipeline's collectFile does) and the reference database files.

The pipeline's input checks run here too: paired-end reads only, the sample
name must differ from the read file names, and every read file needs at
least ``--min-read-counts`` reads.

Sources are URLs (``curl -fL`` to ``<name>.part``, then renamed) or local
paths. With ``--mirror DIR``, a file whose name exists anywhere under DIR is
copied from there instead of downloaded.

stdlib only.

Usage:
    stage_inputs.py --samplesheet S --metadata URL --ref URL,URL [--ref URL ...] \\
        --reads reads/ --samples samples/ --runs runs/ --directions directions/ --reference reference/
    stage_inputs.py --selftest
"""

from __future__ import annotations

import argparse
import csv
import gzip
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# assets/schema_input.json; a run also names a file and is sourced in single quotes
ID_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_]+")
RUN_RE = re.compile(r"[^\s/']+")


def find_in_mirror(mirror: str, name: str) -> Path | None:
    if not mirror:
        return None
    for root, _dirs, files in os.walk(mirror):
        if name in files:
            return Path(root) / name
    return None


def fetch(src: str, dest: Path, mirror: str) -> None:
    """Copy *src* (URL or path) to *dest* through ``dest.part``."""
    part = dest.with_name(dest.name + ".part")
    local = find_in_mirror(mirror, src.rsplit("/", 1)[-1]) if "://" in src else Path(src)
    if local is not None:
        shutil.copyfile(local, part)
    else:
        subprocess.run(["curl", "-fsSL", "--retry", "3", "-o", str(part), src], check=True)
    os.replace(part, dest)


def count_fastq(path: Path) -> int:
    opener = gzip.open if path.name.endswith(".gz") else open
    with opener(path, "rb") as fh:
        return sum(1 for _ in fh) // 4


def simple_name(src: str) -> str:
    """Nextflow getSimpleName: file name up to the first dot."""
    return src.rsplit("/", 1)[-1].split(".", 1)[0]


def read_sheet(path: Path) -> list[dict[str, str]]:
    text = path.read_text()
    delim = "\t" if "\t" in text.splitlines()[0] else ","
    return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(text.splitlines(), delimiter=delim)]


def decontam_metadata(rows: list[dict[str, str]]) -> str:
    """The ch_decontam_metadata collectFile: header of the first entry, rows sorted."""
    entries = []
    for r in rows:
        run = r.get("run") or "1"
        if r.get("control") and r.get("quant_reading"):
            entries.append(("sample\tcontrol\tquant_reading\trun", f"{r['sample']}\t{r['control']}\t{r['quant_reading']}\t{run}"))
        elif r.get("control"):
            entries.append(("sample\tcontrol\trun", f"{r['sample']}\t{r['control']}\t{run}"))
        elif r.get("quant_reading"):
            entries.append(("sample\tquant_reading\trun", f"{r['sample']}\t{r['quant_reading']}\t{run}"))
        else:
            entries.append(("empty", ""))
    if all(h == "empty" for h, _line in entries):
        # nf-core drops this file (countLines() > 1), DECONTAM gets nothing and --decontam decontaminate stops
        raise SystemExit("Decontamination removed all features, please adjust settings. (No samplesheet row has control or quant_reading.)")
    header = entries[0][0]
    body = sorted(line + "\n" for _h, line in entries if line)
    return header + "\n" + "".join(body)


def stage(a: argparse.Namespace) -> None:
    rows = read_sheet(Path(a.samplesheet))
    reads, samples, runs, directions, ref = (Path(p) for p in (a.reads, a.samples, a.runs, a.directions, a.reference))
    for d in (reads, samples, runs, directions, ref):
        d.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    by_run: dict[str, list[str]] = {}
    for r in rows:
        sid = r.get("sample", "")
        if not ID_RE.fullmatch(sid) or sid in seen:
            raise SystemExit(f"invalid or repeated sample name {sid!r}: must start with a letter, and can only contain letters, numbers or underscores")
        seen.add(sid)
        if not r.get("fastq_1") or not r.get("fastq_2"):
            raise SystemExit(f"{sid}: fastq_1 and fastq_2 are required (paired-end Illumina)")
        if sid in (simple_name(r["fastq_1"]), simple_name(r["fastq_2"])):
            raise SystemExit(f"{sid}: the sample name must differ from the read file names")
        (reads / sid).mkdir(exist_ok=True)
        for n in (1, 2):
            dest = reads / sid / f"{sid}_{n}.fastq.gz"
            fetch(r[f"fastq_{n}"], dest, a.mirror)
            if count_fastq(dest) < a.min_read_counts:
                raise SystemExit(f"{sid}: {dest.name} has fewer than {a.min_read_counts} reads")
        run = r.get("run") or "1"
        if not RUN_RE.fullmatch(run):
            raise SystemExit(f"{sid}: invalid run name {run!r}: no spaces, '/' or quotes")
        (samples / sid).write_text(f"id='{sid}'\nrun='{run}'\n")
        by_run.setdefault(run, []).append(sid)
    for run, ids in by_run.items():
        (runs / run).write_text(f"run='{run}'\nsamples='{' '.join(ids)}'\n")
    for d in ("FW", "RV"):
        (directions / d).write_text(f"direction={d}\n")
    fetch(a.metadata, ref / a.metadata.rsplit("/", 1)[-1], a.mirror)
    for src in (u for refs in a.ref for u in refs.split(",") if u.strip()):
        fetch(src, ref / src.rsplit("/", 1)[-1], a.mirror)
    (ref / "decontam_metadata.tsv").write_text(decontam_metadata(rows))


def selftest() -> None:
    rows = [
        {"sample": "b", "quant_reading": "5"},
        {"sample": "a", "quant_reading": "7", "run": "2"},
    ]
    assert decontam_metadata(rows) == "sample\tquant_reading\trun\na\t7\t2\nb\t5\t1\n"
    try:
        decontam_metadata([{"sample": "a"}])
        raise AssertionError("no decontam columns must stop")
    except SystemExit:
        pass
    assert ID_RE.fullmatch("sampleID_1a") and not any(ID_RE.fullmatch(x) for x in ("1a", "a.b", "a-b", "a"))
    assert RUN_RE.fullmatch("run_1") and not any(RUN_RE.fullmatch(x) for x in ("a b", "a/b", "a'b", ""))
    assert simple_name("https://x/1a_S103_L001_R1_001.fastq.gz") == "1a_S103_L001_R1_001"
    with tempfile.TemporaryDirectory() as t:
        fq = Path(t) / "r.fastq.gz"
        with gzip.open(fq, "wt") as fh:
            fh.write("@r\nACGT\n+\nIIII\n" * 3)
        assert count_fastq(fq) == 3
        sheet = Path(t) / "s.tsv"
        sheet.write_text(f"sample\tfastq_1\tfastq_2\tquant_reading\nS1\t{fq}\t{fq}\t10\n")
        meta = Path(t) / "Metadata.tsv"
        meta.write_text("ID\tx\nS1\ta\n")
        ns = argparse.Namespace(
            samplesheet=str(sheet), metadata=str(meta), ref=[], mirror="", min_read_counts=1,
            reads=f"{t}/reads", samples=f"{t}/samples", runs=f"{t}/runs", directions=f"{t}/dir", reference=f"{t}/ref",
        )
        stage(ns)
        assert (Path(t) / "reads/S1/S1_2.fastq.gz").exists()
        assert (Path(t) / "runs/1").read_text() == "run='1'\nsamples='S1'\n"
        assert (Path(t) / "samples/S1").read_text() == "id='S1'\nrun='1'\n"
        assert (Path(t) / "ref/decontam_metadata.tsv").read_text() == "sample\tquant_reading\trun\nS1\t10\t1\n"
    print("selftest ok")


def main() -> None:
    if "--selftest" in sys.argv:
        selftest()
        return
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--samplesheet", required=True)
    ap.add_argument("--metadata", required=True)
    ap.add_argument("--ref", action="append", default=[], help="reference database files (URLs or paths), comma separated, repeatable")
    ap.add_argument("--mirror", default="")
    ap.add_argument("--min-read-counts", type=int, default=1)
    for out in ("reads", "samples", "runs", "directions", "reference"):
        ap.add_argument(f"--{out}", required=True)
    stage(ap.parse_args())


if __name__ == "__main__":
    main()
