#!/usr/bin/env python3
"""
Stage the nf-core/taxprofiler 2.0.1 inputs and plan every process instance.

The pipeline decides in Groovy, before any tool runs, which reads go through
which preprocessing step and which (sample, database) pairs each profiler
gets. Those decisions depend only on the samplesheet, the database sheet and
the params, so this script makes them all up front, for the route the test
profile runs (fastp with pair merging, porechop_abi + nanoq, BBDuk, bowtie2
and minimap2 host removal, run merging, every profiler but MALT and mOTUs,
Krona and taxpasta).

It downloads (or copies from ``--mirror``) the reads into ``reads/<id>_<run>/``
and the databases, host reference and sylph taxonomy into ``dbs/``, then writes
one folder of job files per process family under ``--jobs``. A job file is
bash: ``key=value`` lines and arrays of globs rooted at upper-case variables
(``$RAW``, ``$DBS``, ``$UNTAR``, ``$FASTP``, ...) that each task sets to its
input folders before sourcing the file. Map slots are numbered, so upstream
outputs are found as ``$ROOT/*/<file name>``.

stdlib only.

Usage:
    plan.py --samplesheet S --databases D --hostremoval-reference URL
            --sylph-taxonomy URL [--mirror DIR] --reads R --dbs B --jobs J
    plan.py --selftest
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
LONG = ("OXFORD_NANOPORE", "PACBIO_SMRT")

# The test profile's params (conf/test.config over nextflow.config).
RUN = {
    "kaiju": True, "kraken2": True, "bracken": True, "malt": False,
    "metaphlan": True, "centrifuge": True, "diamond": True, "krakenuniq": True,
    "motus": False, "ganon": True, "kmcp": True, "sylph": True, "melon": True,
    "metacache": True,
}
GANON_REPORT_ARGS = "--report-type reads  --top-percentile 0 --min-count 0 --max-count 0"

LISTS = [
    "untar", "raw_qc", "short", "long", "merge",
    "kraken2", "bracken", "centrifuge", "metaphlan", "kaiju", "diamond",
    "ganon", "kmcp", "sylph", "melon", "metacache",
    "kreport2krona", "krona", "taxpasta_merge", "taxpasta_standardise",
    "bracken_combine", "centrifuge_combine", "kaiju_combine", "kraken2_combine",
    "metaphlan_combine", "ganon_combine", "sylph_combine",
]


def jsplit(s: str) -> list[str]:
    """Java String.split(";"): trailing empty strings are dropped; no match -> [s]."""
    if ";" not in s:
        return [s]
    parts = s.split(";")
    while parts and parts[-1] == "":
        parts.pop()
    return parts


def first_param(s: str) -> str:
    p = jsplit(s)
    return p[0] if p else ""


def second_param(s: str) -> str:
    p = jsplit(s)
    return p[1] if len(p) == 2 else ""


def find_in_mirror(mirror: str, name: str) -> Path | None:
    if not mirror:
        return None
    for root, _dirs, files in os.walk(mirror):
        if name in files:
            return Path(root) / name
    return None


def fetch(src: str, base: Path, dest: Path, mirror: str) -> None:
    """Copy *src* (URL or path) to *dest* through ``dest.part``; link an absolute path."""
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    local = find_in_mirror(mirror, Path(src).name) if "://" in src else base / src
    if "://" not in src and Path(src).is_absolute():
        local.stat()
        part.unlink(missing_ok=True)
        part.symlink_to(local)
    elif local is not None:
        shutil.copyfile(local, part)
    else:
        subprocess.run(["curl", "-fsSL", "--retry", "3", "-o", str(part), src], check=True)
    os.replace(part, dest)


def q(v: str) -> str:
    return "'" + v.replace("'", "'\\''") + "'"


def write_job(jobs: Path, lst: str, key: str, fields: dict) -> None:
    lines = []
    for k, v in fields.items():
        if isinstance(v, list):
            lines.append(f"{k}=({' '.join(v)})")
        elif isinstance(v, bool):
            lines.append(f"{k}={'true' if v else 'false'}")
        else:
            lines.append(f"{k}={q(str(v))}")
    (jobs / lst / key).write_text("\n".join(lines) + "\n")


def basename(src: str) -> str:
    return Path(src).name


def read_samplesheet(path: Path) -> list[dict]:
    runs = []
    with path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            row = {k: (v or "").strip() for k, v in row.items()}
            for k in ("sample", "run_accession"):
                if not ID_RE.fullmatch(row[k]):
                    sys.exit(f"bad {k}: {row[k]!r}")
            plat = row["instrument_platform"]
            f1, f2, fa = row.get("fastq_1", ""), row.get("fastq_2", ""), row.get("fasta", "")
            is_fasta = bool(fa)
            single_end = bool(f1 and not f2 and plat not in LONG)
            if not is_fasta and not f1:
                sys.exit(f"fastq_1 missing for {row['run_accession']}")
            if plat == "PACBIO_SMRT" and not is_fasta:
                sys.exit("PacBio FASTQ input is not ported (no long-read QC branch for it)")
            if plat in LONG and f2:
                sys.exit(f"long reads with fastq_2: {row['run_accession']}")
            run = {
                "id": row["sample"], "run": row["run_accession"], "platform": plat,
                "single_end": single_end, "is_fasta": is_fasta,
                "files": [fa] if is_fasta else [f for f in (f1, f2) if f],
            }
            # ch_input.branch in workflows/taxprofiler.nf
            if not is_fasta and (single_end or f2):
                run["branch"], run["type"] = "fastq", "short"
            elif plat == "OXFORD_NANOPORE" and not is_fasta:
                run["branch"], run["type"], run["single_end"] = "nanopore", "long", True
            elif is_fasta:
                run["branch"], run["single_end"] = "fasta", True
                run["type"] = "short" if plat == "ILLUMINA" else "long"
            else:
                sys.exit(f"unsupported row: {row}")
            runs.append(run)
    return runs


def read_databases(path: Path) -> list[dict]:
    dbs = []
    with path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            row = {k: (v or "").strip() for k, v in row.items()}
            row["db_type"] = row.get("db_type") or "short;long"
            dbs.append(row)
    return dbs


def plan(runs: list[dict], dbs: list[dict], jobs: Path) -> None:
    for lst in LISTS:
        (jobs / lst).mkdir(parents=True, exist_ok=True)

    # -- databases: UNTAR once per enabled .tar.gz, else used as is
    db_path = {}
    untar_seen = []
    for d in dbs:
        name = basename(d["db_path"])
        if name.endswith(".tar.gz"):
            simple = name.split(".")[0]
            if RUN.get(d["tool"]) and name not in untar_seen:
                untar_seen.append(name)
                write_job(jobs, "untar", simple, {"prefix": simple, "archive": [f"$DBS/{name}"]})
            db_path[d["db_name"], d["tool"]] = f"$UNTAR/*/{simple}"
        else:
            db_path[d["db_name"], d["tool"]] = f"$DBS/{name}"

    # -- per run: raw QC, preprocessing, host removal
    final = {}  # group key (meta minus run_accession) -> reads, in samplesheet order
    for r in runs:
        p = f"{r['id']}_{r['run']}"
        raw = [f"$RAW/{p}/{basename(f)}" for f in r["files"]]
        if r["branch"] in ("fastq", "nanopore"):
            write_job(jobs, "raw_qc", p, {"prefix": f"{p}_raw", "reads": raw})
        if r["branch"] == "fastq":
            # FASTP_SINGLE / FASTP_PAIRED (shortread_qc_mergepairs: merged reads go on as single-end)
            fastp_out = f"$FASTP/*/{p}.fastp.fastq.gz" if r["single_end"] else f"$FASTP/*/{p}.merged.fastq.gz"
            write_job(jobs, "short", p, {
                "id": r["id"], "run": r["run"], "prefix": p, "single_end": r["single_end"],
                "reads": raw, "fastp_reads": [fastp_out], "bbduk_reads": [f"$BBDUK/*/{p}.fastq.gz"],
            })
            reads = [f"$BT2/*/{p}.unmapped.fastq.gz"]
        elif r["branch"] == "nanopore":
            write_job(jobs, "long", p, {
                "id": r["id"], "run": r["run"], "prefix": p, "reads": raw,
                "porechop_reads": [f"$PORECHOP/*/{p}_porechop_abi.fastq.gz"],
                "nanoq_reads": [f"$NANOQ/*/{p}_filtered.fastq.gz"],
            })
            reads = [f"$SFQ/*/{p}.unmapped_other.fastq.gz"]
        else:
            reads = raw
        key = (r["id"], r["platform"], True, r["is_fasta"], r["type"])
        g = final.setdefault(key, {"id": r["id"], "platform": r["platform"], "is_fasta": r["is_fasta"],
                                   "type": r["type"], "reads": [], "runs": []})
        g["reads"] += reads
        g["runs"].append(r["run"])

    # -- MERGE_RUNS (run merging; FASTA rows are mixed in after it, unmerged)
    samples = []
    for g in final.values():
        if not g["is_fasta"] and len(g["reads"]) > 1:
            write_job(jobs, "merge", g["id"], {"prefix": g["id"], "reads": g["reads"]})
            g["reads"] = [f"$MERGE/*/{g['id']}.merged.fastq.gz"]
        samples.append(g)
    # fasta samples come last, as .mix(ch_input.fasta_short, ch_input.fasta_long)
    samples.sort(key=lambda g: g["is_fasta"])

    # -- PROFILING: reads x databases of the same type
    ch_dbs = [dict(d, type=t) for d in dbs for t in d["db_type"].split(";")]
    profiles = []  # (tool, db_name, file glob), for Krona and standardisation
    classif = []  # (tool, db_name, file glob)
    for s in samples:
        for d in ch_dbs:
            if d["type"] != s["type"] or not RUN.get(d["tool"]):
                continue
            tool, dbn, params = d["tool"], d["db_name"], d["db_params"]
            db = [db_path[dbn, tool]]
            longread = s["platform"] in LONG
            base = {"id": s["id"], "single_end": True, "reads": s["reads"], "db": db}
            key = f"{s['id']}_{dbn}"
            if tool in ("kraken2", "bracken"):
                if tool == "bracken" and longread:
                    continue
                pre = f"{key}.bracken" if tool == "bracken" else f"{key}.kraken2"
                write_job(jobs, "kraken2", f"{key}_{tool}", dict(base, prefix=pre, args=first_param(params)))
                report = f"$KRAKEN2/*/{pre}.kraken2.report.txt"
                profiles.append(("kraken2-bracken" if tool == "bracken" else "kraken2", dbn, report))
                if tool == "bracken" and RUN["kraken2"]:
                    write_job(jobs, "bracken", key, {
                        "id": s["id"], "prefix": f"{key}.bracken", "args": second_param(params),
                        "db": db, "report": [report],
                    })
                    profiles.append(("bracken", dbn, f"$BRACKEN/*/{key}.bracken.tsv"))
            elif tool == "centrifuge":
                if s["is_fasta"]:
                    continue
                write_job(jobs, "centrifuge", key, dict(base, prefix=f"{key}.centrifuge", args=params))
                profiles.append(("centrifuge", dbn, f"$CKREPORT/*/{key}.centrifuge.txt"))
            elif tool == "metaphlan":
                write_job(jobs, "metaphlan", key, dict(base, prefix=f"{key}.metaphlan", args=params))
                profiles.append(("metaphlan", dbn, f"$METAPHLAN/*/{key}.metaphlan_profile.txt"))
            elif tool == "kaiju":
                write_job(jobs, "kaiju", key, dict(base, prefix=f"{key}.kaiju", krona=key, args=params))
                profiles.append(("kaiju", dbn, f"$KAIJUTABLE/*/{key}.kaijutable.txt"))
                classif.append(("kaiju", dbn, f"$KAIJU/*/{key}.kaiju.tsv"))
            elif tool == "diamond":
                write_job(jobs, "diamond", key, dict(base, prefix=f"{key}.diamond", args=params))
                profiles.append(("diamond", dbn, f"$DIAMOND/*/{key}.diamond.tsv"))
            elif tool == "ganon":
                if longread:
                    continue
                write_job(jobs, "ganon", key, dict(base, prefix=f"{key}.ganon", args=params))
                profiles.append(("ganon", dbn, f"$GANONREPORT/*/{key}.ganon_report.tre"))
            elif tool == "kmcp":
                if longread:
                    continue
                write_job(jobs, "kmcp", key, dict(base, prefix=f"{key}.kmcp_search", args=first_param(params),
                                                  args_profile=second_param(params)))
                profiles.append(("kmcp", dbn, f"$KMCPPROFILE/*/{key}.kmcp.profile"))
            elif tool == "sylph":
                if s["is_fasta"]:
                    continue
                write_job(jobs, "sylph", key, dict(base, prefix=f"{key}.sylph", args=first_param(params),
                                                   args_tax=second_param(params)))
                profiles.append(("sylph", dbn, f"$SYLPHTAX/*/{key}.sylphmpa"))
            elif tool == "melon":
                if s["type"] != "long":
                    continue
                write_job(jobs, "melon", key, dict(base, prefix=key, args=params))
                profiles.append(("melon", dbn, f"$MELON/*/{key}/*.tsv"))
            elif tool == "metacache":
                write_job(jobs, "metacache", key, dict(base, prefix=key, args=params))
                profiles.append(("metacache", dbn, f"$METACACHE/*/{key}.mapping.txt"))

    # -- VISUALIZATION_KRONA: kraken2-style reports -> text; kaiju text per job (KAIJU2KRONA)
    krona = {}
    for tool, dbn, f in profiles:
        if tool in ("kraken2", "kraken2-bracken", "centrifuge"):
            name = f.rsplit("/", 1)[1].split(".")[0]  # <id>_<db_name>
            write_job(jobs, "kreport2krona", f"{name}_{tool}", {"prefix": name, "report": [f]})
            krona.setdefault((dbn, tool), []).append(f"$KREPORT2KRONA/*/{name}.txt")
    for tool, dbn, f in classif:
        name = f.rsplit("/", 1)[1].split(".")[0]
        krona.setdefault((dbn, tool), []).append(f"$KAIJU2KRONA/*/{name}.txt")
    for (dbn, tool), files in krona.items():
        write_job(jobs, "krona", f"{tool}_{dbn}", {"prefix": f"{tool}_{dbn}", "reports": files})

    # -- STANDARDISATION_PROFILES: taxpasta per (tool, db), then each tool's own merge
    groups = {}
    for tool, dbn, f in profiles:
        groups.setdefault((tool, dbn), []).append(f)
    for (tool, dbn), files in groups.items():
        if tool in ("sylph", "melon", "metacache"):
            continue
        prof = "kraken2" if tool == "kraken2-bracken" else tool
        gid = f"{dbn}-bracken" if tool == "kraken2-bracken" else dbn
        lst = "taxpasta_merge" if len(files) > 1 else "taxpasta_standardise"
        write_job(jobs, lst, f"{prof}_{gid}", {"prefix": f"{prof}_{gid}", "profiler": prof, "profiles": files})
    combine = {
        "bracken": "bracken_combine", "centrifuge": "centrifuge_combine", "kraken2": "kraken2_combine",
        "kraken2-bracken": "kraken2_combine", "metaphlan": "metaphlan_combine",
        "ganon": "ganon_combine", "sylph": "sylph_combine",
    }
    prefixes = {
        "bracken_combine": "bracken", "centrifuge_combine": "centrifuge", "kraken2_combine": "kraken2",
        "metaphlan_combine": "metaphlan", "ganon_combine": "ganon", "sylph_combine": "sylph",
    }
    for (tool, dbn), files in groups.items():
        lst = combine.get(tool)
        if not lst:
            continue
        gid = f"{dbn}-bracken" if tool == "kraken2-bracken" else dbn
        write_job(jobs, lst, gid, {"prefix": f"{prefixes[lst]}_{gid}_combined_reports", "profiles": files})
    kaiju = {}
    for tool, dbn, f in classif:
        kaiju.setdefault(dbn, []).append(f)
    for dbn, files in kaiju.items():
        write_job(jobs, "kaiju_combine", dbn, {
            "prefix": f"kaiju_{dbn}_combined_reports", "profiles": files,
            "db": [db_path[dbn, "kaiju"]],
        })


def stage(args) -> None:
    sheet, dbsheet = Path(args.samplesheet), Path(args.databases)
    runs, dbs = read_samplesheet(sheet), read_databases(dbsheet)
    out_reads, out_dbs, jobs = Path(args.reads), Path(args.dbs), Path(os.path.normpath(args.jobs))
    out_reads.mkdir(parents=True, exist_ok=True)
    out_dbs.mkdir(parents=True, exist_ok=True)
    for r in runs:
        for f in r["files"]:
            fetch(f, sheet.parent, out_reads / f"{r['id']}_{r['run']}" / basename(f), args.mirror)
    for d in dbs:
        if RUN.get(d["tool"]):
            fetch(d["db_path"], dbsheet.parent, out_dbs / basename(d["db_path"]), args.mirror)
    for src in (args.hostremoval_reference, args.sylph_taxonomy):
        fetch(src, sheet.parent, out_dbs / basename(src), args.mirror)
    (out_dbs / "refs.env").write_text(
        f"host_fasta={q(basename(args.hostremoval_reference))}\n"
        f"sylph_taxonomy={q(basename(args.sylph_taxonomy))}\n"
    )
    plan(runs, dbs, jobs)


def selftest() -> None:
    assert jsplit("") == [""] and jsplit(";-m 0") == ["", "-m 0"] and jsplit("a;") == ["a"]
    assert first_param(";-m 0") == "" and second_param(";-m 0") == "-m 0" and second_param("-m 60") == ""
    here = Path(__file__).resolve().parent.parent / "examples"
    with tempfile.TemporaryDirectory() as tmp:
        jobs = Path(tmp)
        plan(read_samplesheet(here / "samplesheet.csv"), read_databases(here / "databases.csv"), jobs)
        n = {lst: len(os.listdir(jobs / lst)) for lst in LISTS}
        # Instance counts of `nextflow run nf-core/taxprofiler -r 2.0.1 -profile test` (trace.txt)
        want = {"untar": 10, "raw_qc": 5, "short": 4, "long": 1, "merge": 1, "kraken2": 6, "bracken": 3,
                "centrifuge": 2, "metaphlan": 6, "kaiju": 10, "diamond": 10, "ganon": 3, "kmcp": 3,
                "sylph": 3, "melon": 2, "metacache": 2, "kreport2krona": 8, "krona": 6}
        bad = {k: (n[k], v) for k, v in want.items() if n[k] != v}
        assert not bad, bad
        merge = (jobs / "merge" / "2612").read_text()
        assert "ERR5766176.unmapped" in merge and merge.index("ERR5766176_B") < merge.index("ERR5766180")
    sys.stderr.write("selftest ok\n")


def main() -> None:
    if "--selftest" in sys.argv:
        selftest()
        return
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--samplesheet", required=True)
    ap.add_argument("--databases", required=True)
    ap.add_argument("--hostremoval-reference", required=True)
    ap.add_argument("--sylph-taxonomy", required=True)
    ap.add_argument("--mirror", default="")
    ap.add_argument("--reads", required=True)
    ap.add_argument("--dbs", required=True)
    ap.add_argument("--jobs", required=True, help="parent of the job folders")
    stage(ap.parse_args())


if __name__ == "__main__":
    main()
