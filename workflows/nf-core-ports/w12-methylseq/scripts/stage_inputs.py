#!/usr/bin/env python3
"""
Stage the nf-core/methylseq inputs: the genome fasta and per-sample reads.

``reference`` downloads the fasta (or copies it from a local mirror) into one
folder and writes ``refs.env`` with its file name.

``samples`` splits the samplesheet as the pipeline does: rows sharing a
``sample`` are runs of one sample and must agree on endedness. It writes

- ``reads/<id>/``: the reads, plus ``reads.txt`` (R1 then R2). A sample with
  several runs is concatenated here in row order, as CAT_FASTQ does, into
  ``<id>.merged.fastq.gz`` or ``<id>_{1,2}.merged.fastq.gz``;
- ``samples/<id>``: a bash-sourceable meta file (``single_end``).

Sources are URLs (``curl -fL`` to ``<name>.part``, then renamed) or paths
relative to the samplesheet (copied). An absolute local path is symlinked, as
Nextflow stages it. With ``--mirror DIR``, a file whose name exists anywhere
under DIR is copied from there instead of downloaded.

stdlib only.

Usage:
    stage_inputs.py reference --fasta URL --out reference/
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

ID_RE = re.compile(r"\S+")  # schema_input.json: ^\S+$
FQ_RE = re.compile(r"[^\s/]+\.f(ast)?q\.gz")


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
    name = Path(args.fasta).name
    fetch(args.fasta, Path.cwd(), out / name, args.mirror)
    (out / "refs.env").write_text(f"ref_fasta={name}\n")


def group_rows(rows: list[dict[str, str]]) -> dict[str, dict]:
    """groupTuple + validateInputSamplesheet: runs per sample, same endedness."""
    samples: dict[str, dict] = {}
    for row in rows:
        sid = (row.get("sample") or "").strip()
        if not ID_RE.fullmatch(sid):
            raise ValueError(f"invalid sample name {sid!r}: no spaces")
        reads = [r.strip() for r in (row.get("fastq_1") or "", row.get("fastq_2") or "") if r.strip()]
        if not (row.get("fastq_1") or "").strip():
            raise ValueError(f"{sid}: fastq_1 is required")
        for r in reads:
            if not FQ_RE.fullmatch(Path(r).name):
                raise ValueError(f"{sid}: {r} must end in .fq.gz or .fastq.gz")
        samples.setdefault(sid, {"runs": []})["runs"].append(reads)
    for sid, s in samples.items():
        if len({len(r) for r in s["runs"]}) != 1:
            raise ValueError(
                "Please check input samplesheet -> Multiple runs of a sample must be of the same "
                f"datatype i.e. single-end or paired-end: {sid}"
            )
        s["single_end"] = len(s["runs"][0]) == 1
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
        if len(s["runs"]) == 1:
            names = [Path(r).name for r in s["runs"][0]]
            if len(set(names)) != len(names):
                raise ValueError(f"{sid}: R1 and R2 share a file name")
            for src, name in zip(s["runs"][0], names):
                fetch(src, sheet.parent, sdir / name, args.mirror)
        else:
            # CAT_FASTQ: cat <runs' R1> > <id>_1.merged.fastq.gz (gzip members concatenate)
            mates = [[r[0] for r in s["runs"]]] if s["single_end"] else [[r[i] for r in s["runs"]] for i in (0, 1)]
            names = [f"{sid}.merged.fastq.gz"] if s["single_end"] else [f"{sid}_{i}.merged.fastq.gz" for i in (1, 2)]
            for srcs, name in zip(mates, names):
                part = sdir / (name + ".part")
                with open(part, "wb") as out:
                    for i, src in enumerate(srcs):
                        tmp = sdir / f".run{i}.fastq.gz"
                        fetch(src, sheet.parent, tmp, args.mirror)
                        with open(tmp, "rb") as fh:
                            shutil.copyfileobj(fh, out)
                        tmp.unlink()
                os.replace(part, sdir / name)
        (sdir / "reads.txt").write_text("\n".join(names) + "\n")
        (samples_dir / sid).write_text(f"single_end={'true' if s['single_end'] else 'false'}\n")


def selftest() -> None:
    rows = [
        {"sample": "A", "fastq_1": "a1.fq.gz", "fastq_2": "a2.fq.gz"},
        {"sample": "A", "fastq_1": "a3.fq.gz", "fastq_2": "a4.fq.gz"},
        {"sample": "B", "fastq_1": "b1.fastq.gz", "fastq_2": ""},
    ]
    g = group_rows(rows)
    assert g["A"]["runs"] == [["a1.fq.gz", "a2.fq.gz"], ["a3.fq.gz", "a4.fq.gz"]] and not g["A"]["single_end"]
    assert g["B"]["single_end"]
    for bad in (
        [{"sample": "A", "fastq_1": "x.fq.gz", "fastq_2": ""}],
        [{"sample": "bad id", "fastq_1": "x.fq.gz", "fastq_2": ""}],
        [{"sample": "C", "fastq_1": "x.fastq", "fastq_2": ""}],
    ):
        try:
            group_rows(rows + bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad}")
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        for r in rows:
            for k in ("fastq_1", "fastq_2"):
                if r[k]:
                    (t / r[k]).write_text(r[k])
        sheet = t / "sheet.csv"
        with open(sheet, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        stage_samples(argparse.Namespace(samplesheet=sheet, reads=t / "r", samples=t / "s", mirror=""))
        assert (t / "r/A/reads.txt").read_text() == "A_1.merged.fastq.gz\nA_2.merged.fastq.gz\n"
        assert (t / "r/A/A_1.merged.fastq.gz").read_text() == "a1.fq.gza3.fq.gz"
        assert (t / "r/B/reads.txt").read_text() == "b1.fastq.gz\n"
        assert (t / "s/B").read_text() == "single_end=true\n" and (t / "s/A").read_text() == "single_end=false\n"
        assert sorted(p.name for p in (t / "r/A").iterdir()) == ["A_1.merged.fastq.gz", "A_2.merged.fastq.gz", "reads.txt"]
        fetch(str(t / "a1.fq.gz"), t, t / "abs.fq.gz", "")
        assert (t / "abs.fq.gz").is_symlink() and (t / "abs.fq.gz").read_text() == "a1.fq.gz"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("reference")
    r.add_argument("--fasta", required=True)
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
