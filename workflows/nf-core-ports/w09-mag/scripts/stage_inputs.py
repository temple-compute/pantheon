#!/usr/bin/env python3
"""
Stage the nf-core/mag inputs: per-run reads, sample, assembly and alignment
lists, and the databases.

``samples`` splits the samplesheet (``sample,run,group,short_reads_platform,
short_reads_1,short_reads_2,long_reads``) as the pipeline does for short
paired reads, and writes bash-sourceable meta files named by id:

- ``reads/<id>_run<run>/``: the run's reads under their original names;
- ``runs/<id>_run<run>``: ``id``, ``run``, ``group``, ``r1``, ``r2``;
- ``samples/<id>``: ``id``, ``group``, ``merged`` and ``runs`` (row order);
- ``multi_run/<id>``: the same, only for samples CAT_FASTQ merges (2+ runs);
- ``assemblies/<assembler>-<id>``: MEGAHIT contigs and SPAdes scaffolds;
- ``aligns/<assembler>-<id>-<reads id>``: each assembly against every sample
  of its group (``--binning_map_mode group``).

``databases`` fetches the BUSCO, CAT and GTDB-Tk archives into one folder.

Sources are URLs (``curl -fL`` to ``<name>.part``, then renamed) or paths
relative to the samplesheet (copied). With ``--mirror DIR``, a file whose name
exists anywhere under DIR is copied from there instead of downloaded.

stdlib only.

Usage:
    stage_inputs.py samples --samplesheet sheet.csv --reads reads/ --runs runs/ \\
        --samples samples/ --multi-run multi_run/ --assemblies assemblies/ --aligns aligns/
    stage_inputs.py databases --out dbs/ URL [URL ...]
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
# the schema's short_reads_1/2 pattern; no quote, as names end up in single-quoted meta lines
READS_RE = re.compile(r"[^\s']+\.f(ast)?q\.gz")
# MEGAHIT keeps contigs, SPAdes scaffolds (--spades_downstreaminput scaffolds).
ASSEMBLERS = (("MEGAHIT", "contigs"), ("SPAdes", "scaffolds"))


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


def fresh(folder: Path) -> Path:
    """An empty output folder: a forced rerun must not keep the last run's items."""
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    return folder


