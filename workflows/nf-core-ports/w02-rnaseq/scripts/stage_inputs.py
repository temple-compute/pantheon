#!/usr/bin/env python3
"""
Stage the nf-core/rnaseq inputs: reference files and per-sample reads.

``reference`` downloads the genome files (or copies them from a local
mirror) into one folder and writes ``refs.env``, the file names plus the
parameter-derived switches the pipeline computes in Groovy before any
process runs (biotype QC on or off).

``samples`` splits the samplesheet as the pipeline does: rows sharing a
``sample`` are runs of one sample and must agree on strandedness, endedness
and compression. It writes

- ``reads/<id>/``: the reads under their original names, plus ``reads.txt``
  (row order, R1 then R2 per row);
- ``samples/<id>``: a bash-sourceable meta file (``single_end``,
  ``strandedness``, ``merged``);
- ``multi_run/<id>``: the same meta file, only for samples that CAT_FASTQ
  merges (several runs, or uncompressed reads).

Sources are URLs (``curl -fL`` to ``<name>.part``, then renamed) or paths
relative to the samplesheet (copied). An absolute local path is symlinked, as
Nextflow stages it. With ``--mirror DIR``, a file whose name exists anywhere
under DIR is copied from there instead of downloaded.

stdlib only.

Usage:
    stage_inputs.py reference --fasta URL --gtf URL ... --out reference/
    stage_inputs.py samples --samplesheet sheet.csv --reads reads/ --samples samples/ --multi-run multi_run/
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

ID_RE = re.compile(r"[A-Za-z0-9._-]+")
STRANDEDNESS = {"forward", "reverse", "unstranded", "auto"}


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


# -- reference ----------------------------------------------------------------


def biotype_qc_usable(gtf: Path, biotype: str = "gene_biotype", feature: str = "exon") -> bool:
    """utils_nfcore_rnaseq_pipeline biotypeQcUsable: biotype set on <feature> rows."""
    opener = gzip.open if gtf.name.endswith(".gz") else open
    with opener(gtf, "rt") as fh:
        for line in fh:
            fields = line.rstrip("\n").split("\t")
            if len(fields) > 2 and fields[2] == feature and biotype in fields[-1].split():
                return True
    return False


def stage_reference(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    names = {}
    for key in ("fasta", "gtf", "transcript_fasta", "additional_fasta", "salmon_index", "bbsplit_fasta_list"):
        src = getattr(args, key)
        name = Path(src).name
        fetch(src, Path.cwd(), out / name, args.mirror)
        names[key] = name
    # bbsplit_fasta_list rows are "<name>,<fasta>"; stage each fasta and
    # rewrite the list with the local file names.
    rows = []
    for line in (out / names["bbsplit_fasta_list"]).read_text().splitlines():
        if not line.strip():
            continue
        ref_name, src = (x.strip() for x in line.split(",", 1))
        fetch(src, Path.cwd(), out / Path(src).name, args.mirror)
        rows.append(f"{ref_name},{Path(src).name}")
    (out / "bbsplit_fasta_list.local.txt").write_text("\n".join(rows) + "\n")
    env = {f"ref_{k}": v for k, v in names.items()}
    env["ref_bbsplit_fasta_list"] = "bbsplit_fasta_list.local.txt"
    env["biotype_qc"] = "true" if biotype_qc_usable(out / names["gtf"]) else "false"
    (out / "refs.env").write_text("".join(f"{k}={v}\n" for k, v in env.items()))


# -- samples ------------------------------------------------------------------


def group_rows(rows: list[dict[str, str]]) -> dict[str, dict]:
    """checkSamplesAfterGrouping: merge runs per sample and validate them."""
    samples: dict[str, dict] = {}
    for row in rows:
        sid = (row.get("sample") or "").strip()
        if not ID_RE.fullmatch(sid):
            raise ValueError(f"invalid sample name {sid!r}: use letters, digits, '.', '_' or '-'")
        reads = [r.strip() for r in (row.get("fastq_1") or "", row.get("fastq_2") or "") if r.strip()]
        if not reads or not (row.get("fastq_1") or "").strip():
            raise ValueError(f"{sid}: fastq_1 is required")
        strand = (row.get("strandedness") or "auto").strip()
        if strand not in STRANDEDNESS:
            raise ValueError(f"{sid}: strandedness must be one of {sorted(STRANDEDNESS)}")
        run = {"reads": reads, "single_end": len(reads) == 1, "strandedness": strand}
        s = samples.setdefault(sid, {"runs": []})
        s["runs"].append(run)
    for sid, s in samples.items():
        runs = s["runs"]
        for key, what in (("strandedness", "strandedness"), ("single_end", "datatype i.e. single-end or paired-end")):
            if len({r[key] for r in runs}) != 1:
                raise ValueError(f"Multiple runs of a sample must have the same {what}!: {sid}")
        if len({f.endswith(".gz") for r in runs for f in r["reads"]}) != 1:
            raise ValueError(f"Multiple runs of a sample must not mix compressed and uncompressed FASTQ files: {sid}")
        s["single_end"] = runs[0]["single_end"]
        s["strandedness"] = runs[0]["strandedness"]
        s["reads"] = [f for r in runs for f in r["reads"]]
        # QTF: single-run gzipped samples skip CAT_FASTQ.
        s["merged"] = len(runs) > 1 or not s["reads"][0].endswith(".gz")
    return samples


def meta_text(sid: str, s: dict) -> str:
    return (
        f"single_end={'true' if s['single_end'] else 'false'}\n"
        f"strandedness={s['strandedness']}\n"
        f"merged={'true' if s['merged'] else 'false'}\n"
    )


def stage_samples(args: argparse.Namespace) -> None:
    sheet = Path(args.samplesheet)
    with open(sheet, newline="") as fh:
        samples = group_rows(list(csv.DictReader(fh)))
    reads_dir, samples_dir, multi_dir = Path(args.reads), Path(args.samples), Path(args.multi_run)
    for d in (reads_dir, samples_dir, multi_dir):
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
        (samples_dir / sid).write_text(meta_text(sid, s))
        if s["merged"]:
            (multi_dir / sid).write_text(meta_text(sid, s))


# -- selftest -----------------------------------------------------------------


def selftest() -> None:
    rows = [
        {"sample": "A", "fastq_1": "a1.fq.gz", "fastq_2": "a2.fq.gz", "strandedness": "auto"},
        {"sample": "A", "fastq_1": "a3.fq.gz", "fastq_2": "a4.fq.gz", "strandedness": "auto"},
        {"sample": "B", "fastq_1": "b1.fq.gz", "fastq_2": "", "strandedness": "reverse"},
        {"sample": "C", "fastq_1": "c1.fq.gz", "fastq_2": "c2.fq.gz", "strandedness": "forward"},
    ]
    g = group_rows(rows)
    assert g["A"]["reads"] == ["a1.fq.gz", "a2.fq.gz", "a3.fq.gz", "a4.fq.gz"] and g["A"]["merged"]
    assert not g["B"]["merged"] and g["B"]["single_end"] and not g["C"]["merged"]
    for bad in (
        [{"sample": "B", "fastq_1": "x.fq.gz", "fastq_2": "y.fq.gz", "strandedness": "reverse"}],
        [{"sample": "B", "fastq_1": "x.fq.gz", "fastq_2": "", "strandedness": "forward"}],
        [{"sample": "bad id", "fastq_1": "x.fq.gz", "fastq_2": "", "strandedness": "auto"}],
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
        ns = argparse.Namespace(samplesheet=sheet, reads=t / "r", samples=t / "s", multi_run=t / "m", mirror="")
        stage_samples(ns)
        assert (t / "r/A/reads.txt").read_text() == "a1.fq.gz\na2.fq.gz\na3.fq.gz\na4.fq.gz\n"
        assert sorted(p.name for p in (t / "m").iterdir()) == ["A"]
        assert "strandedness=reverse" in (t / "s/B").read_text()
        assert not (t / "r/A/a1.fq.gz").is_symlink()
        fetch(str(t / "a1.fq.gz"), t, t / "abs.fq.gz", "")
        assert (t / "abs.fq.gz").is_symlink() and (t / "abs.fq.gz").read_text() == "a1.fq.gz"
        gtf = t / "g.gtf"
        gtf.write_text('1\tx\texon\t1\t9\t.\t+\t.\tgene_id "g"; gene_biotype "pc";\n')
        assert biotype_qc_usable(gtf) and not biotype_qc_usable(gtf, "gene_type")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("reference")
    for key in ("fasta", "gtf", "transcript_fasta", "additional_fasta", "salmon_index", "bbsplit_fasta_list"):
        r.add_argument(f"--{key}", required=True)
    r.add_argument("--mirror", default="")
    r.add_argument("--out", required=True)
    s = sub.add_parser("samples")
    s.add_argument("--samplesheet", required=True)
    s.add_argument("--reads", required=True)
    s.add_argument("--samples", required=True)
    s.add_argument("--multi-run", dest="multi_run", required=True)
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
