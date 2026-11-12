#!/usr/bin/env python3
"""
The Groovy-side decisions of nf-core/viralrecon 3.0.0 (Illumina route), as
small file-in/file-out steps.

Each subcommand reads per-sample meta files (bash-sourceable ``key=value``,
one file per sample, named by sample id) and tool outputs, and writes the
next list of meta files. A ``horus_map`` over that list then runs only the
samples that passed, which is what the pipeline's channel ``filter`` and
``branch`` calls do.

- ``fastp``: samples with reads left after fastp
  (WorkflowIllumina.getFastpReadsAfterFiltering > 0); the others go to
  ``fail_mapped_reads_mqc.tsv``.
- ``mapped``: samples with more than ``min_mapped_reads`` mapped reads in
  the Bowtie2 flagstat (getFlagstatMappedReads); the others go to
  ``fail_mapped_samples_mqc.tsv``.
- ``ivar``: samples whose iVar variants table has more than one line
  (VARIANTS_IVAR getNumLinesInFile > 1).
- ``clade``: ``nextclade_clade_mqc.tsv`` from the Nextclade CSVs
  (getNextcladeFieldMapFromCsv).
- ``item``: the fastp, mapped or ivar check for one sample of a chained map
  (workflow.chained.yaml): exits 10 to drop it, or passes its meta.env on.

The ``*_mqc.tsv`` tables are only written when they have rows, as
``collect().ifEmpty([])`` does. Rows are sorted by sample id (Nextflow
writes them in task completion order).

Usage: decide.py <subcommand> --help, or decide.py --selftest
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

DROP = 10  # drop_exit_codes in workflow.chained.yaml

def metas(folder: str) -> list[tuple[str, str]]:
    """(sample id, meta text) per meta file in *folder*."""
    return [(p.name, p.read_text()) for p in sorted(Path(folder).iterdir()) if p.is_file()]


def find_one(root: str, name: str) -> Path:
    """The file *name* anywhere under the map output *root* (numbered slot folders)."""
    hits = sorted(Path(root).glob(f"**/{name}"))
    if not hits:
        raise FileNotFoundError(f"{name} not found under {root}")
    return hits[0]


def write_list(out: str, rows: list[tuple[str, str]]) -> None:
    d = Path(out)
    d.mkdir(parents=True, exist_ok=True)
    for old in d.iterdir():
        old.unlink()
    for sid, text in rows:
        (d / sid).write_text(text)


def write_mqc(path: str, header: list[str], rows: list[str]) -> None:
    """WorkflowCommons.multiqcTsvFromList + collectFile: no file when there are no rows."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.unlink(missing_ok=True)
    if rows:
        p.write_text("\t".join(header) + "\n" + "\n".join(rows))


def flagstat_mapped(text: str) -> int:
    mapped = 0
    for line in text.splitlines():
        if " mapped (" in line:
            mapped = int(line.split()[0])
    return mapped


def nextclade_field(text: str, field: str) -> str:
    headers: list[str] = []
    values: dict[str, str] = {}
    for i, row in enumerate(text.splitlines()):
        vals = row.split(";")
        while vals and vals[-1] == "":  # Java String.split drops trailing empty strings
            vals.pop()
        if i == 0:
            headers = vals
        else:
            for j, h in enumerate(headers):
                values[h] = (vals[j] if j < len(vals) else "") or "NA"
    return values[field]


def cmd_fastp(a: argparse.Namespace) -> None:
    keep, fail = [], []
    for sid, text in metas(a.samples):
        summary = json.loads(find_one(a.fastp, f"{sid}.fastp.json").read_text())["summary"]
        if int(summary["after_filtering"]["total_reads"]) > 0:
            keep.append((sid, text))
        else:
            fail.append(f"{sid}\t{int(summary['before_filtering']['total_reads'])}")
    write_list(a.out, keep)
    write_mqc(a.fail_tsv, ["Sample", "Reads before trimming"], fail)


def cmd_mapped(a: argparse.Namespace) -> None:
    keep, fail = [], []
    for sid, text in metas(a.samples):
        mapped = flagstat_mapped(find_one(a.flagstat, f"{sid}.sorted.bam.flagstat").read_text())
        if mapped > a.min_mapped_reads:
            keep.append((sid, text))
        else:
            fail.append(f"{sid}\t{mapped}")
    write_list(a.out, keep)
    write_mqc(a.fail_tsv, ["Sample", "Mapped reads"], fail)


def cmd_ivar(a: argparse.Namespace) -> None:
    keep = []
    for sid, text in metas(a.samples):
        if len(find_one(a.tsv, f"{sid}.tsv").read_text().splitlines()) > 1:
            keep.append((sid, text))
    write_list(a.out, keep)


def cmd_clade(a: argparse.Namespace) -> None:
    rows = []
    for csv_path in sorted(Path(a.nextclade).glob("**/*.csv")):
        sid = csv_path.name[: -len(".csv")]
        rows.append(f"{sid}\t{nextclade_field(csv_path.read_text(), 'clade')}")
    write_mqc(a.out, ["Sample", "clade"], rows)


