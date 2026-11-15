#!/usr/bin/env python3
"""
The Groovy-side steps of nf-core/fetchngs 1.13.0, as small file-in/file-out steps.

- ``ids``: read --input (one id per line), check each against
  assets/schema_input.json and write one file per id (PIPELINE_INITIALISATION).
- ``branch``: parse the SRA_RUNINFO_TO_FTP tables (splitCsv, unique) and write
  one bash-sourceable meta file per run, into the list for SRA_FASTQ_FTP or
  for the sra-tools subworkflow (the ``ch_sra_reads`` branch of
  workflows/fetchngs.nf).
- ``samplesheet``: samplesheet.csv and id_mappings.csv
  (subworkflows/local/channel_sra_create_csv).

The ``ftp`` and ``sratools`` routes are ported: runs that need Aspera or
fastq-dl stop the ``branch`` step with an error.

Usage: fetchngs.py <subcommand> --help, or fetchngs.py --selftest
"""

from __future__ import annotations

import argparse
import csv
import re
import shlex
import sys
import tempfile
from pathlib import Path

ID_RE = re.compile(r"^(((SR|ER|DR)[APRSX])|(SAM(N|EA|D))|(PRJ(NA|EB|DB))|(GS[EM]))(\d+)$")
DL_KEYS = ["id", "run_accession", "single_end", "fastq_1", "fastq_2", "md5_1", "md5_2"]
EXTRAS = {
    "ampliseq": {"run": ""},
    "atacseq": {"replicate": "1"},
    "mag": {"group": "", "short_reads_platform": "ILLUMINA", "long_reads_platform": ""},
    "rnaseq": {"strandedness": None},  # filled with --strandedness
    "sarek": {"patient": None},  # filled with sample_accession
    "taxprofiler": {"fasta": ""},
}


def flag(s: str) -> bool:
    return s.strip().lower() == "true"


def ids(a: argparse.Namespace) -> None:
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for n, line in enumerate(Path(a.input).read_text().splitlines(), 1):
        i = line.strip()
        if not i:
            continue
        if not ID_RE.match(i):
            sys.exit(f"{a.input} line {n}: '{i}' is not a valid SRA, ENA, DDBJ or GEO identifier")
        (out / i).write_text(i + "\n")


def runs(metadata: str) -> list[dict[str, str]]:
    """SRA_RUNINFO_TO_FTP rows: filter(size > 0), splitCsv(header, tab), unique()."""
    rows: list[dict[str, str]] = []
    for tsv in sorted(Path(metadata).rglob("*.runinfo_ftp.tsv")):
        if tsv.stat().st_size == 0:
            continue
        with tsv.open(newline="") as fh:
            for row in csv.DictReader(fh, delimiter="\t"):
                if row not in rows:
                    rows.append(row)
    return rows


def branch(a: argparse.Namespace) -> None:
    lists = {"ftp": Path(a.ftp), "sratools": Path(a.sratools)}
    for d in lists.values():
        d.mkdir(parents=True, exist_ok=True)
    if flag(a.skip_fastq_download):
        return
    for m in runs(a.metadata):
        method = "ftp"
        if m.get("fastq_aspera") and a.download_method == "aspera":
            method = "aspera"
        if a.download_method == "fastq-dl":
            method = "fastq-dl"
        if (not m.get("fastq_aspera") and not m["fastq_1"]) or a.download_method == "sratools":
            method = "sratools"
        if method not in lists:
            sys.exit(f"{m['id']}: download method '{method}' is not ported (ftp and sratools are)")
        meta = {k: m[k] for k in DL_KEYS}
        (lists[method] / m["id"]).write_text("".join(f"{k}={shlex.quote(v)}\n" for k, v in meta.items()))


def pipeline_map(m: dict[str, str], pipeline: str, strandedness: str) -> dict[str, str]:
    """buildPipelineMap() of channel_sra_create_csv."""
    extra = dict(EXTRAS.get(pipeline, {}))
    if "strandedness" in extra:
        extra["strandedness"] = strandedness
    if "patient" in extra:
        extra["patient"] = m["sample_accession"]
    drop = {"id", "md5_1", "md5_2", "single_end", "fastq_1", "fastq_2"}
    out = {"sample": "_".join(m["id"].split("_")[:-1]), "fastq_1": m["fastq_1"], "fastq_2": m["fastq_2"]}
    out.update(extra)
    out.update({k: v for k, v in m.items() if k not in drop})
    return out


def collect(items: list[str]) -> str:
    """collectFile(newLine, keepHeader, sort) then tokenize('\\n').join('\\n')."""
    items = sorted(items)
    lines = [items[0].split("\n")[0]] if items else []
    for it in items:
        lines += it.split("\n")[1:]
    return "\n".join(x for x in lines if x)


def quoted(values) -> str:
    return ",".join(f'"{v}"' for v in values)


