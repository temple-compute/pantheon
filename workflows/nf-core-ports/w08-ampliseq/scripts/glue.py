#!/usr/bin/env python3
"""
Channel glue of the nf-core/ampliseq test_full route, as head-node steps.

- ``split-fasta``: ``splitFasta(by: N, file: true)`` of the ASV fasta for
  DADA2_TAXONOMY (``--dada_assign_chunksize``, 10000 by default): records in
  order, ``<base>.<n>.fasta`` per chunk, each record's text unchanged.
- ``collect-tsv``: the ``collectFile(keepHeader: true, skip: 1)`` of the
  per-chunk DADA2 taxonomy tables: the first file's header once, then every
  file's rows, files in chunk order.
- ``pplace-tax``: the PPLACEFORMATTAX_SHEET merge (``splitCsv(header: true)``
  of every target's table, ``ASV_ID<TAB>taxonomy`` rows, seed header) into
  ``concatenated_taxonomy.tsv``, targets in name order.

Row order of the merged tables can differ from Nextflow's (collectFile sorts
by its own criteria); every consumer keys the rows by ASV_ID.

stdlib only. Usage:
    glue.py split-fasta --in ASV_seqs.fasta --by 10000 --out DIR
    glue.py collect-tsv --out FILE --pattern REGEX DIR...
    glue.py pplace-tax --out FILE --pattern REGEX DIR...

The merge inputs are the files under DIR (recursively) whose name matches
REGEX (a full match).
    glue.py --selftest
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import tempfile
from pathlib import Path


def split_fasta(src: Path, by: int, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    base = src.name.rsplit(".", 1)[0]
    records: list[str] = []
    cur: list[str] = []
    for line in src.read_text().splitlines(keepends=True):
        if line.startswith(">") and cur:
            records.append("".join(cur))
            cur = []
        cur.append(line)
    if cur:
        records.append("".join(cur))
    files = []
    for i in range(0, len(records), by):
        f = out / f"{base}.{i // by + 1}.fasta"
        f.write_text("".join(records[i:i + by]))
        files.append(f)
    return files


def chunk_key(p: Path) -> tuple[int, str]:
    m = re.search(r"\.(\d+)\.", p.name)
    return (int(m.group(1)) if m else 0, str(p))


def collect_tsv(out: Path, files: list[Path]) -> None:
    files = sorted(files, key=chunk_key)
    with out.open("w") as fh:
        for i, f in enumerate(files):
            lines = f.read_text().splitlines(keepends=True)
            fh.writelines(lines if i == 0 else lines[1:])


def pplace_tax(out: Path, files: list[Path]) -> None:
    with out.open("w") as fh:
        fh.write("ASV_ID\ttaxonomy\n")
        for f in sorted(files, key=lambda p: p.name):
            for r in csv.DictReader(f.read_text().splitlines(), delimiter="\t"):
                fh.write(f"{r['ASV_ID']}\t{r['taxonomy']}\n")


def find(dirs: list[Path], pattern: str) -> list[Path]:
    rx = re.compile(pattern)
    found = [p for d in dirs for p in d.rglob("*") if p.is_file() and rx.fullmatch(p.name)]
    if not found:
        raise SystemExit(f"no file matching {pattern} under {', '.join(map(str, dirs))}")
    return found


def selftest() -> None:
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        (t / "ASV_seqs.fasta").write_text(">a\nAC\nGT\n>b\nGG\n>c\nTT\n")
        got = split_fasta(t / "ASV_seqs.fasta", 2, t / "chunks")
        assert [p.name for p in got] == ["ASV_seqs.1.fasta", "ASV_seqs.2.fasta"]
        assert got[0].read_text() == ">a\nAC\nGT\n>b\nGG\n" and got[1].read_text() == ">c\nTT\n"
        (t / "x.2.tsv").write_text("ASV_ID\tg\nc\t3\n")
        (t / "x.10.tsv").write_text("ASV_ID\tg\nd\t4\n")
        (t / "x.1.tsv").write_text("ASV_ID\tg\na\t1\nb\t2\n")
        collect_tsv(t / "all.tsv", [t / "x.10.tsv", t / "x.2.tsv", t / "x.1.tsv"])
        assert (t / "all.tsv").read_text() == "ASV_ID\tg\na\t1\nb\t2\nc\t3\nd\t4\n"
        (t / "bac16s.tsv").write_text("ASV_ID\ttaxonomy\tx\nb\tB;x\t1\n")
        (t / "arc16s.tsv").write_text("ASV_ID\ttaxonomy\tx\na\tA;y\t2\n")
        pplace_tax(t / "c.tsv", [t / "bac16s.tsv", t / "arc16s.tsv"])
        assert (t / "c.tsv").read_text() == "ASV_ID\ttaxonomy\na\tA;y\nb\tB;x\n"
        assert sorted(p.name for p in find([t], r"x\.\d+\.tsv")) == ["x.1.tsv", "x.10.tsv", "x.2.tsv"]
        try:
            find([t], r"nope")
            raise AssertionError("find must stop on no match")
        except SystemExit:
            pass
    print("selftest ok")


def main() -> None:
    if "--selftest" in sys.argv:
        selftest()
        return
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("split-fasta")
    s.add_argument("--in", dest="src", type=Path, required=True)
    s.add_argument("--by", type=int, default=10000)
    s.add_argument("--out", type=Path, required=True)
    for name in ("collect-tsv", "pplace-tax"):
        c = sub.add_parser(name)
        c.add_argument("--out", type=Path, required=True)
        c.add_argument("--pattern", required=True, help="file name regex (full match)")
        c.add_argument("dirs", type=Path, nargs="+")
    a = ap.parse_args()
    if a.cmd == "split-fasta":
        if not split_fasta(a.src, a.by, a.out):
            raise SystemExit(f"{a.src}: no sequences")
    elif a.cmd == "collect-tsv":
        a.out.parent.mkdir(parents=True, exist_ok=True)
        collect_tsv(a.out, find(a.dirs, a.pattern))
    else:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        pplace_tax(a.out, find(a.dirs, a.pattern))


if __name__ == "__main__":
    main()