def cmd_item(a: argparse.Namespace) -> None:
    meta = Path(a.meta).read_text()
    sid = dict(line.split("=", 1) for line in meta.splitlines() if "=" in line)["id"]
    data = Path(a.data)
    if a.check == "fastp":
        keep = int(json.loads((data / f"{sid}.fastp.json").read_text())["summary"]["after_filtering"]["total_reads"]) > 0
    elif a.check == "mapped":
        keep = flagstat_mapped((data / f"{sid}.sorted.bam.flagstat").read_text()) > a.min_mapped_reads
    else:
        keep = len((data / f"{sid}.tsv").read_text().splitlines()) > 1
    if not keep:
        print(f"{sid}: dropped by the {a.check} filter", file=sys.stderr)
        sys.exit(DROP)
    Path(a.out).mkdir(parents=True, exist_ok=True)
    (Path(a.out) / "meta.env").write_text(meta)


def selftest() -> None:
    assert flagstat_mapped("10 + 0 in total\n7 + 0 mapped (70.00% : N/A)\n3 + 0 primary mapped (30.00% : N/A)\n") == 3
    assert nextclade_field("index;seqName;clade;x\n0;S A;19A;;\n", "clade") == "19A"
    assert nextclade_field("index;seqName;clade;x\n0;S A;;1\n", "clade") == "NA"
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t / "s").mkdir()
        (t / "s/A").write_text("single_end=false\n")
        (t / "s/B").write_text("single_end=true\n")
        for sid, after in (("A", 5), ("B", 0)):
            (t / f"fp/{sid[0]}").mkdir(parents=True, exist_ok=True)
            summary = {"before_filtering": {"total_reads": 9}, "after_filtering": {"total_reads": after}}
            (t / f"fp/{sid[0]}/{sid}.fastp.json").write_text(json.dumps({"summary": summary}))
        cmd_fastp(argparse.Namespace(samples=t / "s", fastp=str(t / "fp"), out=str(t / "p"), fail_tsv=str(t / "f.tsv")))
        assert [p.name for p in (t / "p").iterdir()] == ["A"]
        assert (t / "f.tsv").read_text() == "Sample\tReads before trimming\nB\t9"
        (t / "fs/0").mkdir(parents=True)
        (t / "fs/0/A.sorted.bam.flagstat").write_text("1000 + 0 mapped (1%)\n")
        cmd_mapped(argparse.Namespace(samples=t / "p", flagstat=str(t / "fs"), min_mapped_reads=1000, out=str(t / "m"), fail_tsv=str(t / "m.tsv")))
        assert not list((t / "m").iterdir()) and (t / "m.tsv").read_text() == "Sample\tMapped reads\nA\t1000"
        (t / "fs/0/A.sorted.bam.flagstat").write_text("1001 + 0 mapped (1%)\n")
        cmd_mapped(argparse.Namespace(samples=t / "p", flagstat=str(t / "fs"), min_mapped_reads=1000, out=str(t / "m"), fail_tsv=str(t / "m.tsv")))
        assert [p.name for p in (t / "m").iterdir()] == ["A"] and not (t / "m.tsv").exists()
        (t / "meta.env").write_text("id=A\nsingle_end=false\n")
        item = argparse.Namespace(check="mapped", meta=str(t / "meta.env"), data=str(t / "fs/0"), min_mapped_reads=1000, out=str(t / "i"))
        cmd_item(item)
        assert (t / "i/meta.env").read_text() == "id=A\nsingle_end=false\n"
        (t / "fs/0/A.sorted.bam.flagstat").write_text("1000 + 0 mapped (1%)\n")
        try:
            cmd_item(argparse.Namespace(**{**vars(item), "out": str(t / "j")}))
            raise AssertionError("not dropped")
        except SystemExit as e:
            assert e.code == DROP and not (t / "j").exists()
        (t / "iv").mkdir()
        (t / "iv/A.tsv").write_text("REGION\tPOS\n")
        try:
            cmd_item(argparse.Namespace(check="ivar", meta=str(t / "meta.env"), data=str(t / "iv"), out=str(t / "k")))
            raise AssertionError("not dropped")
        except SystemExit as e:
            assert e.code == DROP


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("fastp")
    p.add_argument("--samples", required=True)
    p.add_argument("--fastp", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--fail-tsv", dest="fail_tsv", required=True)
    p = sub.add_parser("mapped")
    p.add_argument("--samples", required=True)
    p.add_argument("--flagstat", required=True)
    p.add_argument("--min-mapped-reads", dest="min_mapped_reads", type=int, required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--fail-tsv", dest="fail_tsv", required=True)
    p = sub.add_parser("ivar")
    p.add_argument("--samples", required=True)
    p.add_argument("--tsv", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("clade")
    p.add_argument("--nextclade", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("item")
    p.add_argument("--check", choices=["fastp", "mapped", "ivar"], required=True)
    p.add_argument("--meta", required=True, help="the sample's meta.env")
    p.add_argument("--data", required=True, help="the map slot holding the tool output")
    p.add_argument("--min-mapped-reads", dest="min_mapped_reads", type=int, default=0)
    p.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return 0
    cmds = {"fastp": cmd_fastp, "mapped": cmd_mapped, "ivar": cmd_ivar, "clade": cmd_clade, "item": cmd_item}
    if a.cmd not in cmds:
        ap.error("pick a subcommand or --selftest")
    cmds[a.cmd](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