def samplesheet(a: argparse.Namespace) -> None:
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    fastq = sorted((p for d in a.fastq for p in Path(d).rglob("*.fastq.gz")), key=lambda p: p.name)
    sheet, mappings = [], []
    fields = ["sample"] + [f.strip().lower() for f in a.mapping_fields.split(",")] if a.mapping_fields else []
    for m in runs(a.metadata):
        m = dict(m)
        if not flag(a.skip_fastq_download):
            single = flag(m["single_end"])
            # path("*fastq.gz") of SRA_FASTQ_FTP / SRATOOLS_FASTERQDUMP: <id>.fastq.gz or <id>_<n>.fastq.gz
            reads = [str(p.resolve()) for p in fastq if p.name.startswith((m["id"] + ".", m["id"] + "_"))]
            if not reads:
                sys.exit(f"{m['id']}: no downloaded reads in {a.fastq}")
            m["fastq_1"] = reads[0]
            m["fastq_2"] = reads[1] if len(reads) > 1 and not single else ""
        pm = pipeline_map(m, a.nf_core_pipeline, a.strandedness)
        sheet.append(quoted(f'{k}' for k in pm) + "\n" + quoted(pm.values()))
        if len(set(pm) | set(fields)) != len(pm):
            sys.exit(
                f"Invalid option for '--sample_mapping_fields': {a.mapping_fields}.\n"
                f"Valid options: {', '.join(pm)}"
            )
        mappings.append(quoted(fields) + "\n" + quoted(pm[f] for f in fields))
    (out / "samplesheet.csv").write_text(collect(sheet))
    (out / "id_mappings.csv").write_text(collect(mappings))


def selftest() -> None:
    with tempfile.TemporaryDirectory() as d:
        t = Path(d)
        (t / "ids.csv").write_text("SRR9984183\nGSE214215\n\n")
        ids(argparse.Namespace(input=t / "ids.csv", out=t / "ids"))
        assert sorted(p.name for p in (t / "ids").iterdir()) == ["GSE214215", "SRR9984183"]
        (t / "md" / "0").mkdir(parents=True)
        hdr = ["id", "run_accession", "sample_accession", "fastq_ftp", "fastq_1", "fastq_2", "md5_1", "md5_2", "single_end", "fastq_aspera"]
        rows = [
            ["SRX2_SRR2", "SRR2", "SAMN2", "a;b", "u/SRR2_1.fastq.gz", "u/SRR2_2.fastq.gz", "m1", "m2", "false", "x"],
            ["SRX1_SRR1", "SRR1", "SAMN1", "a", "u/SRR1.fastq.gz", "", "m1", "", "true", "x"],
        ]
        (t / "md" / "0" / "X.runinfo_ftp.tsv").write_text("\n".join("\t".join(r) for r in [hdr] + rows + [rows[0]]) + "\n")
        branch(argparse.Namespace(metadata=t / "md", ftp=t / "ftp", sratools=t / "sra", skip_fastq_download="false", download_method="ftp"))
        assert sorted(p.name for p in (t / "ftp").iterdir()) == ["SRX1_SRR1", "SRX2_SRR2"]
        assert "single_end=true\n" in (t / "ftp" / "SRX1_SRR1").read_text()
        branch(argparse.Namespace(metadata=t / "md", ftp=t / "ftp2", sratools=t / "sra2", skip_fastq_download="false", download_method="sratools"))
        assert sorted(p.name for p in (t / "sra2").iterdir()) == ["SRX1_SRR1", "SRX2_SRR2"] and not list((t / "ftp2").iterdir())
        for n in ["SRX1_SRR1.fastq.gz", "SRX2_SRR2_1.fastq.gz", "SRX2_SRR2_2.fastq.gz"]:
            (t / "fq" / "0").mkdir(parents=True, exist_ok=True)
            (t / "fq" / "0" / n).write_bytes(b"")
        ns = argparse.Namespace(metadata=t / "md", fastq=[t / "fq"], skip_fastq_download="false", nf_core_pipeline="sarek",
                                strandedness="auto", mapping_fields="run_accession", out=t / "ss")
        samplesheet(ns)
        s = (t / "ss" / "samplesheet.csv").read_text().split("\n")
        assert s[0] == '"sample","fastq_1","fastq_2","patient","run_accession","sample_accession","fastq_ftp","fastq_aspera"', s[0]
        assert s[1].startswith('"SRX1",') and s[2].startswith('"SRX2",') and len(s) == 3, s
        assert (t / "ss" / "id_mappings.csv").read_text() == '"sample","run_accession"\n"SRX1","SRR1"\n"SRX2","SRR2"'
        ns.mapping_fields = "nope"
        try:
            samplesheet(ns)
            raise AssertionError("bad mapping field accepted")
        except SystemExit:
            pass
    print("selftest ok")


def main() -> None:
    if sys.argv[1:] == ["--selftest"]:
        return selftest()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ids")
    p.add_argument("--input", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=ids)
    p = sub.add_parser("branch")
    p.add_argument("--metadata", required=True)
    p.add_argument("--skip-fastq-download", default="false")
    p.add_argument("--download-method", default="ftp")
    p.add_argument("--ftp", required=True)
    p.add_argument("--sratools", required=True)
    p.set_defaults(fn=branch)
    p = sub.add_parser("samplesheet")
    p.add_argument("--metadata", required=True)
    p.add_argument("--fastq", nargs="*", default=[], help="download output folders")
    p.add_argument("--skip-fastq-download", default="false")
    p.add_argument("--nf-core-pipeline", default="")
    p.add_argument("--strandedness", default="auto")
    p.add_argument("--mapping-fields", default="")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=samplesheet)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
