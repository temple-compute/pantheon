#!/usr/bin/env python3
"""
Stage the nf-core/sarek inputs: reference files and per-lane reads.

``reference`` downloads the genome files (or copies them from a local mirror)
into one folder and writes ``refs.env`` with their file names.

``samples`` splits the samplesheet as sarek's samplesheet_to_channel does for
FASTQ input (mapping step). It writes

- ``reads/<sample>-<lane>/``: the lane's two reads under their original names;
- ``lanes/<sample>-<lane>``: a bash-sourceable meta file (``sample``,
  ``patient``, ``status``, ``sex``, ``fastq_1``, ``fastq_2``, ``read_group``);
- ``samples/<sample>``: the per-sample meta file (``patient``, ``status``,
  ``sex``, ``lanes``), one per sample, for the steps after MarkDuplicates.

The read group is addReadgroupToMeta from workflows/sarek.nf: the flowcell
from the first FASTQ header (5 fields: instrument; 7 or more: field 3), and
``DS`` is the ``--fasta`` value as given.

Sources are URLs (``curl -fL`` to ``<name>.part``, then renamed) or paths
relative to the samplesheet (copied). An absolute local path is symlinked, as
Nextflow stages it. With ``--mirror DIR``, a file whose name exists anywhere
under DIR is copied from there instead of downloaded.

Only the route the test profile runs is supported: paired FASTQ rows of
normal samples (status 0). Other rows stop the run with an error.

stdlib only.

Usage:
    stage_inputs.py reference --fasta URL --fasta_fai URL ... --out reference/
    stage_inputs.py samples --samplesheet sheet.csv --fasta URL --reads reads/ --lanes lanes/ --samples samples/
    stage_inputs.py --selftest
"""

from __future__ import annotations

import argparse
import csv
import gzip
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ID_RE = re.compile(r"[A-Za-z0-9._-]+")
REFS = ["fasta", "fasta_fai", "dict", "intervals", "dbsnp", "dbsnp_tbi", "known_indels", "known_indels_tbi"]


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


def write_meta(path: Path, meta: dict[str, str]) -> None:
    path.write_text("".join(f"{k}={shlex.quote(v)}\n" for k, v in meta.items()))


# -- reference ----------------------------------------------------------------


def cmd_reference(a: argparse.Namespace) -> None:
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    env = []
    for key in REFS:
        src = getattr(a, key)
        name = Path(src).name
        fetch(src, Path.cwd(), out / name, a.mirror)
        env.append(f"ref_{key}={shlex.quote(name)}\n")
    (out / "refs.env").write_text("".join(env))


# -- samples ------------------------------------------------------------------


def first_line(path: Path) -> str:
    try:
        with gzip.open(path, "rt", encoding="ascii") as fh:
            return fh.readline().rstrip("\n")
    except (OSError, UnicodeDecodeError):
        return ""  # sarek logs a warning and goes on without a flowcell


def flowcell(path: Path) -> str | None:
    """flowcellLaneFromFastq: Groovy split(':') drops trailing empty fields."""
    line = first_line(path)
    fields = line.split(":") if line else []
    while fields and fields[-1] == "":
        fields.pop()
    if len(fields) == 5:
        return fields[0][1:]
    if len(fields) >= 7:
        return fields[2]
    return None


def read_group(meta: dict[str, str], fc: str | None, fasta: str, platform: str, center: str) -> tuple[str, str]:
    lane_id = f"{fc}.{meta['sample']}.{meta['lane']}" if fc else f"{meta['sample']}.{meta['lane']}"
    cn = f"CN:{center}\\t" if center else ""
    rg = (
        f"@RG\\tID:{lane_id}\\t{cn}PU:{meta['lane']}\\tSM:{meta['patient']}_{meta['sample']}"
        f"\\tLB:{meta['sample']}\\tDS:{fasta}\\tPL:{platform}"
    )
    return rg, lane_id