def write_meta(path: Path, meta: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{k}='{v}'\n" for k, v in meta.items()))


def parse_rows(rows: list[dict[str, str]]) -> dict[str, dict]:
    """Validate the rows and group the runs per sample, in row order."""
    samples: dict[str, dict] = {}
    seen = set()
    for row in rows:
        get = lambda k: (row.get(k) or "").strip()  # noqa: E731
        sid, run, group = get("sample"), get("run") or "0", get("group") or "0"
        if not ID_RE.fullmatch(sid):
            raise ValueError(f"invalid sample name {sid!r}: use letters, digits, '.', '_' or '-'")
        if not ID_RE.fullmatch(run) or not ID_RE.fullmatch(group):
            raise ValueError(f"{sid}: invalid run {run!r} or group {group!r}")
        if (sid, run) in seen:
            raise ValueError(f"{sid}: run {run} is listed twice")
        seen.add((sid, run))
        r1, r2 = get("short_reads_1"), get("short_reads_2")
        if not r1 or not r2:
            raise ValueError(f"{sid}: this port runs paired short reads only (short_reads_1 and short_reads_2)")
        for r in (r1, r2):
            if not READS_RE.fullmatch(r):
                raise ValueError(f"{sid}: {r!r} must be a .fastq.gz or .fq.gz path or URL without spaces or quotes")
        if get("long_reads"):
            raise ValueError(f"{sid}: long reads are not part of this port")
        s = samples.setdefault(sid, {"group": group, "runs": []})
        if s["group"] != group:
            raise ValueError(f"{sid}: all runs of a sample must be in the same group")
        s["runs"].append({"run": run, "reads": [r1, r2]})
    return samples


def stage_samples(args: argparse.Namespace) -> None:
    sheet = Path(args.samplesheet)
    with open(sheet, newline="") as fh:
        samples = parse_rows(list(csv.DictReader(fh)))
    if not samples:
        raise ValueError("the samplesheet has no rows")
    out = {k: Path(getattr(args, k)) for k in ("reads", "runs", "samples", "multi_run", "assemblies", "aligns")}
    for d in out.values():
        fresh(d)
    for sid, s in samples.items():
        run_ids = []
        for r in s["runs"]:
            rid = f"{sid}_run{r['run']}"
            run_ids.append(rid)
            names = []
            for src in r["reads"]:
                (out["reads"] / rid).mkdir(exist_ok=True)
                name = Path(src).name
                fetch(src, sheet.parent, out["reads"] / rid / name, args.mirror)
                names.append(name)
            write_meta(out["runs"] / rid, {"id": sid, "run": r["run"], "group": s["group"], "r1": names[0], "r2": names[1]})
        meta = {"id": sid, "group": s["group"], "merged": "true" if len(run_ids) > 1 else "false", "runs": " ".join(run_ids)}
        write_meta(out["samples"] / sid, meta)
        if len(run_ids) > 1:
            write_meta(out["multi_run"] / sid, meta)
    for assembler, ext in ASSEMBLERS:
        for sid, s in samples.items():
            aid = f"{assembler}-{sid}"
            write_meta(out["assemblies"] / aid, {"assembler": assembler, "id": sid, "group": s["group"], "ext": ext})
            for rid, r in samples.items():
                if r["group"] == s["group"]:
                    write_meta(out["aligns"] / f"{aid}-{rid}", {"assembler": assembler, "id": sid, "ext": ext, "reads_id": rid})


def stage_databases(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for src in args.urls:
        fetch(src, Path.cwd(), out / Path(src).name, args.mirror)


def selftest() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t / "a_R1.fq.gz").write_bytes(b"x")
        (t / "a_R2.fq.gz").write_bytes(b"y")
        (t / "b_R1.fq.gz").write_bytes(b"z")
        (t / "b_R2.fq.gz").write_bytes(b"w")
        (t / "s.csv").write_text(
            "sample,run,group,short_reads_platform,short_reads_1,short_reads_2,long_reads\n"
            "a,1,0,ILLUMINA,a_R1.fq.gz,a_R2.fq.gz,\n"
            "a,2,0,ILLUMINA,a_R1.fq.gz,a_R2.fq.gz,\n"
            "b,0,1,ILLUMINA,b_R1.fq.gz,b_R2.fq.gz,\n"
        )
        ns = argparse.Namespace(samplesheet=str(t / "s.csv"), mirror="", **{k: str(t / k) for k in ("reads", "runs", "samples", "multi_run", "assemblies", "aligns")})
        stage_samples(ns)
        assert sorted(os.listdir(t / "runs")) == ["a_run1", "a_run2", "b_run0"]
        assert (t / "reads/a_run2/a_R2.fq.gz").read_bytes() == b"y"
        assert "merged='true'" in (t / "samples/a").read_text()
        assert "runs='a_run1 a_run2'" in (t / "samples/a").read_text()
        assert os.listdir(t / "multi_run") == ["a"]
        assert sorted(os.listdir(t / "assemblies")) == ["MEGAHIT-a", "MEGAHIT-b", "SPAdes-a", "SPAdes-b"]
        # group mapping: a and b are in different groups
        assert sorted(os.listdir(t / "aligns")) == ["MEGAHIT-a-a", "MEGAHIT-b-b", "SPAdes-a-a", "SPAdes-b-b"]
        # forced rerun with sample b removed: none of b's items may stay
        (t / "s.csv").write_text("".join((t / "s.csv").read_text().splitlines(True)[:3]))
        stage_samples(ns)
        assert sorted(os.listdir(t / "runs")) == ["a_run1", "a_run2"]
        assert sorted(os.listdir(t / "reads")) == ["a_run1", "a_run2"]
        assert sorted(os.listdir(t / "samples")) == ["a"]
        assert sorted(os.listdir(t / "assemblies")) == ["MEGAHIT-a", "SPAdes-a"]
        assert sorted(os.listdir(t / "aligns")) == ["MEGAHIT-a-a", "SPAdes-a-a"]
        bads = ("a,1,0,ILLUMINA,a_R1.fq.gz,,\n", "a,1,0,ILLUMINA,a_R1.fq.gz,a_R2.fq.gz,l.fq.gz\n", "a b,1,0,ILLUMINA,x,y,\n",
                "a,1,0,ILLUMINA,a'_R1.fq.gz,a_R2.fq.gz,\n", "a,1,0,ILLUMINA,a_R1.fq,a_R2.fq.gz,\n", "a,1,0,ILLUMINA,a R1.fq.gz,a_R2.fq.gz,\n")
        for bad in bads:
            try:
                parse_rows(list(csv.DictReader(["sample,run,group,short_reads_platform,short_reads_1,short_reads_2,long_reads\n", bad])))
            except ValueError:
                continue
            raise AssertionError(f"accepted {bad!r}")
    sys.stderr.write("selftest ok\n")


def main() -> None:
    if sys.argv[1:] == ["--selftest"]:
        selftest()
        return
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("samples")
    s.add_argument("--samplesheet", required=True)
    for k in ("reads", "runs", "samples", "multi-run", "assemblies", "aligns"):
        s.add_argument(f"--{k}", required=True)
    s.add_argument("--mirror", default="")
    s.set_defaults(fn=stage_samples)
    d = sub.add_parser("databases")
    d.add_argument("--out", required=True)
    d.add_argument("--mirror", default="")
    d.add_argument("urls", nargs="+")
    d.set_defaults(fn=stage_databases)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
