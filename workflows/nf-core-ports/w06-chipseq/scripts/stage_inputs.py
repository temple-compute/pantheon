#!/usr/bin/env python3
"""
Stage the nf-core/chipseq inputs: reference files and per-library reads.

``reference`` downloads the genome fasta and GTF (or copies them from a local
mirror) into one folder and writes ``refs.env`` with their file names.

``samples`` reads the checked samplesheet (``samplesheet.valid.csv`` from
check_samplesheet.py, one row per library ``<sample>_REP<n>_T<m>``) and
writes

- ``reads/<lib>/``: the library's reads under their original names, plus
  ``reads.txt`` (R1 then R2);
- ``libs/<lib>``: a bash-sourceable meta file (``single_end``, ``sample``,
  the merged sample id the pipeline gets with ``id - ~/_T\\d+$/``);
- ``samples/<sample>``: one meta file per merged sample (``single_end``,
  ``antibody``, ``control``, ``libs``);
- ``ips/<sample>``: the same, only for samples with a control (IP samples).

Sources are URLs (``curl -fL`` to ``<name>.part``, then renamed) or paths
relative to the folder of the original samplesheet (``--origin``). With ``--mirror DIR``, a file whose
name exists anywhere under DIR is copied from there instead of downloaded.

stdlib only.

Usage:
    stage_inputs.py reference --fasta URL --gtf URL --out reference/
    stage_inputs.py samples --samplesheet samplesheet.valid.csv --origin samplesheet.csv \\
        --reads reads/ --libs libs/ --samples samples/ --ips ips/
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

LIB_RE = re.compile(r"_T\d+$")


def find_in_mirror(mirror: str, name: str) -> Path | None:
    if not mirror:
        return None
    for root, _dirs, files in os.walk(mirror):
        if name in files:
            return Path(root) / name
    return None


def fetch(src: str, base: Path, dest: Path, mirror: str) -> None:
    """Copy *src* (URL or path) to *dest* through ``dest.part``."""
    part = dest.with_name(dest.name + ".part")
    local = find_in_mirror(mirror, Path(src).name) if "://" in src else base / src
    if local is not None:
        shutil.copyfile(local, part)
    else:
        subprocess.run(["curl", "-fsSL", "--retry", "3", "-o", str(part), src], check=True)
    os.replace(part, dest)


def stage_reference(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    env = {}
    for key in ("fasta", "gtf"):
        src = getattr(args, key)
        name = Path(src).name
        if name.endswith(".gz"):
            # shortcut: the test route has plain files; GUNZIP_* is not ported.
            raise SystemExit(f"--{key}: gzipped references are not supported, pass the plain file")
        fetch(src, Path.cwd(), out / name, args.mirror)
        env[f"ref_{key}"] = name
    (out / "refs.env").write_text("".join(f"{k}={v}\n" for k, v in env.items()))


def group_rows(rows: list[dict[str, str]]) -> tuple[dict, dict]:
    """Libraries and merged samples, as INPUT_CHECK and the merge groupTuple build them."""
    libs: dict[str, dict] = {}
    samples: dict[str, dict] = {}
    for row in rows:
        lib = row["sample"]
        reads = [r for r in (row["fastq_1"], row["fastq_2"]) if r]
        single_end = row["single_end"] == "1"
        sid = LIB_RE.sub("", lib)
        libs[lib] = {"reads": reads, "single_end": single_end, "sample": sid}
        s = samples.setdefault(
            sid, {"single_end": single_end, "antibody": row["antibody"], "control": row["control"], "libs": []}
        )
        if (s["single_end"], s["antibody"], s["control"]) != (single_end, row["antibody"], row["control"]):
            raise ValueError(f"{sid}: libraries differ in endedness, antibody or control")
        s["libs"].append(lib)
    return libs, samples


def meta_text(fields: dict) -> str:
    out = []
    for k, v in fields.items():
        if isinstance(v, bool):
            v = "true" if v else "false"
        elif isinstance(v, list):
            v = '"' + " ".join(v) + '"'
        out.append(f"{k}={v}\n")
    return "".join(out)


def stage_samples(args: argparse.Namespace) -> None:
    with open(args.samplesheet, newline="") as fh:
        libs, samples = group_rows(list(csv.DictReader(fh)))
    dirs = {k: Path(getattr(args, k)) for k in ("reads", "libs", "samples", "ips")}
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    for lib, m in libs.items():
        ldir = dirs["reads"] / lib
        ldir.mkdir(exist_ok=True)
        names = [Path(r).name for r in m["reads"]]
        if len(set(names)) != len(names):
            raise ValueError(f"{lib}: two reads share a file name")
        for src, name in zip(m["reads"], names):
            fetch(src, Path(args.origin).parent, ldir / name, args.mirror)
        (ldir / "reads.txt").write_text("\n".join(names) + "\n")
        (dirs["libs"] / lib).write_text(meta_text({"single_end": m["single_end"], "sample": m["sample"]}))
    for sid, s in samples.items():
        text = meta_text(s)
        (dirs["samples"] / sid).write_text(text)
        if s["control"]:
            if s["control"] not in samples:
                raise ValueError(f"{sid}: control {s['control']} is not a sample")
            (dirs["ips"] / sid).write_text(text)


def selftest() -> None:
    rows = [
        {"sample": "IN_REP1_T1", "single_end": "0", "fastq_1": "i1.fq.gz", "fastq_2": "i2.fq.gz", "replicate": "1", "antibody": "", "control": ""},
        {"sample": "A_REP1_T1", "single_end": "0", "fastq_1": "a1.fq.gz", "fastq_2": "a2.fq.gz", "replicate": "1", "antibody": "X", "control": "IN_REP1"},
        {"sample": "A_REP1_T2", "single_end": "0", "fastq_1": "a3.fq.gz", "fastq_2": "a4.fq.gz", "replicate": "1", "antibody": "X", "control": "IN_REP1"},
    ]
    libs, samples = group_rows(rows)
    assert libs["A_REP1_T2"]["sample"] == "A_REP1" and samples["A_REP1"]["libs"] == ["A_REP1_T1", "A_REP1_T2"]
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        for r in rows:
            for k in ("fastq_1", "fastq_2"):
                (t / r[k]).write_text(r[k])
        sheet = t / "valid.csv"
        with open(sheet, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        ns = argparse.Namespace(samplesheet=sheet, origin=sheet, mirror="", reads=t / "r", libs=t / "l", samples=t / "s", ips=t / "i")
        stage_samples(ns)
        assert (t / "r/A_REP1_T2/reads.txt").read_text() == "a3.fq.gz\na4.fq.gz\n"
        assert sorted(p.name for p in (t / "i").iterdir()) == ["A_REP1"]
        assert 'libs="A_REP1_T1 A_REP1_T2"' in (t / "s/A_REP1").read_text()
        assert "sample=IN_REP1" in (t / "l/IN_REP1_T1").read_text()
        bad = rows + [dict(rows[1], sample="B_REP1_T1", control="NOPE_REP1")]
        with open(sheet, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(bad)
        try:
            stage_samples(ns)
        except ValueError:
            pass
        else:
            raise AssertionError("unknown control accepted")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("reference")
    r.add_argument("--fasta", required=True)
    r.add_argument("--gtf", required=True)
    r.add_argument("--mirror", default="")
    r.add_argument("--out", required=True)
    s = sub.add_parser("samples")
    for key in ("samplesheet", "origin", "reads", "libs", "samples", "ips"):
        s.add_argument(f"--{key}", required=True)
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