def read_rows(samplesheet: Path) -> list[dict[str, str]]:
    with open(samplesheet, newline="") as fh:
        rows = [{k.strip(): (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(fh)]
    if not rows:
        sys.exit("samplesheet has no rows")
    for i, r in enumerate(rows, 2):
        for col in ("patient", "sample", "lane", "fastq_1", "fastq_2"):
            if not r.get(col):
                sys.exit(f"samplesheet line {i}: '{col}' is required (only paired FASTQ input is ported)")
        for col in ("patient", "sample", "lane"):
            if not ID_RE.fullmatch(r[col]):
                sys.exit(f"samplesheet line {i}: {col} '{r[col]}' may only hold letters, digits, '.', '_' and '-'")
        r["status"] = r.get("status") or "0"
        r["sex"] = r.get("sex") or "NA"
        if r["status"] != "0":
            sys.exit(f"samplesheet line {i}: status {r['status']}: tumor samples need the somatic route, which is not ported")
    return rows


def cmd_samples(a: argparse.Namespace) -> None:
    sheet = Path(a.samplesheet)
    rows = read_rows(sheet)
    reads, lanes, samples = Path(a.reads), Path(a.lanes), Path(a.samples)
    for d in (reads, lanes, samples):
        d.mkdir(parents=True, exist_ok=True)
    patients: dict[str, str] = {}
    per_sample: dict[str, list[str]] = {}
    for r in rows:
        if patients.setdefault(r["sample"], r["patient"]) != r["patient"]:
            sys.exit(f"Sample ID '{r['sample']}' is associated with multiple patient IDs")
        lid = f"{r['sample']}-{r['lane']}"
        if lid in per_sample.get(r["sample"], []):
            sys.exit(f"sample {r['sample']} lists lane {r['lane']} twice")
        d = reads / lid
        d.mkdir(exist_ok=True)
        names = []
        for col in ("fastq_1", "fastq_2"):
            name = Path(r[col]).name
            fetch(r[col], sheet.parent, d / name, a.mirror)
            names.append(name)
        fc1, fc2 = flowcell(d / names[0]), flowcell(d / names[1])
        if fc1 and fc1 != fc2:
            sys.exit(f"Flowcell ID does not match for paired reads of sample {lid}")
        rg, _ = read_group(r, fc1, a.fasta, a.seq_platform, a.seq_center)
        meta = {k: r[k] for k in ("sample", "patient", "status", "sex")}
        write_meta(lanes / lid, meta | {"fastq_1": names[0], "fastq_2": names[1], "read_group": rg})
        per_sample.setdefault(r["sample"], []).append(lid)
    for sid, lids in per_sample.items():
        r = next(x for x in rows if x["sample"] == sid)
        write_meta(samples / sid, {k: r[k] for k in ("patient", "status", "sex")} | {"lanes": " ".join(lids)})


# -- selftest -----------------------------------------------------------------


def selftest() -> None:
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        for name, header in (("a_1.fq.gz", "@normal#21#998579#1/1"), ("a_2.fq.gz", "@normal#21#998579#1/2"),
                             ("b_1.fq.gz", "@M1:7:FC9:2:1:1:1 1:N"), ("b_2.fq.gz", "@M1:7:FC9:2:1:1:1 2:N")):
            with gzip.open(t / name, "wt") as fh:
                fh.write(f"{header}\nACGT\n+\nIIII\n")
        assert flowcell(t / "a_1.fq.gz") is None
        assert flowcell(t / "b_1.fq.gz") == "FC9"
        (t / "s.csv").write_text(
            "patient,sex,status,sample,lane,fastq_1,fastq_2\n"
            "p,XX,0,s,L1,a_1.fq.gz,a_2.fq.gz\n"
            "p,XX,0,s,L2,b_1.fq.gz,b_2.fq.gz\n"
        )
        ns = argparse.Namespace(samplesheet=str(t / "s.csv"), fasta="https://x//genome.fasta", seq_platform="ILLUMINA",
                                seq_center="", mirror="", reads=str(t / "r"), lanes=str(t / "l"), samples=str(t / "m"))
        cmd_samples(ns)
        env = subprocess.run(["bash", "-c", f". {t}/l/s-L1; printf %s \"$read_group\""], capture_output=True, text=True).stdout
        assert env == r"@RG\tID:s.L1\tPU:L1\tSM:p_s\tLB:s\tDS:https://x//genome.fasta\tPL:ILLUMINA", env
        assert "ID:FC9.s.L2" in (t / "l/s-L2").read_text()
        assert (t / "m/s").read_text().splitlines()[-1] == "lanes='s-L1 s-L2'"
        assert (t / "r/s-L2/b_2.fq.gz").exists()
    print("selftest ok")  # noqa: T201


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("reference")
    for key in REFS:
        r.add_argument(f"--{key}", required=True)
    r.add_argument("--mirror", default="")
    r.add_argument("--out", required=True)
    s = sub.add_parser("samples")
    s.add_argument("--samplesheet", required=True)
    s.add_argument("--fasta", required=True, help="the --fasta value, written to the read group DS tag")
    s.add_argument("--seq_platform", default="ILLUMINA")
    s.add_argument("--seq_center", default="")
    s.add_argument("--mirror", default="")
    s.add_argument("--reads", required=True)
    s.add_argument("--lanes", required=True)
    s.add_argument("--samples", required=True)
    a = ap.parse_args()
    if a.selftest:
        selftest()
    elif a.cmd == "reference":
        cmd_reference(a)
    elif a.cmd == "samples":
        cmd_samples(a)
    else:
        ap.error("pick reference, samples or --selftest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
